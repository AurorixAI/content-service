"""Content Service — Domain Exceptions"""
from __future__ import annotations


class JobNotFoundError(Exception):
    """Job does not exist in Redis."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job not found: {job_id}")
        self.job_id = job_id


class JobAlreadyRunningError(Exception):
    """Attempt to start a job that is already running."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job already running: {job_id}")
        self.job_id = job_id


class PipelineError(Exception):
    """Unrecoverable error in the digitization pipeline."""


class OCRError(PipelineError):
    """Mathpix OCR failed."""


class ExtractionError(PipelineError):
    """Gemini extraction failed for a paragraph."""


class ClassificationError(PipelineError):
    """Skill mapping failed."""
