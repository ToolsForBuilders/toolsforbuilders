"""Linha de comandos.

Exemplos:
  python cli.py --url "https://www.tiktok.com/@conta/video/123"
  python cli.py --text "O INE diz que a inflação em Portugal foi de 10% em 2024"
  python cli.py --image captura.png --json
"""

from __future__ import annotations

import argparse
import mimetypes
import sys

from polygrafo.analyzer import AnalysisError, Polygrafo
from polygrafo.config import get_settings
from polygrafo.ingest import fetch_post
from polygrafo.models import Post, Report


def bar(score: float | None, width: int = 20) -> str:
    if score is None:
        return "[" + "?" * width + "]"
    filled = round(score / 100 * width)
    return "[" + "█" * filled + "·" * (width - filled) + "]"


def print_report(r: Report) -> None:
    print(f"\nPlataforma: {r.post.platform}  Autor: {r.post.author or '—'}  Data: {r.post.published_at or '—'}")
    for n in r.post.extraction_notes:
        print(f"  ⚠ {n}")
    print(f"\nRESULTADO GLOBAL: {bar(r.overall_score)} "
          f"{'' if r.overall_score is None else f'{r.overall_score:.0f}/100'} — {r.overall_label} "
          f"(confiança {r.overall_confidence:.0%})")
    print(r.summary)
    for c in r.claims:
        print(f"\n#{c.claim.id} \"{c.claim.text}\"")
        print(f"   {bar(c.score)} {'' if c.score is None else f'{c.score:.0f}/100'} — {c.label} (confiança {c.confidence:.0%})")
        if c.reasoning:
            print(f"   Raciocínio: {c.reasoning}")
        if c.missing_context:
            print(f"   Contexto em falta: {c.missing_context}")
        for e in c.evidence[:8]:
            mark = {"apoia": "+", "refuta": "−", "neutro": "·"}[e.stance]
            fc = f" [fact-check: {e.factcheck_rating}]" if e.is_professional_factcheck else ""
            print(f"   {mark} {e.domain} ({e.source_tier}, fiab. {e.reliability:.2f}, relev. {e.relevance:.2f}){fc}")
            print(f"     {e.url}")
            if e.excerpt:
                print(f"     “{e.excerpt[:220]}”")
    print("\nNotas de método:")
    for n in r.method_notes:
        print(f"  - {n}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Polígrafo pessoal: verificação de factos em redes sociais")
    ap.add_argument("--url", help="URL da publicação (Facebook, Instagram, TikTok, X, YouTube…)")
    ap.add_argument("--text", help="Texto da publicação (complementa ou substitui o URL)")
    ap.add_argument("--image", help="Captura de ecrã da publicação")
    ap.add_argument("--json", action="store_true", help="Saída em JSON")
    args = ap.parse_args()
    if not (args.url or args.text or args.image):
        ap.error("indique --url, --text ou --image")

    settings = get_settings()
    post = fetch_post(args.url, settings.transcribe) if args.url else Post(platform="texto colado")
    if args.text:
        post.text = (post.text + "\n\n" + args.text).strip()
    img, img_type = None, "image/png"
    if args.image:
        with open(args.image, "rb") as f:
            img = f.read()
        img_type = mimetypes.guess_type(args.image)[0] or "image/png"
    try:
        report = Polygrafo(settings).analyze(post, img, img_type)
    except AnalysisError as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
