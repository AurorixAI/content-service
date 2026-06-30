# content-service

«Мозг» платформы. Хранит учебный граф (предметы → темы → навыки), банк задач и управляет загрузкой учебников через AI-пайплайн (OCR + Gemini).

- **Port**: 8004
- **DB**: `algo_content` (PostgreSQL 15)
- **Queue**: Redis + ARQ (worker для пайплайна)
- **Framework**: FastAPI + SQLAlchemy Core (raw SQL) + Alembic
- **Main file**: `src/main.py`
- **Worker**: `src/worker/tasks.py` (ARQ)

## Переменные окружения

| Переменная | Обязательная | Описание | Пример |
|---|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL DSN | `postgresql://algo:pass@content-postgres:5432/algo_content` |
| `REDIS_URL` | ✅ | Redis DSN (ARQ queue) | `redis://content-redis:6379` |
| `GEMINI_API_KEY` | ✅ | Google Gemini (OCR + генерация задач) | `AIza...` |
| `APP_ENV` | — | `production` / `development` | `production` |
| `OCR_BACKEND` | — | `gemini` (default) или `mathpix` | `gemini` |
| `MATHPIX_APP_ID` | — | Mathpix credentials (если OCR_BACKEND=mathpix) | — |
| `MATHPIX_APP_KEY` | — | Mathpix credentials | — |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Путь к GCP service account key | `/run/secrets/gcp.json` |
| `TEXTBOOKS_DIR` | — | Папка с PDF учебниками | `./textbooks` |
| `WORKER_CONCURRENCY` | — | ARQ worker concurrency | `5` |
| `PIPELINE_CACHE_DIR` | — | Кэш пайплайна | `/tmp/content_pipeline_cache` |

## Как запустить

```bash
cp .env.example .env   # заполнить DATABASE_URL, REDIS_URL, GEMINI_API_KEY

# Запустить API + worker + PostgreSQL + Redis
docker compose up -d --build

# Миграции
docker exec content-api alembic upgrade head

# Prod
docker compose -f docker-compose.prod.yml up -d
```

## Read API (используется diagnostic и exam сервисами)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/v1/content/skills` | Навыки (фильтр по `?level=L4`) |
| GET | `/api/v1/content/skills/{id}` | Навык по ID |
| GET | `/api/v1/content/textbooks` | Список учебников |
| GET | `/api/v1/content/textbooks/{id}/topics` | Темы учебника |
| GET | `/api/v1/content/tasks` | Задания (фильтр по skill_id, difficulty) |
| POST | `/api/v1/content/tasks/batch` | Пакетный запрос заданий |
| GET | `/api/v1/health/live` | Liveness probe |
| GET | `/api/v1/health/ready` | Readiness probe (DB + Redis) |
| GET | `/metrics` | Prometheus метрики |

## Пайплайн загрузки учебника

```
PDF → OCR (Gemini/Mathpix) → структурирование тем → 
генерация задач (Gemini) → сохранение в БД
```

Запуск через ARQ worker (фоновая задача):
```bash
# Поставить в очередь через API
POST /api/v1/content/pipeline/start
{"textbook_id": 1, "pdf_path": "/textbooks/math10.pdf"}
```

Swagger UI (только `development`): http://localhost:8004/docs

## Схема БД

Основные таблицы в `algo_content`:

| Таблица | Описание |
|---------|----------|
| `knowledge_hierarchy` | L1–L4 навыки |
| `skill_prerequisites` | Пререквизиты навыков |
| `textbooks` / `textbook_toc` | Учебники и оглавление |
| `tasks_master` | Банк заданий (IRT, verify, distractors) |
| `textbook_tasks` | Связь заданий с учебником |

Статус классов и runbook скриптов: [`docs/GRADES_STATUS.md`](docs/GRADES_STATUS.md), [`scripts/README.md`](scripts/README.md).
