"""Pydantic models: what the LLM must return, and what the API exposes."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["high", "medium", "low"]
Category = Literal[
    "deposit", "payment", "price_change", "penalty", "termination",
    "access_privacy", "repairs", "utilities", "usage_rules", "general",
]


# ---- LLM output contract (structured output) ----
class ClauseAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_index: int = Field(description="Index of the clause exactly as given in the input")
    risk: RiskLevel
    category: Category
    explanation: str = Field(description="1-3 sentences in Azerbaijani, plain language, for the tenant")
    suggestion: str = Field(description="Fairer rewrite of the clause in Azerbaijani; empty string if risk is low")
    law_refs: list[str] = Field(
        description="Ids of articles from this clause's candidate_articles that directly concern it; [] if none"
    )


class ContractAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="2-3 sentence overall summary in Azerbaijani")
    assessments: list[ClauseAssessment]


# ---- API models ----
Decision = Literal["pending", "accepted", "rejected", "edited"]


class ClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    idx: int
    text: str
    risk: str | None
    category: str | None
    explanation: str | None
    suggestion: str | None
    decision: str
    user_text: str | None
    law_refs: list[str] | None = None
    law_candidates: list[str] | None = None


class LawOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    text: str
    source_url: str


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(validation_alias="public_id")  # the internal integer id is never exposed
    filename: str
    status: str
    error: str | None
    summary: str | None
    preamble: str | None
    cost_usd: float | None
    latency_ms: int | None
    invalid_refs: int | None = None
    trace: dict | None = None
    created_at: datetime
    clauses: list[ClauseOut] = []
    laws: list[LawOut] = []  # the cited articles, so the UI can show their text


class DecisionIn(BaseModel):
    decision: Decision
    user_text: str | None = None
