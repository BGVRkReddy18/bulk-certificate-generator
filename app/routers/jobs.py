"""
AEREO Bulk Certificate Generator — API routers for jobs and certificates.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.models import Job, JobStatus, Recipient, RecipientStatus
from app.schemas.schemas import (
    CertificateListItem,
    CertificateListResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
    RecipientOut,
)
from app.services.job_service import start_job_processing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["jobs", "certificates"])


# ───────────────────────────────────────────────────────────────────────────
# POST /api/jobs/
# ───────────────────────────────────────────────────────────────────────────

@router.post("/jobs/", response_model=JobCreateResponse, status_code=202)
def create_job(payload: JobCreateRequest, db: Session = Depends(get_db)):
    """Create a new bulk certificate-generation job."""

    # Enforce batch-size limit
    if len(payload.recipients) > settings.MAX_RECIPIENTS_PER_JOB:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Too many recipients. Maximum allowed per job is "
                f"{settings.MAX_RECIPIENTS_PER_JOB}."
            ),
        )

    # Create job record
    job = Job(
        event_name=payload.event_name,
        issue_date=payload.issue_date.isoformat(),
        total_recipients=len(payload.recipients),
    )
    db.add(job)
    db.flush()  # populate job.id

    # Create recipient records
    for r in payload.recipients:
        recipient = Recipient(
            job_id=job.id,
            name=r.name,
            email=r.email,
        )
        db.add(recipient)

    db.commit()
    db.refresh(job)

    # Start background processing
    start_job_processing(job.id)

    return JobCreateResponse(
        job_id=job.id,
        status=job.status.value if isinstance(job.status, JobStatus) else job.status,
        message="Job created. Certificate generation has started.",
    )


# ───────────────────────────────────────────────────────────────────────────
# GET /api/jobs/{job_id}/
# ───────────────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Return detailed status and recipient-level outcomes for a job."""

    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    recipients = (
        db.query(Recipient).filter(Recipient.job_id == job_id).all()
    )

    # Compute pending count from live data
    pending_count = sum(
        1
        for r in recipients
        if r.status in (RecipientStatus.PENDING, RecipientStatus.PROCESSING)
    )

    status_value = job.status.value if isinstance(job.status, JobStatus) else job.status

    return JobStatusResponse(
        job_id=job.id,
        event_name=job.event_name,
        issue_date=job.issue_date,
        status=status_value,
        total_recipients=job.total_recipients,
        successful_count=job.successful_count,
        failed_count=job.failed_count,
        pending_count=pending_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
        recipients=[
            RecipientOut(
                id=r.id,
                name=r.name,
                email=r.email,
                status=r.status.value if isinstance(r.status, RecipientStatus) else r.status,
                certificate_id=r.certificate_id,
                error_message=r.error_message,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in recipients
        ],
    )


# ───────────────────────────────────────────────────────────────────────────
# GET /api/jobs/{job_id}/certificates/
# ───────────────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/certificates/", response_model=CertificateListResponse)
def list_certificates(job_id: str, db: Session = Depends(get_db)):
    """List generated certificates and per-recipient failures for a job."""

    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    recipients = (
        db.query(Recipient).filter(Recipient.job_id == job_id).all()
    )

    return CertificateListResponse(
        job_id=job.id,
        certificates=[
            CertificateListItem(
                recipient_id=r.id,
                name=r.name,
                email=r.email,
                status=r.status.value if isinstance(r.status, RecipientStatus) else r.status,
                certificate_id=r.certificate_id,
                error_message=r.error_message,
            )
            for r in recipients
        ],
    )


# ───────────────────────────────────────────────────────────────────────────
# GET /api/certificates/{certificate_id}/download/
# ───────────────────────────────────────────────────────────────────────────

@router.get("/certificates/{certificate_id}/download/")
def download_certificate(certificate_id: str, db: Session = Depends(get_db)):
    """Download a generated certificate PDF by its certificate ID.

    Security: the file path is looked up from the database; the client-supplied
    ``certificate_id`` is never used to construct a filesystem path directly,
    preventing path-traversal attacks.
    """

    recipient = (
        db.query(Recipient)
        .filter(Recipient.certificate_id == certificate_id)
        .first()
    )
    if recipient is None:
        raise HTTPException(
            status_code=404, detail="Certificate not found."
        )

    if not recipient.file_path:
        raise HTTPException(
            status_code=404,
            detail="Certificate file path not available.",
        )

    file_path = Path(recipient.file_path)

    # Ensure the resolved path is under the configured storage directory
    try:
        file_path.resolve().relative_to(settings.storage_path)
    except ValueError:
        logger.warning(
            "Path traversal attempt blocked for certificate %s",
            certificate_id,
        )
        raise HTTPException(status_code=404, detail="Certificate not found.")

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Certificate file is missing from storage.",
        )

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=file_path.name,
    )
