from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Stance = Literal["apoia", "refuta", "neutro"]


class Post(BaseModel):
    """Conteúdo de uma publicação, normalizado a partir de qualquer plataforma."""

    platform: str = "desconhecida"
    url: str | None = None
    author: str | None = None
    published_at: str | None = None
    text: str = ""
    transcript: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    # Avisos sobre limitações da extração (login obrigatório, conteúdo parcial, etc.)
    extraction_notes: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    id: int
    text: str
    kind: Literal["facto", "opiniao", "previsao", "satira"]
    checkable: bool
    context: str = ""


class Evidence(BaseModel):
    url: str
    title: str = ""
    domain: str = ""
    excerpt: str = ""
    source_tier: str = "desconhecida"
    reliability: float = 0.3
    stance: Stance = "neutro"
    relevance: float = 0.0
    note: str = ""
    # Fact-check profissional encontrado na Google Fact Check Tools API.
    is_professional_factcheck: bool = False
    factcheck_rating: str | None = None


class ClaimResult(BaseModel):
    claim: Claim
    score: float | None = Field(None, description="0 = falso, 100 = verdadeiro; None = não verificável")
    confidence: float = 0.0
    label: str
    reasoning: str = ""
    missing_context: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class Report(BaseModel):
    post: Post
    claims: list[ClaimResult]
    overall_score: float | None
    overall_label: str
    overall_confidence: float
    summary: str
    method_notes: list[str] = Field(default_factory=list)
