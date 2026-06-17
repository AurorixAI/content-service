"""
ALGO V1 — AI Enrichment Module
src/pipeline/enrichment.py

AIAnswerSolver  — решает задачи без ответа через Gemini Flash (только answer_raw).
AIDistractorGenerator — генерирует дистракторы для open_text через Gemini Pro.

solution_steps / hints не хранятся в БД — они будут генерироваться real-time
AI-тьютором при необходимости, персонализированно под ошибку ученика.
"""

import logging
from typing import List, Dict

from src.pipeline.gemini_client import (
    call_gemini,
    get_api_key,
    get_pro_model,
    get_flash_model,
    parse_json_response,
)
from src.pipeline.models import ExtractedTask
from src.pipeline.quality import thinking_budget, enrichment_max_tokens, enrichment_retry_max

log = logging.getLogger("pipeline")


class AIAnswerSolver:
    """Решает задачи без ответа через Gemini Flash — только для задач где answer_raw пустой."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or get_api_key()

    def solve(self, task: ExtractedTask, figure_context: str = "") -> ExtractedTask:
        """Заполняет task.answer_raw если он пустой. Не трогает ничего больше."""
        if not task.question_text.strip():
            return task
        if task.answer_raw and task.answer_raw.strip() not in ("", "—", "-", "?", "..."):
            return task

        fig_block = f"\nРисунок к задаче:\n{figure_context.strip()}\n" if figure_context.strip() else ""
        prompt = (
            "Ты — математический педагог. Реши задачу и верни только ответ.\n\n"
            f"Текст: {task.question_text}\nLaTeX: {task.question_latex}\n"
            f"Тип ответа: {task.answer_type}\nСложность: {task.difficulty}\n"
            f"{fig_block}\n"
            'Верни JSON: {"answer":"<окончательный ответ>"}\n\n'
            "answer — точный финальный ответ. Только JSON."
        )
        budget = thinking_budget("enrichment")
        for attempt in range(enrichment_retry_max(missing_answer=True)):
            try:
                raw = call_gemini(
                    prompt,
                    model=get_flash_model(),
                    api_key=self.api_key,
                    temperature=0.1,
                    max_tokens=enrichment_max_tokens(),
                    thinking_budget=budget,
                )
                data = parse_json_response(raw)
                if isinstance(data, dict):
                    ans = data.get("answer", "")
                    if isinstance(ans, (int, float)):
                        ans = str(ans)
                    if isinstance(ans, str) and ans.strip():
                        task.answer_raw = ans.strip()
                        return task
            except Exception as e:
                log.warning("AIAnswerSolver error (%s) attempt %d: %s", task.temp_id, attempt + 1, e)
        return task


class AIDistractorGenerator:
    """
    Генерирует дистракторы для текстовых задач (open_text) через Gemini Pro.

    Используется для open_text и прочих типов, где нужна отдельная Gemini-генерация.
    Дистракторы всегда через Gemini; SymPy — только верификация ответов.

    Формат: [{value, error_type, explanation, plausibility}]
    Модель: Gemini Pro (точнее, надёжнее для педагогических задач)
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or get_api_key()

    def generate(
        self,
        question_text: str,
        correct_answer: str,
        answer_type: str = "open_text",
        count: int = 3,
    ) -> List[Dict]:
        """
        Генерирует дистракторы через Gemini Pro.

        Returns:
            Список словарей: [{value, error_type, explanation, plausibility}]
            Пустой список при ошибке.
        """
        if not question_text or not correct_answer:
            return []

        prompt = (
            "Ты — эксперт по математической педагогике и типичным ошибкам учеников.\n\n"
            f"Задача: {question_text}\n"
            f"Правильный ответ: {correct_answer}\n"
            f"Тип ответа: {answer_type}\n\n"
            f"Сгенерируй {count} правдоподобных НЕПРАВИЛЬНЫХ ответа, которые реальный ученик "
            "мог бы дать. Каждый дистрактор должен отражать конкретную типичную ошибку.\n\n"
            "Верни JSON-массив (без обёрток):\n"
            "[{\n"
            '  "value": "неправильный ответ",\n'
            '  "error_type": "тип_ошибки",  // sign_error, calculation_error, '
            "conceptual_error, partial_answer, misread_problem, unit_error\n"
            '  "explanation": "Почему ученик мог так ответить (1 предложение)",\n'
            '  "plausibility": 0.85  // 0-1, насколько правдоподобен\n'
            "}]\n\n"
            "Правила:\n"
            "- Ответы должны быть РАЗНЫМИ (не дубликаты)\n"
            "- plausibility от 0.6 до 0.95\n"
            "- error_type из списка: sign_error, calculation_error, conceptual_error, "
            "partial_answer, misread_problem, unit_error, formula_error, "
            "simplification_error, rounding_error\n"
            "- Ответы должны быть ПОХОЖИ по формату на правильный\n"
            "- Только JSON-массив, без markdown"
        )

        try:
            text = call_gemini(
                prompt,
                model=get_pro_model(),
                api_key=self.api_key,
                temperature=0.4,
                max_tokens=8192,
                json_mode=True,
            )
            data = parse_json_response(text)

            if isinstance(data, list):
                return self._validate_distractors(data, correct_answer, count)
            elif isinstance(data, dict) and "distractors" in data:
                return self._validate_distractors(
                    data["distractors"], correct_answer, count
                )

        except Exception as e:
            log.warning("AIDistractorGenerator error: %s", e)

        return []

    def _validate_distractors(self, raw: list, correct: str, count: int) -> List[Dict]:
        """Валидирует и нормализует сырые дистракторы от Gemini."""
        results: List[Dict] = []
        seen = {correct.strip().lower()}

        valid_types = {
            "sign_error",
            "calculation_error",
            "conceptual_error",
            "partial_answer",
            "misread_problem",
            "unit_error",
            "formula_error",
            "simplification_error",
            "rounding_error",
            "unknown",
        }

        for item in raw:
            if not isinstance(item, dict):
                continue
            val = str(item.get("value", "")).strip()
            if not val or val.lower() in seen:
                continue

            etype = str(item.get("error_type", "unknown")).strip()
            if etype not in valid_types:
                etype = "unknown"

            plaus = item.get("plausibility", 0.7)
            if not isinstance(plaus, (int, float)):
                plaus = 0.7
            plaus = max(0.1, min(0.95, float(plaus)))

            expl = str(item.get("explanation", ""))

            seen.add(val.lower())
            results.append(
                {
                    "value": val,
                    "error_type": etype,
                    "explanation": expl,
                    "plausibility": plaus,
                }
            )

            if len(results) >= count:
                break

        return results
