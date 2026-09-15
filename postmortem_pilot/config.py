import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    extract_model: str
    reason_model: str
    verify_model: str
    max_lines: int
    chunk_lines: int
    extract_concurrency: int
    verify_concurrency: int
    extract_max_tokens: int
    reason_max_tokens: int
    verify_max_tokens: int
    extract_thinking: bool
    verify_thinking: bool
    usage_log: str | None
    runs_per_ip_per_day: int
    samples_dir: Path
    static_dir: Path

    @property
    def live(self) -> bool:
        return bool(self.api_key)


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        api_key=env("NEBIUS_API_KEY", ""),
        base_url=env("TOKEN_FACTORY_BASE_URL", "https://api.tokenfactory.nebius.com/v1"),
        extract_model=env("EXTRACT_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
        reason_model=env("REASON_MODEL", "nvidia/Nemotron-3-Ultra-550b-a55b"),
        verify_model=env("VERIFY_MODEL", "nvidia/Nemotron-3_5-Lightning"),
        max_lines=int(env("MAX_LINES", "1500")),
        chunk_lines=int(env("CHUNK_LINES", "60")),
        extract_concurrency=int(env("EXTRACT_CONCURRENCY", "6")),
        verify_concurrency=int(env("VERIFY_CONCURRENCY", "8")),
        extract_max_tokens=int(env("EXTRACT_MAX_TOKENS", "2500")),
        reason_max_tokens=int(env("REASON_MAX_TOKENS", "9000")),
        verify_max_tokens=int(env("VERIFY_MAX_TOKENS", "600")),
        extract_thinking=env("EXTRACT_THINKING", "false").lower() == "true",
        verify_thinking=env("VERIFY_THINKING", "false").lower() == "true",
        usage_log=env("USAGE_LOG") or None,
        runs_per_ip_per_day=int(env("RUNS_PER_IP_PER_DAY", "20")),
        samples_dir=Path(env("SAMPLES_DIR", str(ROOT / "samples"))),
        static_dir=ROOT / "static",
    )
