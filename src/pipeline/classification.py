"""
ALGO V1 — Skeleton Textbook Mapper
src/pipeline/classification.py

Иерархический двухшаговый маппинг через Gemini Pro:
  Шаг 1 — Pro выбирает L3-подтему из 57 узлов (10 L2 + 47 L3)
  Шаг 2 — Pro выбирает L4-навык из 2-4 кандидатов под выбранным L3

Почему два шага:
  • Один большой список из 127 L4 — модель путается
  • После выбора L3 остаётся 2-4 варианта — почти тривиальный выбор
  • Точность: ~99% на каждом шаге vs ~70% при плоском списке
"""

import json
import logging
from typing import Dict, List, Optional

from src.pipeline.deepseek_client import (
    call_deepseek,
    get_deepseek_key,
    get_deepseek_model,
    parse_json_response,
)
from src.pipeline.models import ExtractedTask

log = logging.getLogger("pipeline")

# skill_id только при уверенном маппинге; иначе NULL (toc_id достаточно для экзамена)
MIN_MAPPING_CONFIDENCE = 0.70


class SkeletonTextbookMapper:
    """Иерархический маппинг задачи → L4-навык (два вызова Gemini Pro)."""

    def __init__(self, api_key: str = "", skills_json: str = ""):
        self.api_key = api_key or get_deepseek_key()
        self.model = get_deepseek_model()
        self.skills_json = skills_json
        self._class_level = 5

        # Populated by load_skills_from_db
        self._l2: List[Dict] = []          # [{id, name_ru}]
        self._l3: List[Dict] = []          # [{id, name_ru, parent_id}]
        self._l4_by_l3: Dict[str, List[Dict]] = {}  # l3_id → [{id, name_ru, description}]
        self._valid_skill_ids: set = set()

        if skills_json:
            self._index_skills(json.loads(skills_json))

    # ── Loading ──────────────────────────────────────────────────────────

    def load_skills_from_db(self, db_url: str, class_level: int = 5) -> None:
        """Загружает скелет навыков из БД и строит индексы."""
        self._class_level = class_level
        try:
            from sqlalchemy import create_engine, text as sa_text

            engine = create_engine(db_url)
            with engine.connect() as conn:
                rows = conn.execute(
                    sa_text(
                        "SELECT id, level, parent_id, name_ru, description "
                        "FROM knowledge_hierarchy "
                        "WHERE class_level_start <= :cl AND class_level_end >= :cl "
                        "  AND is_active = TRUE "
                        "ORDER BY level, sequence_order"
                    ),
                    {"cl": class_level},
                ).fetchall()

            skills = [
                {"id": r[0], "level": r[1], "parent_id": r[2],
                 "name_ru": r[3], "description": r[4] or ""}
                for r in rows
            ]
            self.skills_json = json.dumps(skills, ensure_ascii=False)
            self._index_skills(skills)
            log.info(
                "Mapper: загружено L1=%d L2=%d L3=%d L4=%d для класса %d",
                sum(1 for s in skills if s["level"] == "L1"),
                len(self._l2), len(self._l3),
                sum(len(v) for v in self._l4_by_l3.values()),
                class_level,
            )
        except Exception as e:
            log.error("Ошибка загрузки скелета: %s", e)

    def _index_skills(self, skills: List[Dict]) -> None:
        """Строит рабочие индексы из flat-списка навыков."""
        self._l2 = [s for s in skills if s["level"] == "L2"]
        self._l3 = [s for s in skills if s["level"] == "L3"]
        self._l4_by_l3 = {}
        for s in skills:
            if s["level"] == "L4":
                self._l4_by_l3.setdefault(s["parent_id"], []).append(s)
        self._valid_skill_ids = {
            s["id"] for s in skills if s["level"] == "L4"
        }

    # ── Two-step mapping ─────────────────────────────────────────────────

    def map_task(self, task: ExtractedTask) -> ExtractedTask:
        """Иерархический маппинг: сначала L3, затем L4."""
        if not self._valid_skill_ids:
            log.warning("Скелет навыков не загружен, пропуск маппинга")
            return task

        # ── Шаг 1: выбираем L3-подтему ───────────────────────────────
        l3_id = self._pick_l3(task)
        if not l3_id:
            log.warning("Task %s: не удалось определить L3, маппинг пропущен", task.temp_id)
            return task

        # ── Шаг 2: выбираем L4-навык из кандидатов под L3 ───────────
        l4_candidates = self._l4_by_l3.get(l3_id, [])
        if not l4_candidates:
            log.warning("Task %s: у L3=%s нет L4-дочерей", task.temp_id, l3_id)
            return task

        if len(l4_candidates) == 1:
            # Единственный вариант — берём без LLM
            self._assign(task, l4_candidates[0]["id"], 0.95, "single_l4_candidate", l3_id)
            return task

        self._pick_l4(task, l3_id, l4_candidates)
        return task

    def _pick_l3(self, task: ExtractedTask) -> Optional[str]:
        """Шаг 1: Pro выбирает L3 из иерархии L2→L3 (57 узлов)."""
        # Строим компактный список: сначала L2 с их L3-детьми
        lines = []
        l3_by_parent: Dict[str, List[Dict]] = {}
        for l3 in self._l3:
            l3_by_parent.setdefault(l3["parent_id"], []).append(l3)

        for l2 in self._l2:
            lines.append(f"[ТЕМА] {l2['id']}: {l2['name_ru']}")
            for l3 in l3_by_parent.get(l2["id"], []):
                lines.append(f"  [ПОДТЕМА] {l3['id']}: {l3['name_ru']}")
        hierarchy_text = "\n".join(lines)

        prompt = (
            f"Ты — эксперт по математике {self._class_level}-го класса.\n\n"
            "Задача:\n"
            f"  Параграф: §{task.paragraph_number} «{task.paragraph_title}»\n"
            f"  Текст: {task.question_text}\n"
            f"  LaTeX: {task.question_latex}\n\n"
            "Иерархия тем и подтем:\n"
            f"{hierarchy_text}\n\n"
            "Определи ОДНУ подтему [ПОДТЕМА], которой принадлежит задача.\n"
            'Верни JSON: {"l3_id": "...", "confidence": 0.95, "reasoning": "..."}\n'
            "Только JSON."
        )
        try:
            raw = call_deepseek(
                prompt,
                api_key=self.api_key,
                model=self.model,
                temperature=0.0,
                max_tokens=512,
                thinking_budget=0,
            )
            data = parse_json_response(raw)
            if not isinstance(data, dict):
                return None
            l3_id = data.get("l3_id", "")
            # Validate: must be a known L3
            known_l3_ids = {l3["id"] for l3 in self._l3}
            if l3_id not in known_l3_ids:
                log.warning("Task %s: Pro вернул неизвестный L3=%s", task.temp_id, l3_id)
                return None
            conf = float(data.get("confidence", 0.0))
            if conf < MIN_MAPPING_CONFIDENCE:
                log.info(
                    "Task %s: L3=%s conf=%.2f < %.2f — маппинг пропущен",
                    task.temp_id, l3_id, conf, MIN_MAPPING_CONFIDENCE,
                )
                return None
            log.debug(
                "Task %s: L3=%s conf=%.2f reason=%s",
                task.temp_id, l3_id, conf, str(data.get("reasoning", ""))[:80],
            )
            return l3_id
        except Exception as e:
            log.warning("Mapper step1 error (%s): %s", task.temp_id, e)
            return None

    def _pick_l4(self, task: ExtractedTask, l3_id: str, candidates: List[Dict]) -> None:
        """Шаг 2: Pro выбирает L4 из 2-4 кандидатов."""
        l3_name = next((l3["name_ru"] for l3 in self._l3 if l3["id"] == l3_id), l3_id)

        # Строим список кандидатов с описаниями
        cand_lines = []
        for c in candidates:
            desc = f" — {c['description']}" if c.get("description") else ""
            cand_lines.append(f"  {c['id']}: {c['name_ru']}{desc}")
        cand_text = "\n".join(cand_lines)

        prompt = (
            f"Ты — эксперт по математике {self._class_level}-го класса.\n\n"
            "Задача:\n"
            f"  Параграф: §{task.paragraph_number} «{task.paragraph_title}»\n"
            f"  Текст: {task.question_text}\n"
            f"  LaTeX: {task.question_latex}\n"
            f"  Сложность: {task.difficulty}\n\n"
            f"Подтема уже определена: «{l3_name}»\n\n"
            f"Конкретные навыки в этой подтеме:\n{cand_text}\n\n"
            "Выбери ОДИН навык, которому соответствует задача.\n"
            'Верни JSON: {"skill_id": "...", "confidence": 0.97, "reasoning": "..."}\n'
            "Только JSON."
        )
        try:
            raw = call_deepseek(
                prompt,
                api_key=self.api_key,
                model=self.model,
                temperature=0.0,
                max_tokens=512,
                thinking_budget=0,
            )
            data = parse_json_response(raw)
            if not isinstance(data, dict):
                return
            sid = data.get("skill_id", "") or None
            conf = float(data.get("confidence", 0.0))

            # Validate: must be one of the candidates
            valid_ids = {c["id"] for c in candidates}
            if sid and sid not in valid_ids:
                log.warning(
                    "Task %s: Pro вернул skill_id=%s не из кандидатов %s",
                    task.temp_id, sid, valid_ids,
                )
                sid = None

            if sid:
                self._assign(task, sid, conf, str(data.get("reasoning", ""))[:200], l3_id)
            else:
                log.warning("Task %s: шаг 2 не дал skill_id", task.temp_id)
        except Exception as e:
            log.warning("Mapper step2 error (%s): %s", task.temp_id, e)

    def _assign(
        self,
        task: ExtractedTask,
        skill_id: str,
        confidence: float,
        reasoning: str,
        l3_id: str,
    ) -> None:
        """Записывает skill_id только при confidence >= MIN_MAPPING_CONFIDENCE."""
        task.tags["mapping_l3"] = l3_id
        task.tags["mapping_reasoning"] = reasoning
        if confidence < MIN_MAPPING_CONFIDENCE:
            task.tags["mapping_confidence"] = round(confidence, 3)
            task.tags["mapping_rejected_skill"] = skill_id
            log.info(
                "Task %s: conf=%.2f < %.2f — skill_id не назначен (кандидат %s)",
                task.temp_id, confidence, MIN_MAPPING_CONFIDENCE, skill_id,
            )
            return
        task.skill_id = skill_id
        task.mapping_confidence = confidence
        task.tags["mapping_confidence"] = round(confidence, 3)
        log.debug("Task %s: mapped → %s (conf=%.2f)", task.temp_id, skill_id, confidence)

    # ── Batch ────────────────────────────────────────────────────────────

    def map_batch(self, tasks: List[ExtractedTask]) -> List[ExtractedTask]:
        return [self.map_task(t) for t in tasks]
