import pytest

from postmortem_pilot.config import load_settings
from postmortem_pilot.jsonx import extract_json
from postmortem_pilot.logs import build_corpus, chunk, redact, timestamp_key
from postmortem_pilot.samples import list_samples, recording_path


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure!\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert extract_json('<think>{"no": 1}</think> result: {"b": "x}y"} trailing') == {"b": "x}y"}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_redaction_catches_secrets():
    text = "dsn=postgres://auth_svc:S3cr3t@db:5432/auth Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijk password=hunter22 mail ops@example.com"
    clean, counts = redact(text)
    for secret in ("S3cr3t", "eyJhbGciOiJIUzI1NiJ9", "hunter22", "ops@example.com"):
        assert secret not in clean
    assert counts["url_password"] == 1 and counts["jwt"] == 1 and counts["key_value"] == 1 and counts["email"] == 1


def test_corpus_refs_chunking_and_limits():
    sources = [{"name": "a.log", "text": "x1\n\nx3\nx4\nx5"}, {"name": "b.log", "text": "y1\ny2"}]
    corpus = build_corpus(sources, max_lines=5)
    assert [l.ref for l in corpus.lines] == ["S1:1", "S1:3", "S1:4", "S1:5", "S2:1"]
    assert corpus.truncated == 1
    chunks = chunk(corpus, max_lines=2)
    assert [[l.ref for l in c] for c in chunks] == [["S1:1", "S1:3"], ["S1:4", "S1:5"], ["S2:1"]]


def test_timestamp_key_normalises_formats():
    assert timestamp_key("2026-09-02 02:51:37.880 UTC [6023] ERROR") == "2026-09-02T02:51:37.880"
    assert timestamp_key("2026-09-02T02:12:40Z Warning") == "2026-09-02T02:12:40.000"
    assert timestamp_key("no time") == ""


def test_samples_load_and_redact():
    settings = load_settings()
    samples = {s["id"]: s for s in list_samples(settings.samples_dir)}
    assert "pgbackrest-disk-full" in samples
    corpus = build_corpus(samples["pgbackrest-disk-full"]["sources"], settings.max_lines)
    joined = "\n".join(l.text for l in corpus.lines)
    assert "S3cr3t-Pg-Pass" not in joined and "q8r2lKxS0t" not in joined
    assert sum(corpus.redactions.values()) >= 2
    assert recording_path(settings.samples_dir, "../etc") is None
