"""Classificação heurística da fiabilidade de fontes por domínio.

AVISO: estas listas são um ponto de partida editável, não uma classificação
oficial. Fiabilidade de um domínio não garante a exatidão de um artigo concreto.
Pode substituir/estender as listas com um ficheiro JSON (POLYGRAFO_SOURCES_FILE)
no formato {"tier_name": {"reliability": 0.9, "domains": ["exemplo.pt"]}}.
Lista atual de signatários IFCN: https://ifcncodeofprinciples.poynter.org/signatories
"""

from __future__ import annotations

import json
from functools import lru_cache
from urllib.parse import urlparse

DEFAULT_TIERS: dict[str, dict] = {
    "fact-checker profissional": {
        "reliability": 0.95,
        "domains": [
            "poligrafo.sapo.pt", "observador.pt/factchecks", "snopes.com", "politifact.com",
            "factcheck.org", "fullfact.org", "maldita.es", "newtral.es", "aosfatos.org",
            "lupa.uol.com.br", "factuel.afp.com", "checamos.afp.com", "factcheck.afp.com",
            "reuters.com/fact-check", "apnews.com/hub/ap-fact-check", "correctiv.org",
            "leadstories.com", "efe.com/verifica", "europeandigitalmediaobservatory.eu",
        ],
    },
    "fonte oficial / científica": {
        "reliability": 0.9,
        "domains": [
            "ine.pt", "pordata.pt", "diariodarepublica.pt", "dre.pt", "portugal.gov.pt", "parlamento.pt",
            "bportugal.pt", "dgs.pt", "sns.gov.pt", "ipma.pt", "europa.eu", "who.int", "un.org",
            "oecd.org", "imf.org", "worldbank.org", "ecdc.europa.eu", "ema.europa.eu", "cdc.gov",
            "nih.gov", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "nature.com", "science.org",
            "thelancet.com", "nejm.org", "bmj.com", "cochranelibrary.com", "ipcc.ch", "nasa.gov",
            "noaa.gov", "ibge.gov.br",
        ],
    },
    "agência / media de referência": {
        "reliability": 0.75,
        "domains": [
            "lusa.pt", "reuters.com", "apnews.com", "afp.com", "bbc.com", "bbc.co.uk", "publico.pt",
            "expresso.pt", "rtp.pt", "observador.pt", "dn.pt", "jn.pt", "sicnoticias.pt",
            "cnnportugal.iol.pt", "tsf.pt", "eco.sapo.pt", "jornaldenegocios.pt", "elpais.com",
            "lemonde.fr", "theguardian.com", "nytimes.com", "washingtonpost.com", "ft.com",
            "economist.com", "dw.com", "euronews.com", "folha.uol.com.br", "g1.globo.com",
        ],
    },
    "enciclopédia / referência secundária": {
        "reliability": 0.55,
        "domains": ["wikipedia.org", "britannica.com", "ourworldindata.org"],
    },
    "rede social / conteúdo de utilizadores": {
        "reliability": 0.1,
        "domains": [
            "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com", "youtube.com",
            "reddit.com", "t.me", "threads.net", "kwai.com", "blogspot.com", "medium.com",
            "substack.com", "wordpress.com", "quora.com",
        ],
    },
}

UNKNOWN_TIER = ("desconhecida", 0.3)
# Sufixos institucionais genéricos (avaliados depois das listas explícitas).
SUFFIX_TIERS = [
    (".gov", "fonte oficial / científica", 0.85),
    (".gov.pt", "fonte oficial / científica", 0.85),
    (".gov.br", "fonte oficial / científica", 0.85),
    (".edu", "académica", 0.7),
    (".ac.uk", "académica", 0.7),
]


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


@lru_cache(maxsize=4)
def _load_tiers(sources_file: str | None) -> dict[str, dict]:
    tiers = {k: {"reliability": v["reliability"], "domains": list(v["domains"])} for k, v in DEFAULT_TIERS.items()}
    if sources_file:
        with open(sources_file, encoding="utf-8") as f:
            for name, spec in json.load(f).items():
                tiers[name] = {"reliability": float(spec["reliability"]), "domains": list(spec.get("domains", []))}
    return tiers


def classify(url: str, sources_file: str | None = None) -> tuple[str, float]:
    """Devolve (nome do nível, fiabilidade 0-1) para um URL.

    Entradas com caminho (ex. "reuters.com/fact-check") têm prioridade sobre o
    domínio simples, e a correspondência mais específica ganha.
    """
    parsed = urlparse(url)
    host = domain_of(url)
    host_path = host + (parsed.path or "").rstrip("/").lower()

    best: tuple[int, str, float] | None = None
    for name, spec in _load_tiers(sources_file).items():
        for entry in spec["domains"]:
            entry = entry.lower()
            entry_host, _, entry_path = entry.partition("/")
            host_ok = host == entry_host or host.endswith("." + entry_host)
            if not host_ok:
                continue
            if entry_path and not host_path.startswith(host + "/" + entry_path):
                continue
            specificity = len(entry)
            if best is None or specificity > best[0]:
                best = (specificity, name, spec["reliability"])
    if best:
        return best[1], best[2]
    for suffix, name, rel in SUFFIX_TIERS:
        if host.endswith(suffix):
            return name, rel
    return UNKNOWN_TIER
