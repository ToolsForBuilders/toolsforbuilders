from polygrafo.sources import classify, domain_of


def test_domain_strips_www():
    assert domain_of("https://www.publico.pt/x") == "publico.pt"


def test_tiers():
    assert classify("https://www.ine.pt/xportal")[1] >= 0.9
    assert classify("https://poligrafo.sapo.pt/fact-check/x")[0] == "fact-checker profissional"
    assert classify("https://www.tiktok.com/@a/video/1")[1] <= 0.1
    assert classify("https://pt.wikipedia.org/wiki/X")[0].startswith("enciclopédia")
    assert classify("https://random-site.example")[0] == "desconhecida"


def test_path_specific_entry_wins():
    assert classify("https://www.reuters.com/fact-check/abc")[0] == "fact-checker profissional"
    assert classify("https://www.reuters.com/world/abc")[0].startswith("agência")


def test_gov_suffix():
    assert classify("https://www.fda.gov/x")[1] >= 0.85


def test_custom_sources_file(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"local": {"reliability": 0.8, "domains": ["meujornal.pt"]}}', encoding="utf-8")
    assert classify("https://meujornal.pt/a", str(p)) == ("local", 0.8)
