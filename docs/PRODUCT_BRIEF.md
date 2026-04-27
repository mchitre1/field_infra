# Infrastructure Intelligence Engine (IIE) - Product Brief

## 1) Project Overview / Description
Infrastructure Intelligence Engine (IIE) converts raw visual inspection data (drone footage, mobile video, fixed camera captures) into prioritized, time-aware maintenance decisions for critical infrastructure operations.  
Unlike tools that only detect visible defects, IIE tracks issue progression over time, estimates risk, and recommends what should be fixed now versus scheduled later.

## 2) Target Audience
- Utility and grid operators (power transmission/distribution)
- Telecom infrastructure owners and field operations teams
- Construction and industrial site managers
- Asset integrity, safety, and maintenance planners

## 3) Primary Benefits / Features
- Multi-source ingestion of image/video inspection data with metadata extraction
- Visual understanding of assets, defects, terrain, and scene context
- Temporal comparison across inspections to detect progression and change
- Action prioritization via risk scoring and operational constraints
- Clear, decision-oriented outputs (what to fix, urgency, deadline)
- Continuous improvement loop from user actions (fixed, deferred, ignored)

## 4) High-Level Tech / Architecture Used
IIE is designed as a modular, cloud-native pipeline where each layer can scale independently.

- **Ingestion & Orchestration:** FastAPI (Python) for upload APIs, Amazon SQS for job queues, and AWS Step Functions for processing workflows
- **Storage Layer:** Amazon S3 for raw media/frames, Amazon RDS for PostgreSQL (+ PostGIS) for inspection metadata, and Amazon ElastiCache (Redis) for short-lived processing state
- **Visual Understanding:** PyTorch inference services on Amazon ECS using YOLO + SAM with OpenCV preprocessing
- **Temporal Intelligence:** Python services (NumPy/OpenCV) on ECS for cross-time alignment, change detection, and progression metrics per asset/zone
- **Decision Engine:** Rule-based prioritization + ML risk scoring service (XGBoost) on ECS, backed by configurable thresholds stored in RDS
- **Serving & Reporting:** FastAPI REST APIs, React + TypeScript dashboard, and Amazon API Gateway for secure external API access
- **MLOps & Training:** Amazon SageMaker for training/retraining pipelines and model versioning, with user feedback events stored in RDS/S3
- **Security & Operations:** AWS IAM for access control, AWS KMS for encryption keys, Amazon CloudWatch for logs/metrics/alerts, and Docker-based CI/CD via GitHub Actions to ECS

## 5) Functional Requirements
- Ingest video/images from drones, smartphones, and fixed cameras
- Extract and store frames, timestamps, geospatial/location metadata, and source context
- Detect and classify assets, defects, and environmental hazards in each inspection
- Align inspections by asset/zone over time to compare state changes
- Compute progression metrics (e.g., crack growth rate, vegetation encroachment delta)
- Generate change maps, anomaly timelines, and trend summaries
- Produce prioritized maintenance recommendations with rationale and suggested SLA windows
- Support configurable risk rules by asset type, severity, and environmental conditions
- Allow users to update issue state (fixed, monitoring, deferred, ignored)
- Capture user outcomes and feed them back into model/risk-score refinement
- Maintain traceable inspection history and decision logs per asset/zone

## 6) Non-Functional Requirements
- **Accuracy:** High precision/recall targets for critical defect classes; calibrated risk scores
- **Scalability:** Handle high-volume video/image ingestion across many sites and assets
- **Latency:** Near-real-time or batch SLAs depending on inspection mode and use case
- **Reliability:** Fault-tolerant processing pipelines with retry and job observability
- **Security:** Encryption in transit/at rest, role-based access, secure data retention policies
- **Compliance:** Auditability and traceability for safety and regulatory workflows
- **Usability:** Clear, actionable outputs understandable by non-ML operations staff
- **Extensibility:** Modular model/rule architecture for new asset types and domains

## Repository note

The `backend/` package currently implements the **ingestion** slice: FastAPI upload and presigned-S3 flows, PostgreSQL inspection records, S3 storage, and optional SQS job publish. See [INGEST_API.md](INGEST_API.md) for the live API contract and configuration.
