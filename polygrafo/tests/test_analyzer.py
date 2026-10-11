"""Testa a orquestração com um cliente falso (sem chamadas reais à API)."""

import json
from types import SimpleNamespace as NS

from polygrafo.analyzer import Polygrafo
from polygrafo.config import Settings
from polygrafo.models import Post


def text(t, citations=None):
    return NS(type="text", text=t, citations=citations)


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        fmt = (kw.get("output_config") or {}).get("format")
        if fmt and "post_text" in fmt["schema"]["properties"]:
            body = {"post_text": "", "claims": [
                {"text": "A inflação em Portugal foi de 2% em 2025", "kind": "facto", "checkable": True, "context": ""},
                {"text": "O governo é péssimo", "kind": "opiniao", "checkable": False, "context": ""},
            ]}
            return NS(stop_reason="end_turn", content=[text(json.dumps(body))])
        if fmt:  # avaliação
            body = {"evidence": [
                {"url": "https://www.ine.pt/inflacao", "title": "INE", "excerpt": "IPC 2,1%", "stance": "apoia", "relevance": 0.9, "note": ""},
                {"url": "https://inventado.example/x", "title": "?", "excerpt": "?", "stance": "refuta", "relevance": 1, "note": ""},
            ], "reasoning": "Dados do INE confirmam.", "missing_context": ""}
            return NS(stop_reason="end_turn", content=[text(json.dumps(body))])
        # pesquisa com ferramentas web
        search = NS(type="web_search_tool_result", content=[NS(url="https://www.ine.pt/inflacao", title="INE")])
        return NS(stop_reason="end_turn", content=[search, text("- URL: https://www.ine.pt/inflacao | Excerto: IPC 2,1%")])


def make():
    fake = FakeMessages()
    client = NS(beta=NS(messages=fake))
    return Polygrafo(Settings(google_factcheck_key=None), client=client), fake


def test_pipeline_drops_unseen_urls_and_scores():
    p, fake = make()
    report = p.analyze(Post(platform="X/Twitter", text="Inflação foi 2% em 2025 e o governo é péssimo"))
    fact, opinion = report.claims
    assert [e.domain for e in fact.evidence] == ["ine.pt"]  # URL inventado descartado
    assert fact.score is not None and fact.score > 60
    assert opinion.score is None
    assert report.overall_score == fact.score
    # Todos os pedidos usam o fallback do lado do servidor
    assert all(c["fallbacks"] == "default" for c in fake.calls)


def test_research_resumes_after_pause_turn():
    p, fake = make()
    responses = [
        NS(stop_reason="pause_turn", content=[NS(type="web_search_tool_result", content=[NS(url="https://a.pt/1")])]),
        NS(stop_reason="end_turn", content=[text("fim")]),
    ]
    fake.create = lambda **kw: (fake.calls.append(kw), responses.pop(0))[1]
    from polygrafo.models import Claim
    notes, seen = p.research(Claim(id=1, text="x", kind="facto", checkable=True), Post())
    assert notes == "fim" and "https://a.pt/1" in seen
    assert fake.calls[1]["messages"][-1]["role"] == "assistant"
