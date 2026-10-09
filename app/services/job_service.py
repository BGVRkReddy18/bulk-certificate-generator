"""
AEREO Bulk Certificate Generator — Job processing service.

Processes bulk certificate jobs using a synchronous background thread.

## Design Decision: ``threading.Thread`` over Celery / asyncio

For a short assignment with SQLite, a simple daemon thread per job is the most
practical approach.  SQLite supports multiple *readers* but only one *writer*
at a time; a single background thread processing one job at a time avoids WAL
contention issues.

### Limitations

* **Durability** — If the server process crashes mid-job, in-progress
  recipients stay in PROCESSING state.  There is no automatic retry or
  recovery.  A production system should use a persistent task queue (Celery +
  Redis/RabbitMQ).
* **Scalability** — One thread per job; concurrent large jobs will compete for
  CPU.  Acceptable for the expected load of this assignment.
* **Concurrency** — Each background thread creates its own DB session to avoid
  unsafe cross-thread session sharing.
"""

import logging
import threading
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.models import Job, JobStatus, Recipient, RecipientStatus
from app.services.pdf_service import generate_certificate_pdf

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_job_processing(job_id: str) -> None:
    """Spawn a background thread to process the given job.

    The thread creates its own database session so the calling request
    handler can safely close its own session.
    """
    thread = threading.Thread(
        target=_process_job,
        args=(job_id,),
        daemon=True,
        name=f"job-{job_id[:8]}",
    )
    thread.start()


def process_job_sync(job_id: str) -> None:
    """Process a job synchronously (useful for tests).

    Uses its own DB session, same as the background path.
    """
    _process_job(job_id)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _process_job(job_id: str) -> None:
    """Process every recipient in *job_id*, updating statuses as we go.

    Each recipient is processed independently; individual failures are
    captured without aborting the remaining recipients.
    """
    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is None:
            logger.error("Job %s not found — aborting processing.", job_id)
            return

        job.status = JobStatus.PROCESSING
        db.commit()

        output_dir: Path = settings.storage_path
        success = 0
        failed = 0

        recipients = (
            db.query(Recipient)
            .filter(Recipient.job_id == job_id)
            .all()
        )

        for recipient in recipients:
            # Skip recipients that already have a terminal status
            # (e.g., VALIDATION_FAILED set during creation)
            if recipient.status in (
                RecipientStatus.COMPLETED,
                RecipientStatus.FAILED,
                RecipientStatus.VALIDATION_FAILED,
            ):
                if recipient.status == RecipientStatus.COMPLETED:
                    success += 1
                else:
                    failed += 1
                continue

            recipient.status = RecipientStatus.PROCESSING
            db.commit()

            try:
                cert_id = str(uuid.uuid4())
                filepath = generate_certificate_pdf(
                    recipient_name=recipient.name,
                    event_name=job.event_name,
                    issue_date=job.issue_date,
                    certificate_id=cert_id,
                    output_dir=output_dir,
                )
                recipient.status = RecipientStatus.COMPLETED
                recipient.certificate_id = cert_id
                recipient.file_path = str(filepath)
                success += 1
            except Exception as exc:
                logger.exception(
                    "Failed to generate certificate for recipient %s",
                    recipient.id,
                )
                recipient.status = RecipientStatus.FAILED
                recipient.error_message = f"PDF generation failed: {type(exc).__name__}"
                failed += 1

            db.commit()

        # ── Determine terminal job status ───────────────────────────────
        job.successful_count = success
        job.failed_count = failed

        if failed == 0:
            job.status = JobStatus.COMPLETED
        elif success == 0:
            job.status = JobStatus.FAILED
        else:
            job.status = JobStatus.COMPLETED_WITH_ERRORS

        db.commit()
        logger.info(
            "Job %s finished — %d succeeded, %d failed.",
            job_id,
            success,
            failed,
        )
    except Exception:
        logger.exception("Unhandled error processing job %s", job_id)
        # Best-effort: mark job as FAILED
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job and job.status not in (
                JobStatus.COMPLETED,
                JobStatus.COMPLETED_WITH_ERRORS,
                JobStatus.FAILED,
            ):
                job.status = JobStatus.FAILED
                db.commit()
        except Exception:
            logger.exception("Could not mark job %s as FAILED", job_id)
    finally:
        db.close()
