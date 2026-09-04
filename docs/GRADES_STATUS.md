# Статус классов (content DB)

База: `algo_content` @ `content-postgres`

Обновить метрики:

```bash
docker exec content-worker python3 /app/scripts/grade_status.py --class-level 8
docker exec content-worker python3 /app/scripts/grade_status.py --class-level 7
```

---

## G8 — DONE ✅

Закрыт: **июнь 2026**

| Метрика | Значение |
|---------|----------|
| Заданий (G8_*) | 3 796 |
| `verification_status=verified` | 3 796 |
| Дистракторы ≥2 | 3 796 |
| `question_latex` | 3 796 |
| `correct_answer_latex` | ~3 738 |
| `value_latex` (все dist) | ~3 768 |
| `generated_from_scratch` | 0 |
| `smart_verify_error` (активные) | 0 |

Источники: Makarychev TB (2 436) + School ALG (1 360).

### Бэкап (verified restore)

```
backups/algo_content/algo_content_20260622_203553.dump
SHA256: 54762714ad8c988e89726ccee169d6e40bb4c393a45e23ea9f9b0887953e9e9f
```

### Что сделано

- Accuracy fixes (SymPy, comparisons, OCR)
- 70 distractor gaps (templates + LLM)
- LaTeX backfill (вопросы, ответы, дистракторы)
- Coordinate → MCQ в diagnostic
- Compound tails, stale tags cleanup

### Архив скриптов

`scripts/archive/g8/` — 21 одноразовый скрипт

---

## G7 — IN PROGRESS

Следующий класс. Operational скрипты:

1. `gap_fill_makarychev7.py` / `gap_fill_algebra7.py`
2. `run_smart_verify.py --class-level 7`
3. `grade_quality_cleanup.py --class-level 7`
4. `backfill_latex.py --class-level 7`
5. `finish_g7.py`
6. `grade_status.py --class-level 7` → цель: как G8

---

## Curriculum tables (та же БД)

| Таблица | Назначение |
|---------|------------|
| `knowledge_hierarchy` | L1–L4 навыки (~1 374) |
| `skill_prerequisites` | Граф пререквизитов (~589) |
| `textbook_skill_map` | Параграф → skill (пока пусто) |
| `tasks_master` | Банк заданий |
| `textbook_tasks` | Связь задание ↔ учебник |

Diagnostic-service читает `knowledge_hierarchy` + `tasks_master` из `algo_content` (read-only).

---

## Definition of Done (любой класс)

### Полнота банка

- [ ] `grade_status`: verified = total
- [ ] dist ≥2 для всех non-prose MCQ-кандидатов
- [ ] LaTeX: question 100%, answers/dist >95%
- [ ] `audit_grade`: failed = 0, dist_gaps = 0
- [ ] Бэкап `backup_algo_content.sh` + verify restore
- [ ] Одноразовые fix-скрипты → `archive/`

### Качество оцифровки (добавлено в С6)

Полнота отвечает на вопрос «все ли задачи на месте», качество — «можно ли их
давать ученику». До С1 второй вопрос не измерялся вообще, и `verified = total`
означало только, что колонки заполнены. Цифры — из `EVAL.md`
(`python3 scripts/eval.py --class-level N`).

- [ ] `compile_rate` ≥ 0.999 — формулы физически рендерятся KaTeX
- [ ] Лексических артефактов LaTeX = 0 (`scripts/audit_latex_compile.py`).
      **`compile_rate = 1.0` этого не гарантирует:** `x \\cdot y` и `rac{1}{2}`
      компилируются без ошибки и показывают ученику мусор
- [ ] `needs_review` — единицы процентов, не десятки. Десятки означают либо
      реальный обвал распознавания, либо что в очередь затесался сигнал
      полноты вместо сигнала качества (так было до С5, см. `EVAL.md`)
- [ ] `answer_coverage` измерен и записан. Низкий — не дефект сам по себе, но
      он говорит, какая доля ответов **придумана моделью**, а не взята из книги
- [ ] `task_recall` и `latex_ned` посчитаны против вручную вычитанного golden
      (`src/eval/golden/README.md`). Без golden эти две метрики недоступны —
      система не может проверить себя собой
- [ ] Строка с цифрами дописана в `EVAL.md`
