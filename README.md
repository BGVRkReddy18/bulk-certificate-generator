# AEREO Bulk Certificate Generator

A backend API that accepts bulk certificate requests, validates recipient data, generates personalized PDF certificates from a professional template, tracks job progress with individual failure isolation, and allows generated certificates to be downloaded.

---

## Features

- **Bulk Job Creation** — Submit one request with many recipients; receive a job ID and track progress.
- **Professional PDF Certificates** — ReportLab-generated landscape A4 certificates with decorative borders, gold accents, and all required fields.
- **Failure Isolation** — Individual recipient failures never block other recipients from processing.
- **Job Progress Tracking** — Real-time status with counts for successful, failed, and pending recipients.
- **Certificate Download** — Download any generated PDF by certificate ID with path-traversal protection.
- **Input Validation** — Comprehensive validation of emails, required fields, batch-size limits, and data types.
- **Consistent Error Responses** — JSON error bodies with appropriate HTTP status codes; no stack traces exposed.

---

## Technology Stack

| Component         | Technology              |
|-------------------|-------------------------|
| Language          | Python 3.11+            |
| Web Framework     | FastAPI                 |
| Database          | SQLite                  |
| ORM               | SQLAlchemy 2.x          |
| Validation        | Pydantic v2             |
| PDF Generation    | ReportLab               |
| Testing           | pytest + FastAPI TestClient |
| Server            | Uvicorn                 |

---

## Prerequisites

- **Python 3.11+** — [Download](https://www.python.org/downloads/)
- **pip** (bundled with Python)
- **Git** (for version control)

---

## Setup (macOS)

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/AERO_Assignment.git
cd AERO_Assignment
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env if you want to change defaults (database path, storage dir, batch limit)
```

### 5. Initialise the database

The database tables are created automatically on the first application startup. No manual migration step is needed.

### 6. Start the application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Running Tests

```bash
pytest tests/ -v
```

Tests use an **in-memory SQLite database** and a **temporary directory** for certificate storage. No production data is touched.

---

## API Endpoints

### 1. Create a Bulk Job

**`POST /api/jobs/`**

**Request Body:**
```json
{
  "event_name": "Python Masterclass 2025",
  "issue_date": "2025-06-15",
  "recipients": [
    { "name": "Alice Johnson", "email": "alice@example.com" },
    { "name": "Bob Smith", "email": "bob@example.com" },
    { "name": "Charlie Lee", "email": "charlie@example.com" }
  ]
}
```

**Response (HTTP 202):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "PENDING",
  "message": "Job created. Certificate generation has started."
}
```

### 2. Get Job Status

**`GET /api/jobs/{job_id}/`**

**Response (HTTP 200):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "event_name": "Python Masterclass 2025",
  "issue_date": "2025-06-15",
  "status": "COMPLETED",
  "total_recipients": 3,
  "successful_count": 3,
  "failed_count": 0,
  "pending_count": 0,
  "created_at": "2025-06-15T10:00:00Z",
  "updated_at": "2025-06-15T10:00:05Z",
  "recipients": [
    {
      "id": "...",
      "name": "Alice Johnson",
      "email": "alice@example.com",
      "status": "COMPLETED",
      "certificate_id": "cert-uuid-here",
      "error_message": null,
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### 3. List Certificates for a Job

**`GET /api/jobs/{job_id}/certificates/`**

**Response (HTTP 200):**
```json
{
  "job_id": "a1b2c3d4-...",
  "certificates": [
    {
      "recipient_id": "...",
      "name": "Alice Johnson",
      "email": "alice@example.com",
      "status": "COMPLETED",
      "certificate_id": "cert-uuid",
      "error_message": null
    }
  ]
}
```

### 4. Download a Certificate

**`GET /api/certificates/{certificate_id}/download/`**

Returns the PDF file with `Content-Type: application/pdf`.

**Example with curl:**
```bash
curl -o certificate.pdf http://localhost:8000/api/certificates/{certificate_id}/download/
```

### 5. Health Check

**`GET /health`**

```json
{ "status": "ok" }
```

### Error Responses

All errors return consistent JSON:
```json
{ "detail": "Human-readable error message" }
```

| Status Code | Meaning                                  |
|-------------|------------------------------------------|
| 202         | Job created, processing started          |
| 200         | Successful retrieval                     |
| 404         | Job or certificate not found             |
| 422         | Validation error (bad input)             |
| 500         | Internal server error (details hidden)   |

---

## Architecture and Processing Flow

```
Client                  FastAPI                     Background Thread
  │                       │                              │
  │  POST /api/jobs/      │                              │
  │──────────────────────►│                              │
  │                       │  Validate + persist job      │
  │                       │  Spawn thread ──────────────►│
  │  ◄── 202 Accepted ───│                              │
  │                       │                              │  For each recipient:
  │                       │                              │    Update status → PROCESSING
  │                       │                              │    Generate PDF
  │                       │                              │    Update status → COMPLETED/FAILED
  │                       │                              │  Update job → terminal status
  │                       │                              │
  │  GET /api/jobs/{id}/  │                              │
  │──────────────────────►│                              │
  │  ◄── 200 status ─────│                              │
```

### Processing Design Decision

This project uses **`threading.Thread`** (one daemon thread per job) instead of Celery, asyncio, or external task queues.

**Why:**
- SQLite does not support high-concurrency writes; a single thread per job avoids WAL contention.
- No external infrastructure (Redis, RabbitMQ) to install.
- Adequate for the expected workload of this assignment.

**Trade-offs:**
- ✅ Simple, zero-dependency background processing
- ✅ Each thread has its own DB session — no unsafe session sharing
- ❌ No automatic retry on failure
- ❌ If the server crashes mid-job, in-progress recipients are not recovered
- ❌ Not suitable for high-concurrency production workloads

---

## Database Design

### `jobs` table

| Column             | Type         | Description                        |
|--------------------|--------------|------------------------------------|
| `id`               | UUID (PK)    | Unique job identifier              |
| `event_name`       | VARCHAR(255) | Event or course name               |
| `issue_date`       | VARCHAR(10)  | ISO date string (YYYY-MM-DD)       |
| `status`           | ENUM         | Job lifecycle status               |
| `total_recipients` | INTEGER      | Total recipients submitted         |
| `successful_count` | INTEGER      | Recipients processed successfully  |
| `failed_count`     | INTEGER      | Recipients that failed             |
| `created_at`       | DATETIME     | Record creation timestamp          |
| `updated_at`       | DATETIME     | Last modification timestamp        |

### `recipients` table

| Column           | Type         | Description                         |
|------------------|--------------|-------------------------------------|
| `id`             | UUID (PK)    | Unique recipient record identifier  |
| `job_id`         | UUID (FK)    | Parent job reference                |
| `name`           | VARCHAR(255) | Recipient's full name               |
| `email`          | VARCHAR(255) | Recipient's email address           |
| `status`         | ENUM         | Recipient processing status         |
| `certificate_id` | UUID (UQ)    | Generated certificate identifier    |
| `file_path`      | TEXT         | Filesystem path to the PDF          |
| `error_message`  | TEXT         | Error details (if failed)           |
| `created_at`     | DATETIME     | Record creation timestamp           |
| `updated_at`     | DATETIME     | Last modification timestamp         |

### Status Definitions

**Job statuses:**
| Status                 | Meaning                                       |
|------------------------|-----------------------------------------------|
| `PENDING`              | Created but processing has not begun           |
| `PROCESSING`           | At least one recipient is being processed      |
| `COMPLETED`            | All recipients processed successfully          |
| `COMPLETED_WITH_ERRORS`| Processing finished; some recipients failed    |
| `FAILED`               | All recipients failed                          |

**Recipient statuses:**
| Status              | Meaning                                       |
|---------------------|-----------------------------------------------|
| `PENDING`           | Not yet processed                              |
| `PROCESSING`        | Currently being processed                      |
| `COMPLETED`         | Certificate generated successfully             |
| `FAILED`            | PDF generation failed                          |
| `VALIDATION_FAILED` | Pre-processing validation failed               |

---

## Validation and Failure Handling

### Input Validation
- **Event name** — required, non-blank, max 255 characters
- **Issue date** — required, ISO 8601 format (YYYY-MM-DD)
- **Recipients list** — required, at least 1 entry, max 500 (configurable)
- **Recipient name** — required, non-blank, max 255 characters
- **Recipient email** — required, valid email format

### Failure Isolation
- Each recipient is processed independently inside a try/except block
- A failing recipient is marked `FAILED` with a safe error message (no stack traces)
- All other recipients continue processing
- The job's terminal status reflects the overall outcome:
  - All succeed → `COMPLETED`
  - Mix → `COMPLETED_WITH_ERRORS`
  - All fail → `FAILED`

### Security
- Certificate downloads look up file paths from the database — client-supplied IDs never construct filesystem paths
- Downloaded files are verified to be under the configured storage directory (path-traversal prevention)
- The global exception handler ensures stack traces are never returned to clients

---

## Known Limitations

1. **No crash recovery** — If the server process dies mid-job, in-progress recipients remain in `PROCESSING` status with no automatic retry.
2. **No persistent task queue** — Background threads are lost on restart. A production system should use Celery or a similar durable queue.
3. **SQLite limitations** — Single-writer constraint limits concurrent job throughput. PostgreSQL would be needed for production scale.
4. **No authentication/authorization** — All endpoints are publicly accessible.
5. **No rate limiting** — The batch-size limit is the only throttling mechanism.
6. **Local file storage** — Certificates are stored on the local filesystem, not in cloud object storage.
7. **No email notifications** — Recipients are not notified when their certificates are ready.

---

## What I Learned

- Designing failure-isolated bulk-processing pipelines where individual errors must not cascade.
- Safe background-processing patterns with separate DB sessions per thread to avoid SQLAlchemy cross-thread issues.
- Practical trade-offs between simplicity (threading) and robustness (Celery) in short-deadline projects.
- Path-traversal prevention and the importance of never letting client input construct filesystem paths.
- Structuring FastAPI projects with clear separation of concerns (routers → services → models → schemas).
- Writing deterministic tests for asynchronous background processing via synchronous monkey-patching.

---

## Future Scope

- **Persistent task queue** — Replace `threading.Thread` with Celery + Redis for crash recovery and horizontal scaling.
- **PostgreSQL** — Replace SQLite for concurrent writes and production-grade reliability.
- **Email delivery** — Notify recipients when their certificates are ready.
- **Template management** — Allow uploading custom certificate templates via the API.
- **Authentication** — Add JWT-based auth and role-based access control.
- **Cloud storage** — Store certificates in S3/GCS instead of the local filesystem.
- **Pagination** — Add pagination to the certificate listing endpoint for large jobs.
- **Webhook callbacks** — Notify external systems when jobs complete.
- **Docker support** — Add a Dockerfile and docker-compose for easy deployment.
- **CI/CD** — GitHub Actions pipeline for automated testing and linting.

---

## Project Structure

```
AERO_Assignment/
├── app/
│   ├── __init__.py
│   ├── config.py            # Settings loaded from env / .env
│   ├── database.py          # SQLAlchemy engine, session, Base
│   ├── main.py              # FastAPI app entry point
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py        # Job and Recipient ORM models
│   ├── routers/
│   │   ├── __init__.py
│   │   └── jobs.py          # API route handlers
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── schemas.py       # Pydantic request/response schemas
│   └── services/
│       ├── __init__.py
│       ├── job_service.py   # Job processing logic
│       └── pdf_service.py   # PDF certificate generation
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Test fixtures and DB setup
│   └── test_api.py          # Comprehensive test suite
├── storage/
│   └── certificates/        # Generated PDFs (gitignored)
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

---

## License

This project was built as an assignment submission.
