from polygrafo.models import Claim, Evidence
from polygrafo.scoring import label_for, overall, score_claim

CLAIM = Claim(id=1, text="x", kind="facto", checkable=True)


def ev(domain, stance, rel=0.9, relevance=1.0):
    return Evidence(url=f"https://{domain}/a", domain=domain, stance=stance, reliability=rel, relevance=relevance)


def test_no_evidence_is_unverifiable():
    r = score_claim(CLAIM, [])
    assert r.score is None and r.label.startswith("Não verificável")


def test_opinion_is_not_scored():
    r = score_claim(Claim(id=1, text="x", kind="opiniao", checkable=False), [ev("ine.pt", "apoia")])
    assert r.score is None


def test_strong_refutation_is_false():
    r = score_claim(CLAIM, [ev("ine.pt", "refuta"), ev("poligrafo.sapo.pt", "refuta"), ev("publico.pt", "refuta", 0.75)])
    assert r.score is not None and r.score < 20 and r.label == "Falso"


def test_strong_support_is_true():
    r = score_claim(CLAIM, [ev("ine.pt", "apoia"), ev("reuters.com", "apoia", 0.75), ev("publico.pt", "apoia", 0.75)])
    assert r.score >= 80 and r.label == "Verdadeiro"


def test_same_domain_counts_once():
    many = [Evidence(url=f"https://blog.com/{i}", domain="blog.com", stance="apoia", reliability=0.3, relevance=1) for i in range(10)]
    one = score_claim(CLAIM, many[:1])
    ten = score_claim(CLAIM, many)
    assert one.score == ten.score


def test_low_reliability_sources_insufficient():
    r = score_claim(CLAIM, [ev("facebook.com", "apoia", 0.1), ev("tiktok.com", "apoia", 0.1)])
    assert r.score is None


def test_mixed_evidence_is_inconclusive():
    r = score_claim(CLAIM, [ev("ine.pt", "apoia"), ev("who.int", "refuta")])
    assert 40 < r.score < 60


def test_overall_flags_false_claims():
    t = score_claim(CLAIM, [ev("ine.pt", "apoia"), ev("reuters.com", "apoia"), ev("bbc.com", "apoia")])
    f = score_claim(CLAIM, [ev("ine.pt", "refuta"), ev("who.int", "refuta")])
    t2 = score_claim(CLAIM, [ev("ine.pt", "apoia"), ev("reuters.com", "apoia"), ev("bbc.com", "apoia"), ev("dn.pt", "apoia")])
    score, label, _ = overall([t, t2, f])
    assert score > 40 and label.startswith("Enganador")


def test_labels():
    assert label_for(None) == "Não verificável"
    assert label_for(90) == "Verdadeiro" and label_for(10) == "Falso" and label_for(50).startswith("Misto")
