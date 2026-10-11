from polygrafo.ingest import detect_platform, parse_open_graph


def test_detect_platform():
    assert detect_platform("https://www.tiktok.com/@a/video/1") == "TikTok"
    assert detect_platform("https://m.facebook.com/story.php?id=1") == "Facebook"
    assert detect_platform("https://www.instagram.com/p/abc/") == "Instagram"
    assert detect_platform("https://x.com/a/status/1") == "X/Twitter"
    assert detect_platform("https://exemplo.pt/a") == "exemplo.pt"


def test_parse_open_graph():
    html = """<html><head><title>T</title>
      <meta property="og:title" content="Título do post">
      <meta property="og:description" content="Vacinas causam X, diz estudo">
      <meta property="og:image" content="https://cdn/img.jpg">
      <meta property="article:published_time" content="2026-01-02">
    </head></html>"""
    og = parse_open_graph(html)
    assert og["title"] == "Título do post"
    assert og["description"].startswith("Vacinas")
    assert og["image"] == "https://cdn/img.jpg"
    assert og["published"] == "2026-01-02"
