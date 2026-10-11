import os

try:  # carrega o ficheiro .env, se existir
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    model: str = field(default_factory=lambda: os.getenv("POLYGRAFO_MODEL", "claude-opus-5-5"))
    language: str = field(default_factory=lambda: os.getenv("POLYGRAFO_LANGUAGE", "pt"))
    max_claims: int = field(default_factory=lambda: int(os.getenv("POLYGRAFO_MAX_CLAIMS", "5")))
    # Número máximo de pesquisas web por afirmação (controla custo).
    max_searches: int = field(default_factory=lambda: int(os.getenv("POLYGRAFO_MAX_SEARCHES", "6")))
    google_factcheck_key: str | None = field(default_factory=lambda: os.getenv("GOOGLE_FACTCHECK_API_KEY") or None)
    transcribe: bool = field(default_factory=lambda: os.getenv("POLYGRAFO_TRANSCRIBE", "0") == "1")
    sources_file: str | None = field(default_factory=lambda: os.getenv("POLYGRAFO_SOURCES_FILE") or None)


def get_settings() -> Settings:
    return Settings()
