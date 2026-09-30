"""API response models (docs/specs/04-wardrobe-api.md, API-REQ-017)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from shared.enums import JobStatus, JobStep


class GarmentCreated(BaseModel):
    """`202` body of `POST /garments` (ING-REQ-001)."""

    garment_id: str
    job_id: str


class JobRead(BaseModel):
    """`GET /jobs/{id}` body (ING-REQ-026, API-REQ-013)."""

    status: JobStatus
    step: JobStep | None
    progress: int
    error: str | None
    result: dict[str, Any] | None
