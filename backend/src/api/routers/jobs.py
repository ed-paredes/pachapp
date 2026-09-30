"""Job status endpoint (ING-REQ-026, API-REQ-013)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.deps import get_session
from api.errors import JOB_NOT_FOUND, AppError, ErrorResponse
from api.schemas import JobRead
from shared.models import Job

router = APIRouter(tags=["jobs"])


@router.get(
    "/jobs/{job_id}",
    response_model=JobRead,
    responses={404: {"model": ErrorResponse}},
)
def get_job(job_id: str, session: Annotated[Session, Depends(get_session)]) -> JobRead:
    job = session.get(Job, job_id)
    if job is None:
        raise AppError(JOB_NOT_FOUND, f"Job {job_id} does not exist", 404, {"job_id": job_id})
    return JobRead(
        status=job.status,
        step=job.step,
        progress=job.progress,
        error=job.error,
        result=job.result,
    )
