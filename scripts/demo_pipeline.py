#!/usr/bin/env python3
"""
Сквозной прогон обновлённого конвейера оцифровки.

Гоняет реальные книги через все пять инвариантов и печатает, что произошло
на каждой стадии:

    приём → И2 ответы из книги → гейты → И5 консенсус → И3 staging → промоушен

Источник — выгрузка прототипа (`newocr/mathocr/data/out`): 6 книг, 2 654 задачи,
10 769 формул. Ни одного вызова API и ни одного PDF: всё, что показывает этот
прогон, — детерминированные проверки и join по номеру.

    python3 scripts/demo_pipeline.py                      # только отчёт
    python3 scripts/demo_pipeline.py --apply              # + запись в staging
    python3 scripts/demo_pipeline.py --books textzadachi5

Без `--apply` БД не нужна вовсе: стадии 1–4 работают на файлах.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline import answer_key as AK  # noqa: E402
from src.pipeline import consensus as C  # noqa: E402
from src.pipeline import gates as G  # noqa: E402
from src.pipeline import structure as ST  # noqa: E402
from src.pipeline import scoring as SC  # noqa: E402
from src.pipeline import provenance as prov  # noqa: E402
from src.pipeline.models import ExtractedTask  # noqa: E402
from src.pipeline.prototype_ingest import discover_books, load_book  # noqa: E402

DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "newocr" / "mathocr" / "data" / "out"

#: Пространство имён для стабильных UUID книг: один и тот же учебник получает
#: один и тот же id при каждом прогоне, иначе staging плодил бы дубли.
_BOOK_NS = uuid.UUID("6f1a1d3e-0000-4000-8000-000000000000")


def book_uuid(name: str) -> str:
    return str(uuid.uuid5(_BOOK_NS, name))


class BookResult:
    def __init__(self, name: str):
        self.name = name
        self.n_tasks = 0
        self.book_answers = 0
        self.join: AK.JoinReport | None = None
        self.marked_solution = 0
        self.gate: Dict[str, int] = {}
        self.formulas = 0
        self.broken = 0
        self.artifacts = 0
        self.compile_measured = True
        self.consensus_flagged = 0
        self.structure: Dict[str, int] = {}
        self.review: Dict[str, object] = {}
        self.staged = 0
        self.coverage: float | None = None


def run_book(
    book_dir: Path, *, compile_formulas: bool, limit: int | None
) -> tuple[BookResult, List[ExtractedTask], List[G.Verdict]]:
    res = BookResult(book_dir.name)

    # ── 1. Приём ──────────────────────────────────────────────────────────
    tasks, answers = load_book(book_dir)
    if limit:
        tasks = tasks[:limit]
    res.n_tasks = len(tasks)
    res.book_answers = len(answers)
    if not tasks:
        return res, [], []

    # ── 1.5. Структурный слой ────────────────────────────────────────────
    # Идёт до всего остального: склейка меняет текст условия, а гейты и join
    # смотрят именно на текст и номер. Прогнать её после — значит проверять
    # обрывки и пришивать ответы к половинам задач.
    tasks, res.structure = ST.apply(tasks)
    res.n_tasks = len(tasks)

    # ── 2. И2: ответы из книги важнее сгенерированных ────────────────────
    # Сначала помечаем то, что уже пришло с ответом рядом с условием,
    # потом пришиваем раздел «Ответы». Порядок важен: join не перезапишет
    # книжный ответ книжным же, но и не пропустит его мимо учёта.
    res.marked_solution = AK.mark_existing_answers(tasks)
    res.join = AK.join_answers(tasks, answers)
    res.coverage = AK.answer_join_coverage(tasks)

    # ── 3. Гейты ─────────────────────────────────────────────────────────
    verdicts = G.evaluate_batch(tasks, compile_formulas=compile_formulas)
    res.gate = G.apply_verdicts(tasks, verdicts)
    res.formulas = sum(v.formulas_checked for v in verdicts)
    res.broken = sum(v.formulas_broken for v in verdicts)
    res.artifacts = sum(len(v.artifacts) for v in verdicts)
    res.compile_measured = all(v.compile_measured for v in verdicts)

    # ── 3.5. Доверие и очередь ручной проверки ───────────────────────────
    # Считается из уже готового вердикта: KaTeX прогнан выше один раз на батч.
    res.review = SC.score_tasks(tasks, verdicts)

    # ── 4. И5: кого имеет смысл гонять повторно ──────────────────────────
    # Только считаем триггеры — сами повторные проходы стоят вызовов и в
    # этом прогоне не делаются. Смысл цифры: во сколько обойдётся консенсус,
    # если его включить (он выборочный, а не сплошной).
    gapped = C.gapped_paragraphs(tasks)
    for t, v in zip(tasks, verdicts):
        need, _why = C.should_consensus(
            t, v, paragraph_has_gap=(t.paragraph_number in gapped)
        )
        if need:
            res.consensus_flagged += 1

    return res, tasks, verdicts


def print_table(results: List[BookResult]) -> None:
    hdr = (
        f"{'Книга':<16} {'задач':>6} {'ответы книги':>13} {'из книги':>9} "
        f"{'формул':>7} {'битых':>6} {'артеф.':>7} "
        f"{'pass':>5} {'review':>7} {'reject':>7} {'консенс.':>9}"
    )
    print(hdr)
    print("─" * len(hdr))
    for r in results:
        cov = "—" if r.coverage is None else f"{r.coverage:.1%}"
        matched = r.join.matched if r.join else 0
        print(
            f"{r.name:<16} {r.n_tasks:>6} {matched:>7}/{r.book_answers:<5} {cov:>9} "
            f"{r.formulas:>7} {r.broken:>6} {r.artifacts:>7} "
            f"{r.gate.get(G.PASS, 0):>5} {r.gate.get(G.REVIEW, 0):>7} "
            f"{r.gate.get(G.REJECT, 0):>7} {r.consensus_flagged:>9}"
        )
    print("─" * len(hdr))
    tot = BookResult("ИТОГО")
    for r in results:
        tot.n_tasks += r.n_tasks
        tot.book_answers += r.book_answers
        tot.formulas += r.formulas
        tot.broken += r.broken
        tot.artifacts += r.artifacts
        tot.consensus_flagged += r.consensus_flagged
        for k in (G.PASS, G.REVIEW, G.REJECT):
            tot.gate[k] = tot.gate.get(k, 0) + r.gate.get(k, 0)
    matched = sum(r.join.matched for r in results if r.join)
    cov = f"{matched / tot.n_tasks:.1%}" if tot.n_tasks else "—"
    print(
        f"{tot.name:<16} {tot.n_tasks:>6} {matched:>7}/{tot.book_answers:<5} {cov:>9} "
        f"{tot.formulas:>7} {tot.broken:>6} {tot.artifacts:>7} "
        f"{tot.gate.get(G.PASS, 0):>5} {tot.gate.get(G.REVIEW, 0):>7} "
        f"{tot.gate.get(G.REJECT, 0):>7} {tot.consensus_flagged:>9}"
    )
    if tot.formulas:
        print(f"\ncompile_rate = {1 - tot.broken / tot.formulas:.4f}  ({tot.broken} битых из {tot.formulas})")

    # Главная цифра прогона. До инварианта И2 у задачи без ответа был ровно
    # один путь — AIAnswerSolver, который писал придуманное моделью значение
    # в то же поле, что и напечатанное в книге, без всякой пометки. Столько
    # выдуманных ответов старый контур записал бы в банк неотличимо.
    no_answer = tot.n_tasks - matched
    print(
        f"\nЗадач без книжного ответа: {no_answer} из {tot.n_tasks}.\n"
        f"  Старый контур выдумал бы их все и записал неотличимо от книжных.\n"
        f"  Новый — помечает answer_source и не пускает в tasks_master без человека."
    )


def print_join_detail(results: List[BookResult]) -> None:
    print("\nJOIN ОТВЕТОВ — как система выбрала ключ")
    for r in results:
        if not r.join:
            continue
        j = r.join
        note = ""
        if j.strategy == AK.BY_PARAGRAPH_NUMBER:
            note = " — номера массово повторяются, join по номеру запрещён"
        elif j.ambiguous:
            note = f" — {j.ambiguous} номеров отказано поштучно (дубли)"
        print(f"  {r.name:<16} ключ={j.strategy:<17} пришито={j.matched:<4}{note}")


def print_review_detail(results: List[BookResult]) -> None:
    """Сколько задач уходит человеку и в каком порядке (Сессия 5)."""
    rows = [r for r in results if r.review]
    if not rows:
        return
    print("\nОЧЕРЕДЬ РУЧНОЙ ПРОВЕРКИ — где система себе не доверяет")
    total, flagged, waiting = 0, 0, 0
    for r in rows:
        n = int(r.review.get("n_tasks") or 0)
        k = int(r.review.get("n_needs_review") or 0)
        total += n
        flagged += k
        mean = r.review.get("ocr_mean")
        mean_txt = "—" if mean is None else f"{mean:.3f}"
        wait = int(r.review.get("n_awaiting_answer") or 0)
        waiting += wait
        print(
            f"  {r.name:<16} брак={k:<5} из {n:<5} ({k / n:>5.1%})  "
            f"ждут ответа={wait:<5}  ocr(средн.)={mean_txt}"
        )
    if total:
        print(
            f"  {'ИТОГО':<16} брак={flagged} из {total} ({flagged / total:.1%}), "
            f"ждут ответа={waiting}"
        )
        print(
            "  Очередь — только брак распознавания. Отсутствие ответа — вопрос\n"
            "  полноты: такие задачи держит гейт промоушена, а не очередь."
        )


def print_structure_detail(results: List[BookResult]) -> None:
    """Что структурный слой поправил в потоке задач (Сессия 4)."""
    rows = [r for r in results if r.structure and any(r.structure.values())]
    if not rows:
        print("\nСТРУКТУРА — правок нет")
        return
    print("\nСТРУКТУРА — задачи перестают быть обрывками")
    for r in rows:
        st = r.structure
        print(
            f"  {r.name:<16} контекст: снят={st['cleaned']:<4} распространён={st['propagated']:<5} "
            f"склеено через разрыв={st['merged']:<4} разделов пересортировано={st['reordered']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Сквозной прогон конвейера оцифровки")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE), help="каталог с выгрузкой книг")
    ap.add_argument("--books", nargs="*", help="только эти книги")
    ap.add_argument("--limit", type=int, help="не больше N задач на книгу")
    ap.add_argument("--apply", action="store_true", help="записать в tasks_staging (нужна БД)")
    ap.add_argument("--no-compile", action="store_true", help="без KaTeX (быстрее)")
    ap.add_argument(
        "--viewer", metavar="DIR",
        help="собрать HTML-вьюер очереди проверки по каждой книге в этот каталог",
    )
    args = ap.parse_args()

    root = Path(args.source)
    books = discover_books(root)
    if args.books:
        wanted = set(args.books)
        books = [b for b in books if b.name in wanted]
    if not books:
        print(f"Книг не найдено в {root}", file=sys.stderr)
        return 2

    print(f"\nИСТОЧНИК: {root}")
    print(f"КНИГ: {len(books)}   KaTeX: {'выключен' if args.no_compile else 'включён'}\n")

    results: List[BookResult] = []
    viewers: List[Path] = []
    staged_all = 0
    run_id = None

    if args.apply:
        if not os.environ.get("DATABASE_URL"):
            print("--apply требует DATABASE_URL", file=sys.stderr)
            return 2
        from src.pipeline.staging import StagingWriter, new_run_id
        from src.pipeline.db_writer import DBWriter

        run_id = new_run_id()
        writer = StagingWriter()
        db = DBWriter()

    for book_dir in books:
        res, tasks, verdicts = run_book(
            book_dir, compile_formulas=not args.no_compile, limit=args.limit
        )
        results.append(res)

        if args.apply and tasks:
            tb_id = book_uuid(res.name)
            db.upsert_textbook(
                textbook_id=tb_id, title=res.name, class_level=0,
                total_pages=None, subject="math",
            )
            res.staged = writer.write_batch(
                tasks, verdicts,
                textbook_id=tb_id, class_level=0, run_id=run_id,
                prefix="DEMO",
            )
            staged_all += res.staged

        if args.viewer and tasks:
            from src.viewer.build import build_viewer

            out = Path(args.viewer) / f"{res.name}.html"
            build_viewer(tasks, verdicts, out, title=f"Проверка: {res.name}")
            viewers.append(out)

    print_table(results)
    print_structure_detail(results)
    print_join_detail(results)
    print_review_detail(results)

    if viewers:
        print(f"\nВЬЮЕР — {len(viewers)} файл(ов):")
        for v in viewers:
            print(f"  {v}")

    if args.apply:
        print(f"\nSTAGING: записано {staged_all} задач, run_id = {run_id}")
        from src.pipeline.staging import promote

        rep = promote(run_id=run_id, dry_run=True)
        print("\nПРОМОУШЕН (dry-run):")
        print(f"  кандидатов (gate=pass):      {rep.candidates}")
        print(f"  прошло бы в tasks_master:    {rep.promoted}")
        if rep.blocked_no_skill:
            print(f"  заблокировано без skill_id:  {rep.blocked_no_skill}")
        if rep.blocked_bad_skill:
            print(f"  заблокировано skill не L4:   {rep.blocked_bad_skill}")
        print(f"\n  Записать: python3 scripts/promote.py --run {run_id} --apply")
    else:
        print("\n(без --apply запись в staging не делалась)")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
