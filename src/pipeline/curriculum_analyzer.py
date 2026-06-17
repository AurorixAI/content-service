"""
Content Service — Curriculum Analyzer

Проблема:
  knowledge_hierarchy заполнен (L1-L4 навыки), но:
  - importance у всех = 5 (дефолт)
  - skill_prerequisites полностью пуста
  - без этих данных deep scan не запустится никогда

Решение:
  LLM-пайплайн анализирует каждый L2-кластер и для каждой L4-пары внутри него:
  1. Выставляет importance (1-10) для L2, L3, L4 узлов
  2. Определяет prerequisite рёбра (hard/soft, weight, criticality)
  3. Добавляет cross-grade зависимости (L4 из предыдущих классов)

Стратегия по батчам:
  Берём один L2-кластер за раз (~5-15 L4 навыков).
  Один запрос к Gemini Pro → получаем importance + prereqs для всего кластера.
  Это даёт контроль контекста и возможность retry по кластеру.

Выходные данные:
  - UPDATE knowledge_hierarchy SET importance=X WHERE id=...
  - INSERT INTO skill_prerequisites (skill_id, prereq_id, type, weight, criticality, ...)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.pipeline.gemini_client import call_gemini, get_pro_model, parse_json_response

log = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SkillNode:
    """Узел иерархии знаний, переданный в LLM."""
    id: str
    level: str           # L2 | L3 | L4
    name_ru: str
    description: str
    parent_id: str
    class_level_start: int
    class_level_end: int
    current_importance: int = 5
    cognitive_type: str = ""
    # Поля из методики (PDF Sardor Bozorov) — ключевой контекст для LLM
    example_task: str = ""        # пример задачи из учебника
    assessed_ability: str = ""    # что именно измеряется
    difficulty_level: str = ""    # Low (A) | Medium (B) | High (C)
    formula: str = ""             # формула/правило если есть


@dataclass
class ImportanceResult:
    node_id: str
    importance: int              # 1-10
    cognitive_type: str          # recall | apply | analyze | evaluate | create
    rationale: str


@dataclass
class PrerequisiteEdge:
    skill_id: str                # навык который ТРЕБУЕТ пререквизит
    prerequisite_id: str         # пририквизит
    dependency_type: str         # hard | soft
    weight: float                # 0.0-1.0
    criticality: int             # 1-10
    is_cross_grade: bool         # пред. класс
    relationship_description: str


@dataclass
class ClusterAnalysisResult:
    cluster_id: str              # L2 id
    importances: List[ImportanceResult] = field(default_factory=list)
    prerequisites: List[PrerequisiteEdge] = field(default_factory=list)
    error: Optional[str] = None


# ── Analyzer ──────────────────────────────────────────────────────────────────

class CurriculumAnalyzer:
    """
    Анализирует один L2-кластер и возвращает:
    - importance для L2, всех его L3 и L4
    - граф prereq-рёбер внутри и между классами
    """

    def analyze_cluster(
        self,
        cluster: SkillNode,               # L2 node
        children_l3: List[SkillNode],     # L3 subtopics
        children_l4: List[SkillNode],     # L4 atomic skills (all in this cluster)
        all_l4_prev_grades: List[SkillNode],  # L4 из классов ниже (для cross-grade)
    ) -> ClusterAnalysisResult:
        """Один вызов Gemini Pro → полный анализ кластера."""

        prompt = self._build_prompt(cluster, children_l3, children_l4, all_l4_prev_grades)

        try:
            raw = call_gemini(
                prompt,
                model=get_pro_model(),
                temperature=0.1,
                max_tokens=32768,
                json_mode=True,
                timeout=180,
            )
            data = parse_json_response(raw)
            return self._parse_response(cluster.id, data, children_l4)

        except Exception as exc:
            log.error("CurriculumAnalyzer failed for cluster %s: %s", cluster.id, exc)
            return ClusterAnalysisResult(cluster_id=cluster.id, error=str(exc))

    # ── Prompt ────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        cluster: SkillNode,
        l3_nodes: List[SkillNode],
        l4_nodes: List[SkillNode],
        prev_grade_l4: List[SkillNode],
    ) -> str:
        cluster_block = (
            f"КЛАСТЕР (L2): {cluster.id}\n"
            f"  Название: {cluster.name_ru}\n"
            f"  Описание: {cluster.description or '—'}\n"
            f"  Классы: {cluster.class_level_start}–{cluster.class_level_end}\n"
        )

        l3_block = "\n".join(
            f"  [{n.id}] {n.name_ru} (L3, класс {n.class_level_start}-{n.class_level_end})"
            for n in l3_nodes
        )

        def _l4_line(n: SkillNode) -> str:
            parts = [f"  [{n.id}] {n.name_ru}"]
            if n.description:
                parts.append(f"    Описание: {n.description}")
            if n.assessed_ability:
                parts.append(f"    Что измеряем: {n.assessed_ability}")
            if n.example_task:
                parts.append(f"    Пример из учебника: {n.example_task}")
            if n.difficulty_level:
                parts.append(f"    Сложность: {n.difficulty_level}")
            if n.formula:
                parts.append(f"    Формула/правило: {n.formula}")
            if n.cognitive_type:
                parts.append(f"    Тип (методика): {n.cognitive_type}")
            return "\n".join(parts)

        l4_block = "\n".join(_l4_line(n) for n in l4_nodes)

        prev_block = ""
        if prev_grade_l4:
            prev_block = (
                "\nНАВЫКИ ИЗ ПРЕДЫДУЩИХ КЛАССОВ (возможные cross-grade пререквизиты):\n"
                + "\n".join(
                    f"  [{n.id}] {n.name_ru}"
                    + (f" — {n.assessed_ability}" if n.assessed_ability else "")
                    + f" (класс {n.class_level_start}-{n.class_level_end})"
                    for n in prev_grade_l4
                )
            )

        return f"""Ты — эксперт по методике математического образования (программа Sardor Bozorov).
Анализируй кластер навыков строго на основе предоставленных данных из учебной программы.
Все зависимости должны отражать реальный методический порядок изучения тем, а не общие знания.

{cluster_block}

ПОДТЕМЫ (L3):
{l3_block}

НАВЫКИ (L4 — атомарные):
{l4_block}
{prev_block}

ЗАДАЧА 1 — IMPORTANCE (приоритет для диагностики):
Для КАЖДОГО узла (кластер L2, все L3, все L4) укажи:
- importance: 1-10 (10 = фундаментальный, без него всё сломается; 1 = факультативный)
  Правило: importance >= 8 ЗАПУСКАЕТ deep scan при провале. Ставь 8+ только критическим темам.
- cognitive_type: recall | apply | analyze | evaluate | create
- rationale: 1 предложение почему именно этот приоритет

ЗАДАЧА 2 — PREREQUISITES (граф зависимостей для deep scan):
Для каждой L4-пары где A требует B (ученик не может освоить A без B):
- skill_id: A (тот кто требует)
- prerequisite_id: B (то что нужно сначала)
- dependency_type: "hard" (нельзя без него) | "soft" (желательно)
- weight: 0.0-1.0 (сила зависимости)
- criticality: 1-10 (насколько критично для диагностики)
- is_cross_grade: true если пререквизит из другого класса
- relationship_description: 1 предложение что именно блокируется

ПРАВИЛА:
- Не придумывай зависимости — только математически обоснованные
- hard prereq: без него ученик физически не решит задачу (напр. умножение дробей → сложение дробей)
- soft prereq: помогает но можно обойтись (напр. упрощение выражений → раскрытие скобок)
- Не создавай циклы A→B→A
- Cross-grade: берёшь только из предоставленного списка предыдущих классов

ФОРМАТ ОТВЕТА (строгий JSON):
{{
  "importances": [
    {{"node_id": "G5_T06", "importance": 9, "cognitive_type": "apply", "rationale": "..."}},
    ...
  ],
  "prerequisites": [
    {{
      "skill_id": "G5_SK06_03",
      "prerequisite_id": "G5_SK06_01",
      "dependency_type": "hard",
      "weight": 0.9,
      "criticality": 8,
      "is_cross_grade": false,
      "relationship_description": "..."
    }},
    ...
  ]
}}

Только JSON, без комментариев.
"""

    # ── Parser ────────────────────────────────────────────────────────────

    def _parse_response(
        self,
        cluster_id: str,
        data: Any,
        l4_nodes: List[SkillNode],
    ) -> ClusterAnalysisResult:
        if not isinstance(data, dict):
            return ClusterAnalysisResult(
                cluster_id=cluster_id,
                error=f"Unexpected response type: {type(data)}",
            )

        valid_l4_ids = {n.id for n in l4_nodes}

        # Parse importances
        importances: List[ImportanceResult] = []
        for item in data.get("importances", []):
            try:
                imp = max(1, min(10, int(item["importance"])))
                ctype = item.get("cognitive_type", "apply")
                if ctype not in ("recall", "apply", "analyze", "evaluate", "create"):
                    ctype = "apply"
                importances.append(ImportanceResult(
                    node_id=item["node_id"],
                    importance=imp,
                    cognitive_type=ctype,
                    rationale=item.get("rationale", ""),
                ))
            except (KeyError, ValueError, TypeError) as exc:
                log.warning("Skip malformed importance item: %s — %s", item, exc)

        # Parse prerequisites
        prerequisites: List[PrerequisiteEdge] = []
        seen_pairs: set = set()
        for item in data.get("prerequisites", []):
            try:
                skill_id = item["skill_id"]
                prereq_id = item["prerequisite_id"]

                if skill_id == prereq_id:
                    continue  # self-loop
                pair = (skill_id, prereq_id)
                if pair in seen_pairs:
                    continue  # duplicate
                seen_pairs.add(pair)

                dep_type = item.get("dependency_type", "soft")
                if dep_type not in ("hard", "soft"):
                    dep_type = "soft"

                weight = float(item.get("weight", 0.7))
                weight = max(0.0, min(1.0, weight))

                criticality = max(1, min(10, int(item.get("criticality", 5))))

                prerequisites.append(PrerequisiteEdge(
                    skill_id=skill_id,
                    prerequisite_id=prereq_id,
                    dependency_type=dep_type,
                    weight=weight,
                    criticality=criticality,
                    is_cross_grade=bool(item.get("is_cross_grade", False)),
                    relationship_description=item.get("relationship_description", ""),
                ))
            except (KeyError, ValueError, TypeError) as exc:
                log.warning("Skip malformed prereq item: %s — %s", item, exc)

        log.info(
            "Cluster %s: %d importances, %d prerequisites",
            cluster_id, len(importances), len(prerequisites),
        )
        return ClusterAnalysisResult(
            cluster_id=cluster_id,
            importances=importances,
            prerequisites=prerequisites,
        )
