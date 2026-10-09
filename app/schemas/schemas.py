"""
AEREO Bulk Certificate Generator — Pydantic schemas for request / response validation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class RecipientIn(BaseModel):
    """Schema for a single recipient inside a job-creation request."""

    name: str = Field(..., min_length=1, max_length=255, description="Recipient full name")
    email: EmailStr = Field(..., description="Recipient email address")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name must not be blank or whitespace-only")
        return v.strip()


class JobCreateRequest(BaseModel):
    """Schema for ``POST /api/jobs/``."""

    event_name: str = Field(
        ..., min_length=1, max_length=255, description="Name of the event or course"
    )
    issue_date: date = Field(..., description="Certificate issue date (YYYY-MM-DD)")
    recipients: list[RecipientIn] = Field(
        ..., min_length=1, description="List of certificate recipients"
    )

    @field_validator("event_name")
    @classmethod
    def event_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Event name must not be blank or whitespace-only")
        return v.strip()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class RecipientOut(BaseModel):
    """Response representation of a recipient / certificate record."""

    id: str
    name: str
    email: str
    status: str
    certificate_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class JobCreateResponse(BaseModel):
    """Returned on successful job creation (HTTP 202)."""

    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Detailed job-status response."""

    job_id: str
    event_name: str
    issue_date: str
    status: str
    total_recipients: int
    successful_count: int
    failed_count: int
    pending_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    recipients: list[RecipientOut]

    model_config = {"from_attributes": True}


class CertificateListItem(BaseModel):
    """Single entry in the certificate listing endpoint."""

    recipient_id: str
    name: str
    email: str
    status: str
    certificate_id: Optional[str] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class CertificateListResponse(BaseModel):
    """Response for ``GET /api/jobs/{job_id}/certificates/``."""

    job_id: str
    certificates: list[CertificateListItem]


class ErrorResponse(BaseModel):
    """Standard JSON error body."""

    detail: str
