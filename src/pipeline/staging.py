"""
ALGO — Staging и промоушен (инвариант И3)
src/pipeline/staging.py

Инвариант: **в `tasks_master` не пишет никто. Пишет промоушен.**

Конвейер кладёт результат в `tasks_staging` — вместе с вердиктом гейтов и
провенансом. Отдельный шаг переносит в `tasks_master` только то, что прошло.
Не прошло — остаётся в карантине с флагами и ждёт человека.

Что это даёт, чего не давала дисциплина:
* «стало лучше или сломали 200 задач» — это диф двух таблиц, а не
  восстановление дампа вслепую;
* гейт компиляции (задача 4 С2) реализуется как условие промоушена и **не
  требует трогать `orchestrator.py`** — тот самый файл, который единственный
  довёз результат и который договорились не переписывать;
* прогон можно повторить: `run_id` адресует попытку целиком.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import text

from src.pipeline import gates as G
from src.pipeline import schema_vocab as vocab
from src.pipeline.db_writer import _engine
from src.pipeline.models import ExtractedTask
from src.pipeline.smart_verify_common import SUCCESS_STATUSES
from src.pipeline.task_ids import build_source_reference, build_task_id

log = logging.getLogger("pipeline")


#: Префикс демо-узлов графа знаний (`scripts/seed_demo_skills.py`). Задачи на
#: такой навык в `tasks_master` не пускаем: это леса, а не содержание.
_DEMO_SKILL_PREFIX = "DEMO_"

#: Ниже этого числа задач схлопывание в один навык не показательно —
#: у короткого прогона это может быть правдой.
_COLLAPSE_MIN_TASKS = 20

#: `tasks_staging.task_id` — `VARCHAR(60)`. Длина живёт константой, потому что
#: от неё зависит разведение дублей (`dedupe_task_id`), а не только обрезка.
TASK_ID_MAXLEN = 60


def dedupe_task_id(task_id: str, used: set) -> str:
    """Свободный идентификатор для дубля внутри батча: `…_dup2`, `…_dup3`, …

    Суффикс приписывается **вместо хвоста базы**, а не поверх неё (B44). Было:
    `while f"{task_id}_dup{suffix}"[:60] in used: suffix += 1` — при базе,
    упирающейся в 60 символов, обрезка съедала сам суффикс, кандидат переставал
    меняться с ростом `suffix`, и цикл крутился вечно. Происходит это внутри
    открытой транзакции `engine.begin()`, то есть вешает не только прогон, но и
    держит транзакцию. Воспроизведено на id длиной 60 (два дубля) и 57 (три).

    Реальные id выходят на 32–43 символа, поэтому это была заряженная мина, а
    не текущий отказ: достаточно длинного `paragraph_number` от модели.
    """
    if task_id not in used:
        return task_id
    suffix = 2
    # Граница есть, и она не «на всякий случай»: столько различных дублей
    # одного номера в одном батче означает, что сломана сегментация, а не
    # что нужен ещё один суффикс. Дальше — id, уникальный по построению.
    while suffix < 1000:
        mark = f"_dup{suffix}"
        candidate = task_id[: TASK_ID_MAXLEN - len(mark)] + mark
        if candidate not in used:
            return candidate
        suffix += 1
    return f"dup_{uuid.uuid4().hex}"[:TASK_ID_MAXLEN]


def new_run_id() -> str:
    """Идентификатор одного прогона конвейера. Адресует попытку целиком."""
    return uuid.uuid4().hex[:16]


@dataclass
class PromotionReport:
    """Что сделал (или сделал бы) промоушен."""

    dry_run: bool = True
    candidates: int = 0
    promoted: int = 0
    blocked_no_skill: int = 0
    blocked_bad_skill: int = 0
    #: Навык — демо-заглушка (`DEMO_*`), а не настоящий узел графа знаний.
    blocked_demo_skill: int = 0
    #: Идентификатор уже занят задачей ДРУГОЙ книги. Записывать нельзя:
    #: `ON CONFLICT (id) DO NOTHING` не перезапишет чужую строку, но и нашу не
    #: сохранит — задача исчезла бы, засчитавшись как промоутнутая, а мост
    #: `textbook_tasks` привязал бы нашу книгу к чужому условию.
    blocked_id_taken: int = 0
    #: Все кандидаты схлопнулись в один навык — признак того, что графа знаний
    #: под классификатором фактически не было.
    skill_collapse: bool = False
    failed: int = 0
    errors: List[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "candidates": self.candidates,
            "promoted": self.promoted,
            "blocked_no_skill": self.blocked_no_skill,
            "blocked_bad_skill": self.blocked_bad_skill,
            "blocked_demo_skill": self.blocked_demo_skill,
            "blocked_id_taken": self.blocked_id_taken,
            "skill_collapse": self.skill_collapse,
            "failed": self.failed,
            "errors": self.errors[:10],
        }


class StagingWriter:
    """Пишет задачи в `tasks_staging` вместе с вердиктом гейтов."""

    def write_batch(
        self,
        tasks: Sequence[ExtractedTask],
        verdicts: Sequence[G.Verdict],
        *,
        textbook_id: str,
        class_level: int,
        run_id: str,
        prefix: str = "G_TB",
    ) -> int:
        """Upsert батча. Возвращает число записанных строк.

        Пишутся **все** задачи, включая `reject`: staging обязан принять брак,
        иначе он либо потеряется, либо просочится мимо учёта.
        """
        if not tasks:
            return 0
        assert len(tasks) == len(verdicts), "вердикт нужен на каждую задачу"

        engine = _engine()
        written = 0
        # Идентификаторы внутри батча разводятся принудительно. Источник
        # не гарантирует уникальности (см. gates.check_duplicate_ids), а
        # `ON CONFLICT DO UPDATE` не может задеть одну строку дважды в одной
        # транзакции — вторая задача просто исчезала бы. Дефект уже помечен
        # гейтом; здесь важно, чтобы данные не пропали.
        used: set[str] = set()
        with engine.begin() as conn:
            for i, (task, v) in enumerate(zip(tasks, verdicts, strict=True)):
                # Идентификатор строится из места в книге, а не из `temp_id`.
                # `temp_id` — рабочий номер внутри параграфа (`TEMP_6_032`): он
                # не говорит, что это за задача, и совпадает у разных книг.
                # Формат `{prefix}_{параграф}_{номер}` задан продовой базой.
                task_id = build_task_id(
                    prefix, task.paragraph_number, task.exercise_number,
                ) or (task.temp_id or f"{prefix}_{run_id}_{i:05d}")
                task_id = dedupe_task_id(task_id[:TASK_ID_MAXLEN], used)
                used.add(task_id)
                try:
                    conn.execute(text(_UPSERT_SQL), _row(task, v, task_id, textbook_id, class_level, run_id))
                    written += 1
                except Exception as exc:  # одна плохая строка не роняет батч
                    log.error("staging: %s не записана: %s", task_id, str(exc)[:200])
        log.info("staging: записано %d/%d (run=%s)", written, len(tasks), run_id)
        return written


def quality_tags(task: ExtractedTask) -> Dict[str, Any]:
    """`task.tags` плюс сигналы качества, по которым потом судят о задаче.

    Восстановление половины B41. `db_writer` дописывал сюда `sympy_verified`
    перед записью, а `staging._row` отдавал `task.tags` как есть — и признак,
    по которому расхождение «проверено/не проверял никто» можно было бы найти
    постфактум, не сохранялся вовсе.
    """
    tags = dict(task.tags or {})
    tags["sympy_verified"] = bool(task.sympy_verified)
    if task.sympy_verified:
        tags["sympy_confidence"] = round(task.sympy_confidence, 3)
    if task.mapping_confidence:
        tags.setdefault("mapping_confidence", round(task.mapping_confidence, 3))
    return tags


def verification_status(tags: object) -> str:
    """`verified` только если математику кто-то действительно проверял (B41).

    В `_INSERT_MASTER_SQL` это значение было зашито строкой `'verified'` —
    всем подряд. Гейт `pass` проверяет структуру, провенанс, артефакты и
    компиляцию формул, но **не математику**, поэтому в `tasks_master` уезжало
    «проверено» для задач, чей ответ не проверял никто.

    Оба признака, которые считались раньше, сохранены: `smart_verify_status`
    из канонического `smart_verify_common.verification_status()` и
    `sympy_verified` из `db_writer`. Ни того, ни другого нет — `pending`, и
    задачу подберёт обычная очередь smart-verify.
    """
    if not isinstance(tags, dict):
        return "pending"
    if tags.get("smart_verify_status") in SUCCESS_STATUSES:
        return "verified"
    return "verified" if tags.get("sympy_verified") else "pending"


def _row(
    task: ExtractedTask,
    v: G.Verdict,
    task_id: str,
    textbook_id: str,
    class_level: int,
    run_id: str,
) -> Dict[str, Any]:
    return {
        "task_id": task_id[:60],
        "textbook_id": textbook_id,
        "class_level": class_level,
        "skill_id": (task.skill_id or "").strip() or None,
        "toc_id": task.toc_id,
        "paragraph_number": task.paragraph_number or None,
        "exercise_number": task.exercise_number or None,
        "page": task.page or None,
        "question_text": task.question_text,
        "question_latex": task.question_latex or "",
        "shared_context": (task.shared_context or "").strip() or None,
        "correct_answer": task.answer_raw or None,
        "answer_type": task.answer_type,
        "answer_options": json.dumps(task.answer_options or [], ensure_ascii=False),
        "distractor_meta": json.dumps(task.distractor_meta or [], ensure_ascii=False),
        "difficulty": task.difficulty,
        "cognitive_load": task.cognitive_load,
        "is_star": bool(task.is_star),
        "task_category": task.task_category or "standard",
        "tags": json.dumps(quality_tags(task), ensure_ascii=False),
        # B39: IRT-параметры считались только в `db_writer`, и новый шов записи
        # потерял их целиком — в staging таких колонок не было вовсе. Для
        # CAT/IRT в diagnostics-service это значило одинаковую `irt_difficulty`
        # у каждой задачи банка: подбор задачи под theta переставал различать
        # задачи и выдавал формально работающий бессмысленный выбор.
        **vocab.irt_params(task.difficulty, task.answer_type),
        "answer_source": task.answer_source,
        "text_source": task.text_source,
        "answer_source_page": task.answer_source_page,
        "confidence": json.dumps(task.confidence or {}, ensure_ascii=False),
        "gate_status": v.status,
        "gate_reasons": json.dumps(v.reasons, ensure_ascii=False),
        "formulas_checked": v.formulas_checked,
        "formulas_broken": v.formulas_broken,
        "compile_measured": v.compile_measured,
        "run_id": run_id,
    }


_UPSERT_SQL = """
INSERT INTO tasks_staging (
    task_id, textbook_id, class_level, skill_id, toc_id,
    paragraph_number, exercise_number, page,
    question_text, question_latex, shared_context, correct_answer, answer_type,
    answer_options, distractor_meta, difficulty, cognitive_load,
    irt_discrimination, irt_difficulty, irt_guessing,
    is_star, task_category, tags,
    answer_source, text_source, answer_source_page, confidence,
    gate_status, gate_reasons, formulas_checked, formulas_broken,
    compile_measured, run_id
) VALUES (
    :task_id, CAST(:textbook_id AS UUID), :class_level, :skill_id, :toc_id,
    :paragraph_number, :exercise_number, :page,
    :question_text, :question_latex, :shared_context, :correct_answer, :answer_type,
    CAST(:answer_options AS JSONB), CAST(:distractor_meta AS JSONB),
    :difficulty, :cognitive_load,
    :irt_discrimination, :irt_difficulty, :irt_guessing,
    :is_star, :task_category, CAST(:tags AS JSONB),
    :answer_source, :text_source, :answer_source_page, CAST(:confidence AS JSONB),
    :gate_status, CAST(:gate_reasons AS JSONB), :formulas_checked, :formulas_broken,
    :compile_measured, :run_id
)
ON CONFLICT (textbook_id, task_id) DO UPDATE SET
    question_text    = EXCLUDED.question_text,
    question_latex   = EXCLUDED.question_latex,
    shared_context   = EXCLUDED.shared_context,
    correct_answer   = EXCLUDED.correct_answer,
    answer_type      = EXCLUDED.answer_type,
    answer_options   = EXCLUDED.answer_options,
    distractor_meta  = EXCLUDED.distractor_meta,
    difficulty       = EXCLUDED.difficulty,
    cognitive_load   = EXCLUDED.cognitive_load,
    irt_discrimination = EXCLUDED.irt_discrimination,
    irt_difficulty   = EXCLUDED.irt_difficulty,
    irt_guessing     = EXCLUDED.irt_guessing,
    tags             = EXCLUDED.tags,
    skill_id         = EXCLUDED.skill_id,
    toc_id           = EXCLUDED.toc_id,
    answer_source    = EXCLUDED.answer_source,
    text_source      = EXCLUDED.text_source,
    answer_source_page = EXCLUDED.answer_source_page,
    confidence       = EXCLUDED.confidence,
    gate_status      = EXCLUDED.gate_status,
    gate_reasons     = EXCLUDED.gate_reasons,
    formulas_checked = EXCLUDED.formulas_checked,
    formulas_broken  = EXCLUDED.formulas_broken,
    compile_measured = EXCLUDED.compile_measured,
    run_id           = EXCLUDED.run_id,
    updated_at       = NOW()
"""


# ---------------------------------------------------------------------------
# Промоушен
# ---------------------------------------------------------------------------

#: Кандидаты на промоушен. Условия — единственное определение «что достойно
#: попасть к ученику». Меняется только здесь.
_CANDIDATES_SQL = """
SELECT s.*
FROM tasks_staging s
WHERE s.promoted_at IS NULL
  AND s.gate_status = 'pass'
  AND (:run_id      IS NULL OR s.run_id = :run_id)
  AND (:textbook_id IS NULL OR s.textbook_id = CAST(:textbook_id AS UUID))
ORDER BY s.staging_id
"""

_INSERT_MASTER_SQL = """
INSERT INTO tasks_master (
    id, skill_id, question_text, question_latex, shared_context,
    correct_answer, correct_answer_latex, answer_type,
    difficulty, cognitive_load, distractor_meta, answer_options,
    irt_discrimination, irt_difficulty, irt_guessing,
    toc_id, tags, verification_status, source_type, source_reference,
    is_star, task_category,
    answer_source, text_source, answer_source_page, confidence,
    is_active
) VALUES (
    :id, :skill_id, :question_text, :question_latex, :shared_context,
    :correct_answer, :correct_answer_latex, :answer_type,
    :difficulty, :cognitive_load, CAST(:distractor_meta AS JSONB),
    CAST(:answer_options AS JSONB),
    :irt_discrimination, :irt_difficulty, :irt_guessing,
    :toc_id, CAST(:tags AS JSONB), :verification_status, 'textbook', :source_reference,
    :is_star, :task_category,
    :answer_source, :text_source, :answer_source_page, CAST(:confidence AS JSONB),
    TRUE
)
ON CONFLICT (id) DO NOTHING
"""

_BRIDGE_SQL = """
INSERT INTO textbook_tasks (textbook_id, task_id, paragraph_number, exercise_number)
VALUES (CAST(:textbook_id AS UUID), :task_id, :paragraph_number, :exercise_number)
ON CONFLICT (textbook_id, task_id) DO NOTHING
"""


def id_taken_by_other_book(
    owners: Dict[str, set], task_id: str, textbook_id: object,
) -> bool:
    """Идентификатор уже в `tasks_master` и принадлежит не этой книге.

    `owners` — что показала БД: id → множество книг-владельцев по
    `textbook_tasks`. Задача без строки в мосте (владелец `None`) считается
    чужой: чья она — неизвестно, а перезаписать её мы всё равно не можем.

    Повторный промоушен той же книги коллизией не считается — там `DO NOTHING`
    ровно то, что нужно.
    """
    known = owners.get(task_id)
    if known is None:
        return False
    return known != {str(textbook_id)}


def promote(
    *,
    run_id: Optional[str] = None,
    textbook_id: Optional[str] = None,
    dry_run: bool = True,
    limit: Optional[int] = None,
    allow_skill_collapse: bool = False,
) -> PromotionReport:
    """Перенести прошедшие гейты задачи из staging в `tasks_master`.

    `dry_run=True` по умолчанию и это не формальность: правило §0.7 требует
    сначала показать, что будет сделано. В режиме `dry_run` не выполняется
    ни одной записи — считаются только кандидаты и то, что их заблокирует.
    """
    engine = _engine()
    report = PromotionReport(dry_run=dry_run)

    with engine.connect() as conn:
        rows = conn.execute(
            text(_CANDIDATES_SQL), {"run_id": run_id, "textbook_id": textbook_id}
        ).mappings().all()

    if limit is not None:
        rows = rows[:limit]
    report.candidates = len(rows)
    if not rows:
        return report

    # tasks_master требует skill_id NOT NULL и уровень L4 (триггер
    # trg_tasks_master_skill_l4). Проверяем заранее, чтобы отказ был внятной
    # строкой отчёта, а не исключением из триггера посреди батча.
    skill_ids = {r["skill_id"] for r in rows if r["skill_id"]}
    valid_l4: set = set()
    if skill_ids:
        with engine.connect() as conn:
            valid_l4 = {
                r[0]
                for r in conn.execute(
                    text("SELECT id FROM knowledge_hierarchy WHERE level = 'L4' AND id = ANY(:ids)"),
                    {"ids": list(skill_ids)},
                )
            }

    # Идентификатор строится из места в книге, а префикс у книг одного класса
    # общий (в выгрузке прода три учебника 5 класса делят `G5_TB`). Значит,
    # столкновение возможно, и молчаливым оно быть не должно: `DO NOTHING`
    # оставил бы чужую задачу на месте, нашу выбросил, но засчитал как
    # промоутнутую. Берём чужие идентификаторы заранее — «чужой» здесь значит
    # «принадлежит другой книге», повторный прогон той же книги коллизией не
    # считается.
    # Владелец считается по каждой строке отдельно: `promote()` можно звать и
    # без фильтра по книге, и тогда единственного «своего» textbook_id нет.
    owners: Dict[str, set] = {}
    candidate_ids = [r["task_id"] for r in rows]
    if candidate_ids:
        with engine.connect() as conn:
            for tid, book in conn.execute(
                text("""
                    SELECT m.id, tt.textbook_id
                    FROM tasks_master m
                    LEFT JOIN textbook_tasks tt ON tt.task_id = m.id
                    WHERE m.id = ANY(:ids)
                """),
                {"ids": candidate_ids},
            ):
                owners.setdefault(tid, set()).add(str(book) if book else None)

    # Схлопывание в один навык. У настоящего учебника задачи расходятся по
    # десяткам навыков; один навык на всю книгу означает, что графа знаний под
    # классификатором не было и он поставил первое попавшееся. Проверено
    # фактом 2026-08-30: на локальной БД с демо-сидом из 4 узлов все 208 задач
    # книги получили `DEMO_S01_01_01`, и промоушен пропустил бы их — узел
    # формально уровня L4.
    if len(skill_ids) == 1 and len(rows) >= _COLLAPSE_MIN_TASKS:
        report.skill_collapse = True
        log.error(
            "промоушен: все %d задач замаплены на один навык %s — "
            "похоже, граф знаний пуст. Промоушен остановлен.",
            len(rows), next(iter(skill_ids)),
        )
        if not allow_skill_collapse:
            return report

    for r in rows:
        if not r["skill_id"]:
            report.blocked_no_skill += 1
            continue
        if str(r["skill_id"]).startswith(_DEMO_SKILL_PREFIX):
            report.blocked_demo_skill += 1
            continue
        if r["skill_id"] not in valid_l4:
            report.blocked_bad_skill += 1
            continue
        if id_taken_by_other_book(owners, r["task_id"], r["textbook_id"]):
            report.blocked_id_taken += 1
            log.error(
                "промоушен: id %s уже занят задачей другой книги — пропуск",
                r["task_id"],
            )
            continue
        if dry_run:
            report.promoted += 1
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(_INSERT_MASTER_SQL), _master_params(r))
                conn.execute(
                    text(_BRIDGE_SQL),
                    {
                        "textbook_id": str(r["textbook_id"]),
                        "task_id": r["task_id"],
                        "paragraph_number": r["paragraph_number"],
                        "exercise_number": r["exercise_number"],
                    },
                )
                conn.execute(
                    text(
                        "UPDATE tasks_staging SET promoted_at = NOW(), promoted_to = :tid "
                        "WHERE staging_id = :sid"
                    ),
                    {"tid": r["task_id"], "sid": r["staging_id"]},
                )
            report.promoted += 1
        except Exception as exc:
            report.failed += 1
            report.errors.append(f"{r['task_id']}: {str(exc)[:160]}")

    return report


def _master_params(r) -> Dict[str, Any]:
    return {
        "id": r["task_id"],
        "skill_id": r["skill_id"],
        "question_text": r["question_text"],
        "question_latex": r["question_latex"] or "",
        "shared_context": r["shared_context"],
        "correct_answer": r["correct_answer"] or "—",
        "correct_answer_latex": r["correct_answer_latex"],
        "answer_type": r["answer_type"],
        "difficulty": r["difficulty"],
        "cognitive_load": r["cognitive_load"],
        "distractor_meta": json.dumps(r["distractor_meta"] or [], ensure_ascii=False),
        "answer_options": json.dumps(r["answer_options"] or [], ensure_ascii=False),
        # IRT не пересчитывается из `difficulty` здесь: значение уже посчитано
        # на записи в staging и должно доехать тем же, каким его увидит человек
        # в карантине. Старая строка (до колонок в staging) читается как
        # отсутствие — тогда считаем на месте, чтобы не уехал дефолт схемы.
        **_master_irt(r),
        "toc_id": r["toc_id"],
        "tags": json.dumps(r["tags"] or {}, ensure_ascii=False),
        "verification_status": verification_status(r["tags"]),
        "source_reference": build_source_reference(
            r["textbook_id"], r["paragraph_number"], r["exercise_number"],
        ),
        "is_star": bool(r["is_star"]),
        "task_category": r["task_category"] or "standard",
        "answer_source": r["answer_source"],
        "text_source": r["text_source"],
        "answer_source_page": r["answer_source_page"],
        "confidence": json.dumps(r["confidence"] or {}, ensure_ascii=False),
    }


def _master_irt(r) -> Dict[str, float]:
    """Параметры IRT для вставки в `tasks_master`.

    Ноль здесь значит «не посчитано», а не «посчитано и вышло ноль». Это не
    перестраховка, а хвост B39. Миграция `a9b0c1d2e3f5` заводит колонки через
    `ADD COLUMN ... DEFAULT 0.0`, а Postgres заполняет дефолтом **уже
    существующие** строки, вместо того чтобы оставить NULL. Проверка «значение
    отсутствует» на них не срабатывала, и промоушен принимал дефолт миграции
    за результат расчёта — то есть симптом, ради которого заводился B39,
    пережил бы починку самого B39 на всех строках, записанных до неё.

    Замер на живой базе 2026-09-04: в `tasks_staging` 3 290 строк, из них 421
    готовый кандидат (`gate_status='pass'`), и у **всех 421** сохранено
    `irt_difficulty = 0.0000` при живой сложности A/B/C (69 A, 290 B, 62 C).

    Отличить дефолт от расчёта можно потому, что `irt_params` не возвращает
    ноль ни для одной сложности: `A/B/C → -1.0/0.5/1.5`. Цена правила —
    калибровка, давшая ровно 0.0, была бы пересчитана из `difficulty`. Платить
    пока нечем: калибровки нет, значение берётся только из этой формулы. Когда
    появится, у неё должен быть свой признак источника — так же, как у ответа
    его даёт провенанс, а не угадывание по самому значению.
    """
    stored = r["irt_difficulty"] if "irt_difficulty" in r.keys() else None
    if stored is None or float(stored) == 0.0:
        return vocab.irt_params(r["difficulty"], r["answer_type"])
    return {
        "irt_discrimination": float(
            r["irt_discrimination"] if r["irt_discrimination"] is not None
            else vocab.IRT_DEFAULT_DISCRIMINATION
        ),
        "irt_difficulty": float(stored),
        "irt_guessing": float(r["irt_guessing"] or 0.0),
    }
