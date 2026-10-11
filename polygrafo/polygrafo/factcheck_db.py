"""Pesquisa em fact-checks profissionais já publicados (Google Fact Check Tools API).

Documentação: https://developers.google.com/fact-check/tools/api/reference/rest/v1alpha1/claims/search
A API agrega artigos marcados com ClaimReview por organizações de fact-checking.
"""

from __future__ import annotations

import logging

import httpx

from .models import Evidence
from .sources import classify, domain_of

log = logging.getLogger(__name__)

ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


def search_factchecks(query: str, api_key: str | None, language: str = "pt", limit: int = 5) -> list[Evidence]:
    if not api_key:
        return []
    params = {"query": query[:500], "key": api_key, "pageSize": limit}
    if language:
        params["languageCode"] = language
    try:
        r = httpx.get(ENDPOINT, params=params, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("Google Fact Check API falhou: %s", e)
        return []
    out: list[Evidence] = []
    for c in r.json().get("claims", []):
        for review in c.get("claimReview", []):
            url = review.get("url")
            if not url:
                continue
            tier, rel = classify(url)
            # Quem publica ClaimReview é, por definição, um fact-checker.
            rel = max(rel, 0.9)
            publisher = (review.get("publisher") or {}).get("name", "")
            out.append(Evidence(
                url=url,
                title=review.get("title") or publisher,
                domain=domain_of(url),
                excerpt=f"Afirmação verificada: \"{c.get('text', '')}\" — Classificação: {review.get('textualRating', '?')} ({publisher})",
                source_tier="fact-checker profissional" if tier == "desconhecida" else tier,
                reliability=rel,
                is_professional_factcheck=True,
                factcheck_rating=review.get("textualRating"),
            ))
    return out[: limit * 2]
