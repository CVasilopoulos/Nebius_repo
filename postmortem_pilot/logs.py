import re
from dataclasses import dataclass

REDACTIONS: list[tuple[str, re.Pattern, str]] = [
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED_JWT]"),
    ("bearer", re.compile(r"(?i)\b(bearer)\s+(?!\[REDACTED)[A-Za-z0-9._~+/=-]{16,}"), r"\1 [REDACTED_TOKEN]"),
    ("url_password", re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+):[^\s@/]+@"), r"\1:[REDACTED]@"),
    ("key_value", re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|client[_-]?secret)\s*([=:])\s*(?!\[REDACTED)[^\s,;\"']+"), r"\1\2[REDACTED]"),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[REDACTED_EMAIL]"),
]

TIMESTAMP = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:[.,](\d+))?")


@dataclass(frozen=True)
class LogLine:
    ref: str
    source_id: str
    number: int
    text: str

    @property
    def timestamp(self) -> str:
        return timestamp_key(self.text)


@dataclass
class Corpus:
    sources: list[dict]
    lines: list[LogLine]
    redactions: dict[str, int]
    truncated: int
    raw_chars: int

    def by_ref(self) -> dict[str, LogLine]:
        return {line.ref: line for line in self.lines}


def timestamp_key(text: str) -> str:
    match = TIMESTAMP.search(text or "")
    if not match:
        return ""
    return f"{match.group(1)}T{match.group(2)}.{(match.group(3) or '0')[:3].ljust(3, '0')}"


def redact(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for name, pattern, replacement in REDACTIONS:
        text, n = pattern.subn(replacement, text)
        if n:
            counts[name] = counts.get(name, 0) + n
    return text, counts


def build_corpus(sources: list[dict], max_lines: int) -> Corpus:
    lines: list[LogLine] = []
    meta: list[dict] = []
    redactions: dict[str, int] = {}
    truncated = 0
    raw_chars = 0
    for index, source in enumerate(sources, start=1):
        source_id = f"S{index}"
        text = source.get("text") or ""
        raw_chars += len(text)
        count = 0
        for number, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            if len(lines) >= max_lines:
                truncated += 1
                continue
            clean, counts = redact(raw.rstrip())
            for key, value in counts.items():
                redactions[key] = redactions.get(key, 0) + value
            lines.append(LogLine(f"{source_id}:{number}", source_id, number, clean[:2000]))
            count += 1
        meta.append({"id": source_id, "name": (source.get("name") or source_id)[:120], "lines": count})
    return Corpus(meta, lines, redactions, truncated, raw_chars)


def chunk(corpus: Corpus, max_lines: int, max_chars: int = 9000) -> list[list[LogLine]]:
    chunks: list[list[LogLine]] = []
    for source in corpus.sources:
        current: list[LogLine] = []
        size = 0
        for line in (l for l in corpus.lines if l.source_id == source["id"]):
            if current and (len(current) >= max_lines or size + len(line.text) > max_chars):
                chunks.append(current)
                current, size = [], 0
            current.append(line)
            size += len(line.text)
        if current:
            chunks.append(current)
    return chunks


def render(lines: list[LogLine]) -> str:
    return "\n".join(f"[{line.ref}] {line.text}" for line in lines)
