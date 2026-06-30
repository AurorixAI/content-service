# G8 one-off fix scripts (archived)

Применены в июне 2026 при доводке 8 класса до production-ready.
**Не запускать повторно** — только для истории и reference.

| Скрипт | Что делал |
|--------|-----------|
| `fix_g8_accuracy_step1.py` | Исправление accuracy (SymPy, сравнения) |
| `fix_g8_compound_tails.py` | Обрезка хвостов compound OCR |
| `fix_g8_expression_exact_number.py` | expression → exact_number |
| `fix_g8_stale_tags.py` | Очистка устаревших тегов |
| `fix_g8_dist_gaps.py` | Дистракторы для 70 text-заданий |
| `fix_tb_scratch_step1/2.py` | Scratch TB + promoted from_scratch |
| `fix_alg_step1.py` | ALG accuracy fixes |
| `fix_tb_group_*.py` | Пакетные фиксы по группам review |
| `fix_tb_human_review_*.py` | Human review queue |
| `fix_tb_failed_step1.py` | Failed verify retry batch |
| `beautify_g8_scratch.py` | Форматирование scratch-ответов |
| `backfill_tb_latex.py` | → заменён на `backfill_latex.py` |
| `backfill_alg_latex.py` | → заменён на `backfill_latex.py` |
| `revert_blind_corrections.py` | Откат слепых правок |
| `chain_g8_sympy_loop.sh` | SymPy batch loop |

Актуальные инструменты — в `scripts/README.md`.
