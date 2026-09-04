from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    evidence_id: str
    fact_id: str = ""
    source_file: str
    record_id: str = ""
    field: str = ""
    value: Any = None
    note: str = ""


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class AskResponse(BaseModel):
    answer: str
    mode: str
    intent: str
    confidence: str
    evidence: list[Evidence]
    tool_calls: list[str] = Field(default_factory=list)
    data_date: str = "unknown"
    data_revision: str = "unknown"


class WhatIfRequest(BaseModel):
    config_id: str = Field(min_length=1, max_length=256)
    duration_days: float | None = None
    proposed_price: float = Field(gt=0)


class WhatIfResponse(BaseModel):
    answer: str = ""
    config_id: str
    proposed_price: float
    competitor_median_price: float | None
    old_relative_index: float | None
    new_relative_index: float | None
    old_market_position: str
    new_market_position: str
    price_to_competitive_ceiling: float | None
    price_change_from_current_pct: float | None = None
    evidence: list[Evidence]
    data_date: str = "unknown"
    data_revision: str = "unknown"


class ExplainRequest(BaseModel):
    config_id: str = Field(min_length=1, max_length=256)
    duration_days: float | None = None
