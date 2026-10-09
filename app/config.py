"""
AEREO Bulk Certificate Generator — Application Configuration.

Loads settings from environment variables / .env file.
"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-wide configuration loaded from environment variables."""

    DATABASE_URL: str = "sqlite:///./aereo.db"
    STORAGE_DIR: str = "./storage/certificates"
    MAX_RECIPIENTS_PER_JOB: int = 500

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def storage_path(self) -> Path:
        """Return the storage directory as a resolved Path, creating it if needed."""
        path = Path(self.STORAGE_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
