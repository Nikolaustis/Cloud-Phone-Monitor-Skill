from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from collections import defaultdict, deque
from typing import Deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from . import AI_RELEASE_VERSION
from cloud_phone_monitor.ai_context import build_ai_context
from .config import Settings
from .orchestrator import PricingCopilot
from .schemas import AskRequest, AskResponse, Evidence, ExplainRequest, WhatIfRequest, WhatIfResponse
from .presentation import render_configuration_explanation, render_market_brief, render_what_if
from .store import ContextStore, ContextUnavailable
from .tools import PricingTools, attach_evidence_ids

settings = Settings.from_env()


def _auto_build_local_context() -> None:
    """Refresh local AI context from canonical Dashboard data before serving.

    This prevents the Copilot API from serving a stale/sparse config_index after
    source-code upgrades. Remote-only context deployments are left untouched.
    """
    if not settings.auto_build_context:
        return
    data_dir = settings.context_dir.parent
    canonical_inventory = data_dir / "duration_price_comparison.json"
    if not canonical_inventory.is_file():
        return
    build_ai_context(data_dir, settings.context_dir)


_auto_build_local_context()
store = ContextStore(settings)
tools = PricingTools(store)
copilot = PricingCopilot(settings, tools)
SERVICE_INSTANCE_ID = uuid.uuid4().hex
SERVICE_STARTED_AT_UTC = datetime.now(timezone.utc).isoformat()
SERVICE_PID = os.getpid()

app = FastAPI(
    title="Cloud Phone Pricing Intelligence API",
    version=AI_RELEASE_VERSION,
    description="Evidence-grounded query, explanation and deterministic pricing simulation API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_buckets: dict[str, Deque[float]] = defaultdict(deque)


@app.middleware("http")
async def simple_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/ai/"):
        now = time.monotonic()
        key = request.client.host if request.client else "unknown"
        bucket = _buckets[key]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= settings.max_requests_per_minute:
            return _json_error(429, "AI request rate limit exceeded")
        bucket.append(now)
    return await call_next(request)


def _json_error(status_code: int, detail: str):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _meta() -> tuple[str, str]:
    manifest = store.manifest
    return str(manifest.get("data_date") or "unknown"), str(manifest.get("data_revision") or "unknown")


@app.get("/health")
def health():
    try:
        manifest = store.manifest
        return {
            "ok": True,
            "service": "cloud-phone-pricing-intelligence-api",
            "service_instance_id": SERVICE_INSTANCE_ID,
            "service_pid": SERVICE_PID,
            "service_started_at_utc": SERVICE_STARTED_AT_UTC,
            "service_launch_token": settings.service_launch_token,
            "api_version": AI_RELEASE_VERSION,
            "mode": copilot.mode,
            "provider": settings.provider,
            "schema_version": manifest.get("schema_version"),
            "contract_version": manifest.get("contract_version"),
            "data_date": manifest.get("data_date"),
            "data_revision": manifest.get("data_revision"),
            "safe_data_only": manifest.get("safe_data_only"),
        }
    except ContextUnavailable as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/ai/refresh")
def refresh_context():
    _auto_build_local_context()
    store.refresh()
    return {"ok": True, "manifest": store.manifest}


@app.get("/api/ai/brief")
def market_brief():
    try:
        payload = tools.get_market_overview()
        summary = payload["result"]
        data_date, revision = _meta()
        return {
            "answer": render_market_brief(summary),
            "mode": "evidence",
            "intent": "get_market_overview",
            "confidence": "high",
            "tool_calls": ["get_market_overview"],
            "evidence": attach_evidence_ids(payload.get("evidence", [])),
            "data_date": data_date,
            "data_revision": revision,
        }
    except ContextUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/ai/ask", response_model=AskResponse)
def ask(request: AskRequest):
    try:
        result = copilot.ask(request.question)
        data_date, revision = _meta()
        return AskResponse(
            answer=result["answer"],
            mode=copilot.mode,
            intent=result.get("intent", "unknown"),
            confidence=result.get("confidence", "unknown"),
            evidence=[Evidence(**item) for item in result.get("evidence", [])],
            tool_calls=[str(item) for item in result.get("tool_calls", [])],
            data_date=data_date,
            data_revision=revision,
        )
    except ContextUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/ai/explain")
def explain(request: ExplainRequest):
    try:
        compare = tools.compare_configuration(request.config_id, request.duration_days)
        rows = compare["result"]
        if not rows:
            raise HTTPException(status_code=404, detail="Configuration not found")
        row = rows[0]
        pairings = tools.get_pairing_evidence(request.config_id, request.duration_days, 20)
        evidence = attach_evidence_ids(compare["evidence"] + pairings["evidence"])
        answer = render_configuration_explanation(row, pairings["result"])
        data_date, revision = _meta()
        return {
            "answer": answer,
            "mode": "evidence",
            "intent": "explain_configuration",
            "confidence": "high",
            "tool_calls": ["compare_configuration", "get_pairing_evidence"],
            "evidence": evidence,
            "facts": {"configuration": row, "pairings": pairings["result"]},
            "data_date": data_date,
            "data_revision": revision,
        }
    except ContextUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/ai/what-if", response_model=WhatIfResponse)
def what_if(request: WhatIfRequest):
    try:
        payload = tools.simulate_price(request.config_id, request.proposed_price, request.duration_days)
        result = payload["result"]
        if not result.get("found"):
            raise HTTPException(status_code=404, detail="Configuration not found")
        data_date, revision = _meta()
        return WhatIfResponse(
            answer=render_what_if(result),
            config_id=request.config_id,
            proposed_price=request.proposed_price,
            competitor_median_price=result.get("competitor_median_price"),
            old_relative_index=result.get("old_relative_index"),
            new_relative_index=result.get("new_relative_index"),
            old_market_position=result.get("old_market_position") or "unknown",
            new_market_position=result.get("new_market_position") or "unknown",
            price_to_competitive_ceiling=result.get("price_to_competitive_ceiling"),
            price_change_from_current_pct=result.get("price_change_from_current_pct"),
            evidence=[Evidence(**item) for item in attach_evidence_ids(payload.get("evidence", []))],
            data_date=data_date,
            data_revision=revision,
        )
    except ContextUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/ai/configs")
def configs(limit: int = 200):
    rows = store.configs[: max(1, min(limit, 500))]
    return {"rows": rows, "manifest": store.manifest}


@app.get("/api/ai/tools")
def tool_catalog():
    return {"tools": sorted(tools.registry().keys()), "mode": copilot.mode}
