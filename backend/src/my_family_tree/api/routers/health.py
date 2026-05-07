"""Health check. Reports DB, Redis (TODO), and storage reachability."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from my_family_tree.api.deps import SessionDep, SettingsDep, StorageDep

router = APIRouter()


class HealthStatus(BaseModel):
    status: str
    db: str
    s3: str
    llm: dict[str, str]


@router.get("/healthz", response_model=HealthStatus)
async def healthz(
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> HealthStatus:
    db_ok = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception as e:
        db_ok = f"error: {e!s}"

    s3_ok = "ok"
    try:
        await storage.head("__health__")
    except Exception as e:
        s3_ok = f"error: {e!s}"

    llm_status = {
        "openai": "configured" if settings.llm.openai_api_key is not None else "missing",
        "anthropic": "configured" if settings.llm.anthropic_api_key is not None else "missing",
    }
    return HealthStatus(status="ok", db=db_ok, s3=s3_ok, llm=llm_status)
