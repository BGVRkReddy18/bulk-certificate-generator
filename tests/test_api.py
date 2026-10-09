"""
AEREO Bulk Certificate Generator — comprehensive test suite.

Covers:
1.  Job creation with multiple recipients
2.  Request and recipient validation (missing fields, bad emails, blank names)
3.  Successful PDF generation and file validity
4.  Job status and progress counts
5.  Simulated failure for one recipient while others succeed
6.  Listing and downloading certificates
7.  Unknown job / certificate IDs → 404
8.  Empty batches and edge cases
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.models import RecipientStatus


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _valid_payload(n: int = 3) -> dict:
    """Return a valid job-creation payload with *n* recipients."""
    return {
        "event_name": "Python Masterclass 2025",
        "issue_date": "2025-06-15",
        "recipients": [
            {"name": f"User {i}", "email": f"user{i}@example.com"}
            for i in range(1, n + 1)
        ],
    }


# ──────────────────────────────────────────────────────────────────────────
# 1. Job creation
# ──────────────────────────────────────────────────────────────────────────

class TestJobCreation:
    def test_create_job_success(self, client):
        resp = client.post("/api/jobs/", json=_valid_payload())
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert body["status"] in ("PENDING", "PROCESSING", "COMPLETED")
        assert body["message"]

    def test_create_job_returns_unique_ids(self, client):
        r1 = client.post("/api/jobs/", json=_valid_payload())
        r2 = client.post("/api/jobs/", json=_valid_payload())
        assert r1.json()["job_id"] != r2.json()["job_id"]

    def test_multiple_recipients_created(self, client):
        resp = client.post("/api/jobs/", json=_valid_payload(5))
        job_id = resp.json()["job_id"]
        status = client.get(f"/api/jobs/{job_id}/").json()
        assert status["total_recipients"] == 5
        assert len(status["recipients"]) == 5


# ──────────────────────────────────────────────────────────────────────────
# 2. Validation
# ──────────────────────────────────────────────────────────────────────────

class TestValidation:
    def test_missing_event_name(self, client):
        payload = _valid_payload()
        del payload["event_name"]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422

    def test_blank_event_name(self, client):
        payload = _valid_payload()
        payload["event_name"] = "   "
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422

    def test_missing_issue_date(self, client):
        payload = _valid_payload()
        del payload["issue_date"]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422

    def test_invalid_date_format(self, client):
        payload = _valid_payload()
        payload["issue_date"] = "15-06-2025"  # not ISO
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422

    def test_empty_recipients_list(self, client):
        payload = _valid_payload()
        payload["recipients"] = []
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422

    def test_missing_recipients_field(self, client):
        resp = client.post(
            "/api/jobs/",
            json={"event_name": "Test", "issue_date": "2025-01-01"},
        )
        assert resp.status_code == 422

    def test_invalid_email(self, client):
        payload = _valid_payload()
        payload["recipients"] = [{"name": "Alice", "email": "not-an-email"}]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422

    def test_blank_recipient_name(self, client):
        payload = _valid_payload()
        payload["recipients"] = [{"name": "  ", "email": "a@b.com"}]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422

    def test_missing_recipient_name(self, client):
        payload = _valid_payload()
        payload["recipients"] = [{"email": "a@b.com"}]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422

    def test_missing_recipient_email(self, client):
        payload = _valid_payload()
        payload["recipients"] = [{"name": "Alice"}]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422

    def test_batch_size_limit(self, client):
        payload = _valid_payload()
        payload["recipients"] = [
            {"name": f"User {i}", "email": f"u{i}@x.com"}
            for i in range(600)
        ]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 422
        assert "Too many recipients" in resp.json()["detail"]


# ──────────────────────────────────────────────────────────────────────────
# 3. PDF generation
# ──────────────────────────────────────────────────────────────────────────

class TestPdfGeneration:
    def test_pdf_files_created(self, client, storage_dir: Path):
        resp = client.post("/api/jobs/", json=_valid_payload(2))
        job_id = resp.json()["job_id"]
        status = client.get(f"/api/jobs/{job_id}/").json()
        completed = [
            r for r in status["recipients"] if r["status"] == "COMPLETED"
        ]
        assert len(completed) == 2
        for r in completed:
            assert r["certificate_id"] is not None

    def test_pdf_is_valid(self, client, storage_dir: Path):
        """Downloaded PDF must start with the ``%PDF`` magic bytes."""
        resp = client.post("/api/jobs/", json=_valid_payload(1))
        job_id = resp.json()["job_id"]
        certs = client.get(f"/api/jobs/{job_id}/certificates/").json()
        cert_id = certs["certificates"][0]["certificate_id"]

        dl = client.get(f"/api/certificates/{cert_id}/download/")
        assert dl.status_code == 200
        assert dl.headers["content-type"] == "application/pdf"
        assert dl.content[:5] == b"%PDF-"


# ──────────────────────────────────────────────────────────────────────────
# 4. Job status and counts
# ──────────────────────────────────────────────────────────────────────────

class TestJobStatus:
    def test_completed_status_and_counts(self, client):
        resp = client.post("/api/jobs/", json=_valid_payload(3))
        job_id = resp.json()["job_id"]
        status = client.get(f"/api/jobs/{job_id}/").json()

        assert status["status"] == "COMPLETED"
        assert status["total_recipients"] == 3
        assert status["successful_count"] == 3
        assert status["failed_count"] == 0
        assert status["pending_count"] == 0

    def test_status_includes_event_and_date(self, client):
        resp = client.post("/api/jobs/", json=_valid_payload())
        job_id = resp.json()["job_id"]
        status = client.get(f"/api/jobs/{job_id}/").json()
        assert status["event_name"] == "Python Masterclass 2025"
        assert status["issue_date"] == "2025-06-15"


# ──────────────────────────────────────────────────────────────────────────
# 5. Partial failure isolation
# ──────────────────────────────────────────────────────────────────────────

class TestFailureIsolation:
    def test_one_failure_others_succeed(self, client):
        """
        Patch ``generate_certificate_pdf`` to raise on the second call.
        The other recipients must still complete successfully.
        """
        call_count = {"n": 0}
        _original = None

        def _failing_generator(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("Simulated PDF error")
            from app.services.pdf_service import generate_certificate_pdf as _orig
            return _orig(**kwargs)

        with patch(
            "app.services.job_service.generate_certificate_pdf",
            side_effect=_failing_generator,
        ):
            resp = client.post("/api/jobs/", json=_valid_payload(3))

        job_id = resp.json()["job_id"]
        status = client.get(f"/api/jobs/{job_id}/").json()

        assert status["status"] == "COMPLETED_WITH_ERRORS"
        assert status["successful_count"] == 2
        assert status["failed_count"] == 1

        failed = [r for r in status["recipients"] if r["status"] == "FAILED"]
        assert len(failed) == 1
        assert failed[0]["error_message"]
        # Must not expose stack traces
        assert "Traceback" not in failed[0]["error_message"]

    def test_all_fail(self, client):
        """If every recipient fails, job status should be FAILED."""
        with patch(
            "app.services.job_service.generate_certificate_pdf",
            side_effect=RuntimeError("boom"),
        ):
            resp = client.post("/api/jobs/", json=_valid_payload(2))

        job_id = resp.json()["job_id"]
        status = client.get(f"/api/jobs/{job_id}/").json()
        assert status["status"] == "FAILED"
        assert status["successful_count"] == 0
        assert status["failed_count"] == 2


# ──────────────────────────────────────────────────────────────────────────
# 6. Certificate listing and download
# ──────────────────────────────────────────────────────────────────────────

class TestCertificates:
    def test_list_certificates(self, client):
        resp = client.post("/api/jobs/", json=_valid_payload(2))
        job_id = resp.json()["job_id"]

        certs = client.get(f"/api/jobs/{job_id}/certificates/").json()
        assert certs["job_id"] == job_id
        assert len(certs["certificates"]) == 2
        for c in certs["certificates"]:
            assert c["certificate_id"] is not None
            assert c["status"] == "COMPLETED"

    def test_download_certificate(self, client):
        resp = client.post("/api/jobs/", json=_valid_payload(1))
        job_id = resp.json()["job_id"]
        certs = client.get(f"/api/jobs/{job_id}/certificates/").json()
        cert_id = certs["certificates"][0]["certificate_id"]

        dl = client.get(f"/api/certificates/{cert_id}/download/")
        assert dl.status_code == 200
        assert len(dl.content) > 100  # non-trivial file

    def test_list_includes_failures(self, client):
        with patch(
            "app.services.job_service.generate_certificate_pdf",
            side_effect=RuntimeError("fail"),
        ):
            resp = client.post("/api/jobs/", json=_valid_payload(1))

        job_id = resp.json()["job_id"]
        certs = client.get(f"/api/jobs/{job_id}/certificates/").json()
        assert certs["certificates"][0]["status"] == "FAILED"
        assert certs["certificates"][0]["error_message"]


# ──────────────────────────────────────────────────────────────────────────
# 7. Unknown IDs
# ──────────────────────────────────────────────────────────────────────────

class TestNotFound:
    def test_unknown_job_status(self, client):
        resp = client.get("/api/jobs/nonexistent-id/")
        assert resp.status_code == 404

    def test_unknown_job_certificates(self, client):
        resp = client.get("/api/jobs/nonexistent-id/certificates/")
        assert resp.status_code == 404

    def test_unknown_certificate_download(self, client):
        resp = client.get("/api/certificates/nonexistent-id/download/")
        assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────────
# 8. Edge cases
# ──────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_single_recipient(self, client):
        payload = _valid_payload(1)
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        status = client.get(f"/api/jobs/{job_id}/").json()
        assert status["successful_count"] == 1

    def test_long_recipient_name(self, client):
        payload = _valid_payload()
        payload["recipients"] = [
            {"name": "A" * 200, "email": "long@example.com"}
        ]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 202

    def test_special_characters_in_name(self, client):
        payload = _valid_payload()
        payload["recipients"] = [
            {"name": "José María O'Brien-López", "email": "jose@example.com"}
        ]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        status = client.get(f"/api/jobs/{job_id}/").json()
        assert status["successful_count"] == 1

    def test_duplicate_emails_allowed(self, client):
        """Same person may receive certificates for the same event."""
        payload = _valid_payload()
        payload["recipients"] = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Alice Copy", "email": "alice@example.com"},
        ]
        resp = client.post("/api/jobs/", json=payload)
        assert resp.status_code == 202

    def test_malformed_json_body(self, client):
        resp = client.post(
            "/api/jobs/",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
