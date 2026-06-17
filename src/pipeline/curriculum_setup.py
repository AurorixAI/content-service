"""
Content Service — Curriculum Setup Orchestrator

Полный пайплайн инициализации curriculum для одного class_level:

  1. Загрузить всё дерево L1→L4 из knowledge_hierarchy
  2. Для каждого L2-кластера → CurriculumAnalyzer.analyze_cluster()
  3. Применить importances → UPDATE knowledge_hierarchy
  4. Применить prerequisites → INSERT skill_prerequisites
  5. Сохранить прогресс в Redis (по кластерам)

Cross-grade:
  При анализе класса N передаём L4-навыки из классов 5..N-1
  чтобы LLM мог создать межклассовые зависимости.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.core.job_state import JobStateManager, PipelineStep
from src.pipeline.curriculum_analyzer import (
    ClusterAnalysisResult,
    CurriculumAnalyzer,
    ImportanceResult,
    PrerequisiteEdge,
    SkillNode,
)

log = logging.getLogger(__name__)


def _engine():
    return create_engine(get_settings().database_url)


class CurriculumSetupOrchestrator:
    """
    Запускает LLM-анализ и заполняет:
      - knowledge_hierarchy.importance
      - knowledge_hierarchy.cognitive_type
      - skill_prerequisites (весь граф)

    Args:
        job_id: для отчётности в Redis (тот же JobStateManager)
        class_level: анализируемый класс (5-11)
        dry_run: если True — только логируем, не пишем в БД
    """

    def __init__(self, job_id: str, class_level: int, dry_run: bool = False) -> None:
        self.job_id = job_id
        self.class_level = class_level
        self.dry_run = dry_run
        self.state = JobStateManager()
        self.analyzer = CurriculumAnalyzer()
        self._engine = _engine()

    def run(self) -> dict:
        """
        Полный прогон. Возвращает:
          { clusters_done, importances_updated, prerequisites_inserted, errors }
        """
        log.info("[%s] Curriculum setup: class=%d dry_run=%s",
                 self.job_id, self.class_level, self.dry_run)

        # 1. Загрузить дерево
        tree = self._load_tree()
        l2_clusters = tree["l2"]
        log.info("[%s] Loaded %d L2 clusters", self.job_id, len(l2_clusters))

        self.state.set_paragraphs_total(self.job_id, len(l2_clusters))

        # 2. L4 из предыдущих классов для cross-grade
        prev_l4 = self._load_prev_grade_l4()
        log.info("[%s] Cross-grade pool: %d L4 skills", self.job_id, len(prev_l4))

        stats = {
            "clusters_done": 0,
            "importances_updated": 0,
            "prerequisites_inserted": 0,
            "errors": [],
        }

        # 3. Обрабатываем кластер за кластером
        for cluster in l2_clusters:
            l3_children = [n for n in tree["l3"] if n.parent_id == cluster.id]
            l4_children = [n for n in tree["l4"] if self._in_cluster(n, l3_children)]

            if not l4_children:
                log.warning("[%s] Cluster %s has no L4 skills, skip", self.job_id, cluster.id)
                self.state.increment_paragraph(self.job_id, 0)
                continue

            log.info(
                "[%s] Analyzing cluster %s (%s): %d L3, %d L4",
                self.job_id, cluster.id, cluster.name_ru,
                len(l3_children), len(l4_children),
            )

            result = self.analyzer.analyze_cluster(
                cluster=cluster,
                children_l3=l3_children,
                children_l4=l4_children,
                all_l4_prev_grades=prev_l4,
            )

            if result.error:
                stats["errors"].append({"cluster": cluster.id, "error": result.error})
                self.state.increment_paragraph(self.job_id, 0)
                continue

            # 4. Применяем результаты
            imp_count = self._apply_importances(result.importances)
            pre_count = self._apply_prerequisites(result.prerequisites)

            stats["importances_updated"] += imp_count
            stats["prerequisites_inserted"] += pre_count
            stats["clusters_done"] += 1
            self.state.increment_paragraph(self.job_id, len(l4_children))

            log.info(
                "[%s] Cluster %s done: +%d importances, +%d prereqs",
                self.job_id, cluster.id, imp_count, pre_count,
            )

        log.info(
            "[%s] Curriculum setup complete: %s",
            self.job_id, stats,
        )
        return stats

    # ── Data loading ──────────────────────────────────────────────────────

    def _load_tree(self) -> Dict[str, List[SkillNode]]:
        """Load L1/L2/L3/L4 for this class_level with full methodology fields."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, level, parent_id, name_ru, description,
                           class_level_start, class_level_end,
                           importance, cognitive_type,
                           example_task, assessed_ability, difficulty_level, formula
                    FROM knowledge_hierarchy
                    WHERE class_level_start <= :cl
                      AND class_level_end >= :cl
                      AND is_active = TRUE
                    ORDER BY level, sequence_order
                """),
                {"cl": self.class_level},
            ).fetchall()

        nodes = [
            SkillNode(
                id=r[0], level=r[1], parent_id=r[2] or "",
                name_ru=r[3], description=r[4] or "",
                class_level_start=r[5] or self.class_level,
                class_level_end=r[6] or self.class_level,
                current_importance=r[7] or 5,
                cognitive_type=r[8] or "",
                example_task=r[9] or "",
                assessed_ability=r[10] or "",
                difficulty_level=r[11] or "",
                formula=r[12] or "",
            )
            for r in rows
        ]

        return {
            "l1": [n for n in nodes if n.level == "L1"],
            "l2": [n for n in nodes if n.level == "L2"],
            "l3": [n for n in nodes if n.level == "L3"],
            "l4": [n for n in nodes if n.level == "L4"],
        }

    def _load_prev_grade_l4(self) -> List[SkillNode]:
        """Load L4 skills from grades < class_level (for cross-grade prereqs)."""
        if self.class_level <= 5:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, level, parent_id, name_ru, description,
                           class_level_start, class_level_end,
                           importance, cognitive_type,
                           example_task, assessed_ability, difficulty_level, formula
                    FROM knowledge_hierarchy
                    WHERE level = 'L4'
                      AND class_level_end < :cl
                      AND is_active = TRUE
                    ORDER BY class_level_end DESC, sequence_order
                    LIMIT 60
                """),
                {"cl": self.class_level},
            ).fetchall()
        return [
            SkillNode(
                id=r[0], level=r[1], parent_id=r[2] or "",
                name_ru=r[3], description=r[4] or "",
                class_level_start=r[5] or 5,
                class_level_end=r[6] or 5,
                current_importance=r[7] or 5,
                cognitive_type=r[8] or "",
                example_task=r[9] or "",
                assessed_ability=r[10] or "",
                difficulty_level=r[11] or "",
                formula=r[12] or "",
            )
            for r in rows
        ]

    # ── Apply results ─────────────────────────────────────────────────────

    def _apply_importances(self, items: List[ImportanceResult]) -> int:
        if self.dry_run or not items:
            for i in items:
                log.info("[DRY] UPDATE %s → importance=%d ctype=%s", i.node_id, i.importance, i.cognitive_type)
            return len(items)

        count = 0
        with self._engine.begin() as conn:
            for item in items:
                result = conn.execute(
                    text("""
                        UPDATE knowledge_hierarchy
                        SET importance = :imp,
                            cognitive_type = :ctype,
                            updated_at = NOW()
                        WHERE id = :nid
                          AND is_active = TRUE
                    """),
                    {
                        "imp": item.importance,
                        "ctype": item.cognitive_type,
                        "nid": item.node_id,
                    },
                )
                if result.rowcount > 0:
                    count += 1
                else:
                    log.warning("importance UPDATE: node %s not found", item.node_id)
        return count

    def _apply_prerequisites(self, edges: List[PrerequisiteEdge]) -> int:
        if not edges:
            return 0
        if self.dry_run:
            for e in edges:
                log.info(
                    "[DRY] INSERT prereq %s → %s (%s w=%.2f crit=%d)",
                    e.skill_id, e.prerequisite_id, e.dependency_type, e.weight, e.criticality,
                )
            return len(edges)

        count = 0
        with self._engine.begin() as conn:
            for edge in edges:
                # Verify both nodes exist before inserting
                exists = conn.execute(
                    text("""
                        SELECT COUNT(*) FROM knowledge_hierarchy
                        WHERE id IN (:a, :b) AND is_active = TRUE
                    """),
                    {"a": edge.skill_id, "b": edge.prerequisite_id},
                ).scalar()

                if exists < 2:
                    log.warning(
                        "Prereq skipped: one or both nodes not found (%s → %s)",
                        edge.skill_id, edge.prerequisite_id,
                    )
                    continue

                conn.execute(
                    text("""
                        INSERT INTO skill_prerequisites (
                            skill_id, prerequisite_id,
                            dependency_type, criticality, weight,
                            relationship_description,
                            confidence, discovery_source,
                            created_at
                        )
                        VALUES (
                            :skill_id, :prereq_id,
                            :dep_type, :criticality, :weight,
                            :description,
                            0.85, 'ml',
                            NOW()
                        )
                        ON CONFLICT (skill_id, prerequisite_id) DO UPDATE SET
                            dependency_type          = EXCLUDED.dependency_type,
                            criticality              = EXCLUDED.criticality,
                            weight                   = EXCLUDED.weight,
                            relationship_description = EXCLUDED.relationship_description,
                            confidence               = EXCLUDED.confidence,
                            discovery_source         = 'ml'
                    """),
                    {
                        "skill_id": edge.skill_id,
                        "prereq_id": edge.prerequisite_id,
                        "dep_type": edge.dependency_type,
                        "criticality": edge.criticality,
                        "weight": float(edge.weight),
                        "description": edge.relationship_description,
                    },
                )
                count += 1
        return count

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _in_cluster(l4_node: SkillNode, l3_children: List[SkillNode]) -> bool:
        """Check if an L4 node belongs to any of these L3 subtopics."""
        l3_ids = {n.id for n in l3_children}
        return l4_node.parent_id in l3_ids
