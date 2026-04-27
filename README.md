# Infrastructure Intelligence Engine (IIE)

Backend services for converting visual inspection media (drone, mobile, fixed camera) into maintenance intelligence. See [docs/PRODUCT_BRIEF.md](docs/PRODUCT_BRIEF.md) for the full product picture.

## Implemented today

The backend currently implements five connected slices under `backend/`:

- **Ingestion (feature 0001):** multipart and presigned uploads persist inspections, store source media in S3, and publish ingest jobs to SQS when configured.
- **Frame extraction (feature 0002):** a worker consumes ingest jobs, extracts frames from image/video media, stores frame JPEGs in S3, and persists frame-level metadata for downstream analysis.
- **Detection and classification (feature 0003):** the worker runs frame-level inference, classifies outputs into asset/defect/environmental hazard groups, persists detections (confidence + geometry), and exposes query APIs for inspection/frame detections.
- **Temporal alignment and change tracking (feature 0004):** after detections, the worker aligns detections against a baseline inspection for the same cohort, stores alignment pairs/change events, and exposes alignment/change query APIs.
- **Progression metrics (feature 0005):** after alignment, the worker derives quantitative metrics from persisted `persisted` alignment pairs (e.g. crack growth rate, vegetation encroachment delta), stores `progression_metrics` rows, and exposes list + summary read APIs.

API details, worker behavior, request examples, and configuration are in [docs/INGEST_API.md](docs/INGEST_API.md).

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
