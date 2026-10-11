"""Cálculo determinístico do score de veracidade.

O modelo de linguagem só classifica cada evidência (apoia / refuta / neutro e
relevância 0-1). O número final é calculado aqui, de forma reprodutível e
auditável, para que o score não seja um valor "inventado" pelo modelo.

Fórmula (por afirmação):
  peso_i   = fiabilidade_da_fonte_i × relevância_i
  Por domínio conta apenas a evidência de maior peso em cada sentido
  (10 artigos do mesmo site não são 10 confirmações independentes).
  A = soma dos pesos que apoiam,  R = soma dos pesos que refutam
  score     = 50 + 50 × (A − R) / (A + R + K)          (0 = falso, 100 = verdadeiro)
  confiança = (A + R) / (A + R + 1)
  Se A + R < MIN_EVIDENCE → "Não verificável".

Isto é uma heurística transparente, NÃO um método cientificamente validado.
Os limiares podem e devem ser calibrados com casos reais.
"""

from __future__ import annotations

from .models import Claim, ClaimResult, Evidence

K_SMOOTHING = 0.5
MIN_EVIDENCE = 0.4
CONFIDENT = 0.5


def label_for(score: float | None) -> str:
    if score is None:
        return "Não verificável"
    if score >= 80:
        return "Verdadeiro"
    if score >= 60:
        return "Maioritariamente verdadeiro"
    if score > 40:
        return "Misto / inconclusivo"
    if score > 20:
        return "Maioritariamente falso"
    return "Falso"


def _independent_weights(evidence: list[Evidence]) -> tuple[float, float]:
    best: dict[tuple[str, str], float] = {}
    for ev in evidence:
        if ev.stance == "neutro":
            continue
        w = max(0.0, min(1.0, ev.reliability)) * max(0.0, min(1.0, ev.relevance))
        key = (ev.domain or ev.url, ev.stance)
        best[key] = max(best.get(key, 0.0), w)
    support = sum(w for (_, s), w in best.items() if s == "apoia")
    refute = sum(w for (_, s), w in best.items() if s == "refuta")
    return support, refute


def score_claim(claim: Claim, evidence: list[Evidence], reasoning: str = "", missing_context: str = "") -> ClaimResult:
    if not claim.checkable:
        return ClaimResult(
            claim=claim, score=None, confidence=0.0,
            label=f"Não verificável ({claim.kind})", reasoning=reasoning,
            missing_context=missing_context, evidence=evidence,
        )
    support, refute = _independent_weights(evidence)
    total = support + refute
    if total < MIN_EVIDENCE:
        return ClaimResult(
            claim=claim, score=None, confidence=round(total / (total + 1), 2),
            label="Não verificável (evidência insuficiente)", reasoning=reasoning,
            missing_context=missing_context, evidence=evidence,
        )
    score = 50 + 50 * (support - refute) / (total + K_SMOOTHING)
    return ClaimResult(
        claim=claim, score=round(score, 1), confidence=round(total / (total + 1), 2),
        label=label_for(score), reasoning=reasoning,
        missing_context=missing_context, evidence=evidence,
    )


def overall(results: list[ClaimResult]) -> tuple[float | None, str, float]:
    """Média dos scores ponderada pela confiança, com alerta para falsidades."""
    scored = [r for r in results if r.score is not None]
    if not scored:
        return None, "Não verificável", 0.0
    weight = sum(r.confidence for r in scored) or 1.0
    score = sum(r.score * r.confidence for r in scored) / weight
    confidence = sum(r.confidence for r in scored) / len(scored)
    label = label_for(score)
    has_confident_false = any(r.score <= 20 and r.confidence >= CONFIDENT for r in scored)
    if has_confident_false and score > 40:
        label = "Enganador (contém afirmações falsas)"
    return round(score, 1), label, round(confidence, 2)
