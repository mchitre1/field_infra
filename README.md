# Infrastructure Intelligence Engine (IIE)

Backend services for converting visual inspection media (drone, mobile, fixed camera) into maintenance intelligence. See [docs/PRODUCT_BRIEF.md](docs/PRODUCT_BRIEF.md) for the full product picture.

## Implemented today

The **ingestion vertical slice** is implemented under `backend/`: multipart uploads and presigned S3 uploads persist inspection metadata in PostgreSQL, store bytes in S3, and enqueue processing jobs on Amazon SQS when configured.

API details, request examples, and configuration are in [docs/INGEST_API.md](docs/INGEST_API.md).

## Backend quick start

Prerequisites: Python 3.11+, PostgreSQL, and (for full flows) AWS credentials for S3/SQS.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
```

Set environment variables (see [docs/INGEST_API.md](docs/INGEST_API.md#configuration)), then apply migrations and run the API:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Health check: `GET http://127.0.0.1:8000/health`

OpenAPI schema: `http://127.0.0.1:8000/docs`

Tests:

```bash
cd backend
python -m pytest
```
