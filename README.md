# ReconStream

High-volume bank reconciliation engine with PostgreSQL-native fuzzy matching.

Built with **Django 5.2**, **Django Ninja**, **PostgreSQL** (pg_trgm), **Celery**, and **Redis**.

---

## Quick Start

```bash
# 1. Clone and configure
git clone <repo-url> && cd recon-stream
cp .env.example .env          # Edit secrets if needed

# 2. Start all services (DB, Redis, web, Celery worker)
make up                        # docker-compose up -d --build

# 3. Open Swagger UI
open http://localhost:8000/api/docs
```

The full stack (Postgres, Redis, Django, Celery worker) starts in under 60 seconds.

## Architecture

```
┌──────────────┐     HTTP      ┌─────────────────────────────────┐
│  Swagger UI  │──────────────▶│  Django + Ninja API             │
│  / curl      │               │  • CSV upload (ingestion)       │
└──────────────┘               │  • POST /reconcile (async)      │
                               │  • GET /results, /stats         │
                               │  • Idempotency middleware       │
                               │  • Request-ID middleware        │
                               └────────┬──────────┬─────────────┘
                                        │          │
                          transaction.  │          │  Celery task
                          on_commit     │          │  dispatch
                                        ▼          ▼
                               ┌──────────────┐  ┌──────────────┐
                               │ PostgreSQL 15 │  │  Redis 7     │
                               │ • 4 models    │  │  • Broker    │
                               │ • pg_trgm     │  │  • Backend   │
                               │ • GIN indexes │  │  • Idem keys │
                               └──────────────┘  └──────┬───────┘
                                        ▲                │
                                        │                ▼
                                        │         ┌──────────────┐
                                        └─────────│ Celery Worker│
                                                  │ • Matcher    │
                                                  │ • Retry (3x) │
                                                  └──────────────┘
```

See [`docs/architecture.mermaid`](docs/architecture.mermaid) for a detailed Mermaid diagram.

## How It Works

### Two-Pass Matching Engine

1. **Exact Pass** — SQL-native join on `(amount, date, reference)`. No Python iteration for candidate discovery; a `Subquery` annotation finds the first unmatched GL entry per bank transaction.

2. **Fuzzy Pass** — For remaining unmatched rows, candidates are narrowed by amount tolerance (±$0.10) and date window (±5 days), then ranked by `pg_trgm` trigram similarity on the description field. Best match above the 0.3 threshold is selected.

Both passes use `SELECT ... FOR UPDATE (SKIP LOCKED)` to prevent double-matching under concurrency.

### Concurrency Safety

- **Row-level locking**: `select_for_update(skip_locked=True)` on GL entries prevents two concurrent workers from matching the same row.
- **Integrity guard**: `MatchResult` uses `OneToOneField` on both `bank_transaction` and `gl_entry`, so duplicate matches fail at the DB constraint level. `IntegrityError` is caught and skipped.
- **Idempotent task**: If a job is already `COMPLETED`, the Celery task returns early.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/recon/upload/bank-transactions/` | Upload bank CSV, creates a new job |
| `POST` | `/api/recon/upload/gl-entries/{job_id}/` | Upload GL CSV for an existing job |
| `POST` | `/api/recon/reconcile/{job_id}/` | Trigger async matching (202) |
| `GET`  | `/api/recon/results/{job_id}/` | Paginated match results |
| `GET`  | `/api/recon/stats/{job_id}/` | Aggregated job statistics |
| `GET`  | `/healthz/` | Health check (DB + Redis) |

## Development

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for local linting only)

### Make Targets

```bash
make up             # Start all services
make down           # Stop all services
make test           # Run pytest in the web container
make lint           # Run ruff + mypy
make migrate        # Apply migrations
make makemigrations # Generate new migrations
make shell          # Django shell
make logs           # Tail container logs
make seed           # Load sample data
```

### Running Tests

```bash
# Full suite (unit + integration + property-based + concurrency)
make test

# Specific test module
docker-compose exec web pytest src/ -k test_matching -v

# Property-based tests only
docker-compose exec web pytest src/ -k test_properties -v
```

### Project Layout

```
recon-stream/
├── src/
│   ├── config/              # Django settings, URLs, Celery, WSGI
│   ├── core/                # Shared: TimeStampedModel, health, middleware, logging
│   │   ├── middleware/
│   │   │   ├── idempotency.py   # Idempotency-Key header support
│   │   │   └── request_id.py    # X-Request-ID propagation
│   │   └── logging.py          # structlog config (JSON prod / console dev)
│   ├── reconciliation/
│   │   ├── models.py            # ReconciliationJob, BankTransaction, GLEntry, MatchResult
│   │   ├── schemas.py           # Pydantic DTOs
│   │   ├── api.py               # Django Ninja router
│   │   ├── tasks.py             # Celery tasks
│   │   ├── services/
│   │   │   ├── ingestion.py     # CSV parsing + bulk insert
│   │   │   └── matcher.py       # Two-pass matching engine
│   │   └── tests/
│   │       ├── factories.py     # Factory Boy factories
│   │       ├── test_matching.py # Unit + freezegun boundary tests
│   │       ├── test_properties.py # Hypothesis property-based tests
│   │       ├── test_ingestion.py
│   │       ├── test_concurrency.py
│   │       ├── test_idempotency.py
│   │       └── test_query_count.py
│   └── conftest.py
├── docs/
│   └── architecture.mermaid
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
└── .env.example
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Web framework | Django 5.2 LTS | ORM, migrations, middleware |
| API layer | Django Ninja 1.5 | OpenAPI schema, async-ready |
| Database | PostgreSQL 15 | ACID, pg_trgm fuzzy matching |
| Task queue | Celery 5.4 | Async reconciliation jobs |
| Broker/cache | Redis 7 | Task broker, result backend, idempotency |
| Logging | structlog | Structured JSON (prod) / colored console (dev) |
| Validation | Pydantic 2.10 | CSV row validation |
| Testing | pytest, Hypothesis, freezegun | Unit, property-based, date boundary |
| Linting | ruff, mypy (strict) | Code quality, type safety |

## License

MIT
