# Content scripts — operational runbook

Скрипты запускаются **внутри `content-worker`** (или локально с `DATABASE_URL`):

```bash
docker cp scripts/<script>.py content-worker:/app/scripts/
docker exec content-worker python3 /app/scripts/<script>.py [args]
```

Бэкап БД заданий:

```bash
./algo-infrastructure/scripts/backup_algo_content.sh
```

---

## Структура

```
scripts/
├── README.md                 ← этот файл
├── grade_status.py           ← дашборд по классу
├── audit_grade.py            ← failed + dist gaps
├── grade_quality_cleanup.py  ← compound / OCR repair
├── backfill_latex.py         ← LaTeX вопросов/ответов/дистракторов
├── run_smart_verify.py       ← основной verify + distractors
├── finish_g7.py / finish_g8.py
├── split_compound_tasks.py
├── ingest_textbook.py          ← PDF → пайплайн
├── gap_fill_makarychev7.py     ← G7 ingestion
├── gap_fill_algebra7.py
├── archive/g8/                 ← одноразовые G8-фиксы (не трогать)
└── archive/dev/                ← отладочные _*.py
```

Обёртки для совместимости: `backfill_g8_latex.py`, `audit_g8_failures.py`, `g8_quality_cleanup.py` → делегируют в общие скрипты.

---

## Workflow по классу

### 1. Статус

```bash
python3 scripts/grade_status.py --class-level 8
python3 scripts/grade_status.py --class-level 7
```

### 2. Аудит проблем

```bash
python3 scripts/audit_grade.py --class-level 7
```

### 3. Smart Verify (основной путь)

```bash
python3 scripts/run_smart_verify.py --class-level 7 --limit 100
```

### 4. Качество контента

```bash
python3 scripts/grade_quality_cleanup.py --class-level 7 --dry-run
python3 scripts/grade_quality_cleanup.py --class-level 7 --steps 1,2
```

### 5. LaTeX (после правок контента)

```bash
python3 scripts/backfill_latex.py --class-level 7 --dry-run
python3 scripts/backfill_latex.py --class-level 7
```

### 6. Добивка (fallback после Smart Verify)

```bash
python3 scripts/finish_g7.py
```

---

## G8 — закрыт ✅

| Критерий | Статус |
|----------|--------|
| Verified | 3796/3796 |
| Дистракторы ≥2 | 3796/3796 |
| LaTeX question | 100% |
| LaTeX answers | ~99% |
| `generated_from_scratch` | 0 |
| Бэкап | `backups/algo_content/algo_content_20260622_203553.dump` |

Детали: `docs/GRADES_STATUS.md`

---

## G7 — следующий этап

| Скрипт | Назначение |
|--------|------------|
| `gap_fill_makarychev7.py` | Дозагрузка TB Makarychev 7 |
| `gap_fill_algebra7.py` | Дозагрузка ALG 7 |
| `insert_toc_makarychev7.py` | TOC TB |
| `insert_toc_algebra7.py` | TOC ALG |
| `finish_g7.py` | Ответы + дистракторы + skill map |
| `fix_skills_g7_g8.py` | Skill mapping |

Порядок: **ingest → smart_verify → grade_quality_cleanup → backfill_latex → finish_g7 → grade_status**

---

## Ingestion (новый учебник)

```bash
python3 scripts/ingest_textbook.py ...
python3 scripts/insert_toc_*.py
python3 scripts/digitize_qa.py
python3 scripts/run_post_processing_all.py
```

---

## Правила

1. **Одноразовые фиксы** → `archive/g8/`, не копить в корне `scripts/`
2. **Перед массовым UPDATE** → `--dry-run`, потом бэкап
3. **LaTeX** → только `backfill_latex.py`, не ручные SQL
4. **Verify** → `run_smart_verify.py`, не старые chain-скрипты
5. **Дистракторы** → pipeline (`distractor_gate`), не массовый `input_mode=mcq` в tags
