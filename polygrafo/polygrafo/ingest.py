"""Extração do conteúdo de publicações em redes sociais.

Limitações reais (é importante conhecê-las):
- Meta (Facebook/Instagram) e TikTok não oferecem API pública para ler
  publicações arbitrárias de terceiros. A Meta Content Library e a TikTok
  Research API existem, mas só para investigadores aprovados.
- Muitas publicações exigem sessão iniciada; nesse caso só se obtêm os
  metadados públicos (Open Graph) ou nada.
- Extrair conteúdo automaticamente pode violar os Termos de Serviço das
  plataformas. Use para fins pessoais e com moderação.

Estratégia em cascata:
  1. yt-dlp (se instalado): descrição, autor e data de vídeos/posts de TikTok,
     Instagram, Facebook, X, YouTube, Kwai, etc.
  2. Metadados Open Graph / Twitter Card do HTML público.
  3. Alternativa sempre disponível: o utilizador cola o texto ou envia uma
     captura de ecrã (lida pelo modelo com visão).
"""

from __future__ import annotations

import logging
import os
import tempfile
from html.parser import HTMLParser

import httpx

from .models import Post
from .sources import domain_of

log = logging.getLogger(__name__)

PLATFORMS = {
    "facebook.com": "Facebook", "fb.watch": "Facebook", "instagram.com": "Instagram",
    "tiktok.com": "TikTok", "x.com": "X/Twitter", "twitter.com": "X/Twitter",
    "youtube.com": "YouTube", "youtu.be": "YouTube", "threads.net": "Threads",
    "t.me": "Telegram", "kwai.com": "Kwai", "reddit.com": "Reddit", "linkedin.com": "LinkedIn",
}

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def detect_platform(url: str) -> str:
    host = domain_of(url)
    for dom, name in PLATFORMS.items():
        if host == dom or host.endswith("." + dom):
            return name
    return host or "desconhecida"


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def parse_open_graph(html: str) -> dict[str, str]:
    p = _MetaParser()
    p.feed(html)
    m = p.meta
    return {
        "title": m.get("og:title") or m.get("twitter:title") or p.title.strip(),
        "description": m.get("og:description") or m.get("twitter:description") or m.get("description", ""),
        "image": m.get("og:image") or m.get("twitter:image", ""),
        "author": m.get("author") or m.get("article:author") or m.get("og:site_name", ""),
        "published": m.get("article:published_time", ""),
    }


def _from_ytdlp(url: str, post: Post, transcribe: bool) -> bool:
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        post.extraction_notes.append("yt-dlp não instalado: extração limitada a metadados Open Graph.")
        return False
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # yt-dlp lança muitas exceções diferentes por extrator
        post.extraction_notes.append(f"yt-dlp não conseguiu ler a publicação ({type(e).__name__}).")
        log.debug("yt-dlp falhou: %s", e)
        return False
    if info.get("_type") == "playlist" and info.get("entries"):
        info = next((e for e in info["entries"] if e), info)
    parts = [info.get("title") or "", info.get("description") or ""]
    post.text = "\n\n".join(dict.fromkeys(p.strip() for p in parts if p and p.strip()))
    post.author = info.get("uploader") or info.get("channel") or info.get("creator") or post.author
    if info.get("upload_date"):
        d = info["upload_date"]
        post.published_at = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    if info.get("thumbnail"):
        post.image_urls.append(info["thumbnail"])
    if transcribe and info.get("duration"):
        post.transcript = _transcribe(url, post)
    return bool(post.text or post.transcript)


def _transcribe(url: str, post: Post) -> str | None:
    """Transcrição local do áudio com faster-whisper (opcional, pesado)."""
    try:
        import yt_dlp  # type: ignore
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        post.extraction_notes.append("Transcrição pedida mas faster-whisper não está instalado.")
        return None
    with tempfile.TemporaryDirectory() as tmp:
        opts = {"quiet": True, "format": "bestaudio/best", "outtmpl": os.path.join(tmp, "audio.%(ext)s"), "noplaylist": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            audio = next(os.path.join(tmp, f) for f in os.listdir(tmp))
            segments, _ = WhisperModel("small", compute_type="int8").transcribe(audio)
            return " ".join(s.text.strip() for s in segments)
        except Exception as e:
            post.extraction_notes.append(f"Falha na transcrição ({type(e).__name__}).")
            return None


def _from_open_graph(url: str, post: Post) -> bool:
    try:
        r = httpx.get(url, headers={"User-Agent": BROWSER_UA, "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"},
                      follow_redirects=True, timeout=15)
    except httpx.HTTPError as e:
        post.extraction_notes.append(f"Não foi possível aceder ao URL ({type(e).__name__}).")
        return False
    if r.status_code >= 400:
        post.extraction_notes.append(f"O site respondeu HTTP {r.status_code} (provável login obrigatório ou bloqueio).")
        return False
    og = parse_open_graph(r.text)
    text = "\n\n".join(dict.fromkeys(t.strip() for t in (og["title"], og["description"]) if t and t.strip()))
    generic = {"facebook", "instagram", "tiktok", "log in", "iniciar sessão", "entrar"}
    if not text or text.lower() in generic:
        post.extraction_notes.append("A página não expõe o conteúdo sem sessão iniciada.")
        return False
    post.text = text
    post.author = post.author or og["author"] or None
    post.published_at = post.published_at or og["published"] or None
    if og["image"]:
        post.image_urls.append(og["image"])
    post.extraction_notes.append("Conteúdo obtido dos metadados públicos (pode estar truncado).")
    return True


def fetch_post(url: str, transcribe: bool = False) -> Post:
    post = Post(platform=detect_platform(url), url=url)
    if not _from_ytdlp(url, post, transcribe):
        _from_open_graph(url, post)
    if not (post.text or post.transcript):
        post.extraction_notes.append(
            "Sem conteúdo extraído. Cole o texto da publicação ou envie uma captura de ecrã."
        )
    return post
