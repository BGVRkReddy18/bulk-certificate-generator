"""
AEREO Bulk Certificate Generator — SQLAlchemy ORM models.

Defines the `Job` and `Recipient` tables with appropriate relationships,
constraints, and UUID-based identifiers.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobStatus(str, enum.Enum):
    """Lifecycle statuses for a bulk-generation job."""

    PENDING = "PENDING"                        # Created but processing has not begun
    PROCESSING = "PROCESSING"                  # At least one recipient is being processed
    COMPLETED = "COMPLETED"                    # All recipients processed successfully
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"  # Processing finished; some failed
    FAILED = "FAILED"                          # All recipients failed


class RecipientStatus(str, enum.Enum):
    """Lifecycle statuses for an individual recipient within a job."""

    PENDING = "PENDING"            # Not yet processed
    PROCESSING = "PROCESSING"     # Currently being processed
    COMPLETED = "COMPLETED"       # Certificate generated successfully
    FAILED = "FAILED"             # Certificate generation failed
    VALIDATION_FAILED = "VALIDATION_FAILED"  # Pre-processing validation failed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Job(Base):
    """Represents a bulk certificate-generation job."""

    __tablename__ = "jobs"

    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    event_name: str = Column(String(255), nullable=False)
    issue_date: str = Column(String(10), nullable=False)  # ISO date string
    status: str = Column(
        Enum(JobStatus), nullable=False, default=JobStatus.PENDING
    )

    total_recipients: int = Column(Integer, nullable=False, default=0)
    successful_count: int = Column(Integer, nullable=False, default=0)
    failed_count: int = Column(Integer, nullable=False, default=0)

    created_at: datetime = Column(DateTime(timezone=True), default=_utcnow)
    updated_at: datetime = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationship
    recipients = relationship(
        "Recipient", back_populates="job", cascade="all, delete-orphan"
    )


class Recipient(Base):
    """Represents one certificate recipient within a job."""

    __tablename__ = "recipients"

    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    job_id: str = Column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    name: str = Column(String(255), nullable=False)
    email: str = Column(String(255), nullable=False)
    status: str = Column(
        Enum(RecipientStatus), nullable=False, default=RecipientStatus.PENDING
    )

    certificate_id: str | None = Column(String(36), unique=True, nullable=True)
    file_path: str | None = Column(Text, nullable=True)
    error_message: str | None = Column(Text, nullable=True)

    created_at: datetime = Column(DateTime(timezone=True), default=_utcnow)
    updated_at: datetime = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationship
    job = relationship("Job", back_populates="recipients")
