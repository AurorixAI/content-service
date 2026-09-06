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

from src.pipeline.deepseek_client import (
    call_deepseek,
    get_deepseek_key,
    get_deepseek_model,
    parse_json_response,
)
from src.pipeline.models import ExtractedTask
from src.pipeline.quality import thinking_budget, enrichment_max_tokens, enrichment_retry_max

log = logging.getLogger("pipeline")


class AIAnswerSolver:
    """Решает задачи без ответа через Gemini Flash — только для задач где answer_raw пустой."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or get_deepseek_key()

    def solve(self, task: ExtractedTask, figure_context: str = "") -> ExtractedTask:
        """Заполняет task.answer_raw если он пустой. Не трогает ничего больше."""
        if not task.question_text.strip():
            return task
        if task.answer_raw and task.answer_raw.strip() not in ("", "—", "-", "?", "..."):
            return task

        fig_block = f"\nРисунок к задаче:\n{figure_context.strip()}\n" if figure_context.strip() else ""
        prompt = self._build_prompt(task, fig_block)
        for attempt in range(enrichment_retry_max(missing_answer=True)):
            try:
                raw = call_deepseek(
                    prompt,
                    model=get_deepseek_model(),
                    api_key=self.api_key,
                    temperature=0.1,
                    max_tokens=enrichment_max_tokens(),
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

    def _build_prompt(self, task: ExtractedTask, fig_block: str = "") -> str:
        """Строит тип-специфичный промпт для максимальной точности решения."""
        at = task.answer_type or "exact_number"
        q = task.question_text
        q_latex = task.question_latex or q

        # Тип-специфичные инструкции для точности ответа
        type_hint = {
            "exact_number": (
                "Вычисли числовой ответ. Верни точное число, дробь или √-выражение. "
                "Без слов — только значение. Пример: \"12\" или \"-3/4\" или \"√5\"."
            ),
            "decimal": (
                "Вычисли ответ в десятичном виде. Верни число с запятой. Пример: \"1,75\"."
            ),
            "fraction": (
                "Вычисли ответ в виде обыкновенной дроби. Сократи до несократимой. "
                "Пример: \"7/12\" или \"-5/8\"."
            ),
            "expression": (
                "Упрости выражение и верни результат в алгебраическом виде. "
                "Пример: \"2x²+3x-1\" или \"(a+b)²\"."
            ),
            "equation_solution": (
                "Реши уравнение/систему. Верни все корни через \"; \". "
                "Пример: \"x=2; x=-3\" или \"x=1; y=4\"."
            ),
            "inequality": (
                "Реши неравенство. Верни ответ в виде промежутка. "
                "Пример: \"x > -2\" или \"x ∈ (-∞; 3)\"."
            ),
            "set": (
                "Найди все числа (или объекты) из условия, удовлетворяющие требованию. "
                "Перечисли их через \"; \" в том же виде, в каком они даны в задаче. "
                "Если подходящих нет — верни \"∅\". Пример: \"1,(5); 1,68\"."
            ),
            "multiple_choice": (
                "Определи единственный верный вариант из предложенных и верни его дословно. "
                "Например: \"Если a ∈ N, то a ∈ Z\"."
            ),
            "text": (
                "Сформулируй точный краткий ответ. "
                "Если задача открытая (много вариантов) — дай один конкретный пример ответа."
            ),
        }.get(at, "Реши задачу и верни точный финальный ответ.")

        return (
            "Ты — эксперт-математик. Реши задачу строго по условию.\n\n"
            f"Задача: {q}\n"
            f"LaTeX: {q_latex}\n"
            f"Тип ответа: {at}\n"
            f"Сложность: {task.difficulty}\n"
            f"{fig_block}\n"
            f"Инструкция: {type_hint}\n\n"
            "Верни JSON: {\"answer\": \"<точный ответ>\"}\n"
            "Только JSON, без объяснений."
        )



class AIDistractorGenerator:
    """
    Генерирует дистракторы для текстовых задач (open_text) через Gemini Pro.

    Используется для open_text и прочих типов, где нужна отдельная Gemini-генерация.
    Дистракторы всегда через Gemini; SymPy — только верификация ответов.

    Формат: [{value, error_type, explanation, plausibility}]
    Модель: Gemini Pro (точнее, надёжнее для педагогических задач)
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or get_deepseek_key()

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
            text = call_deepseek(
                prompt,
                model=get_deepseek_model(),
                api_key=self.api_key,
                temperature=0.3,
                max_tokens=2048,
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
