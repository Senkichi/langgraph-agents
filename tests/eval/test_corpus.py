"""Tests for the corpus loader and the shipped default corpus."""

from __future__ import annotations

from pathlib import Path

from langgraph_agents.eval.corpus import (
    DEFAULT_CORPUS_DIR,
    Task,
    load_corpus,
    load_task,
    parse_task,
)


def _write(path: Path, contents: str) -> Path:
    path.write_text(contents, encoding="utf-8")
    return path


class TestParseTask:
    def test_parses_full_task(self):
        raw = (
            "# Task: Thing\n\n"
            "Do the thing.\n\n"
            "## Expected response shape (for eval reference only, not shown to pipeline)\n"
            "- Length: long\n"
            "- Key concepts: alpha, beta, gamma\n"
            "- Failure modes: hand-wave, ignores latency\n"
        )
        t = parse_task(raw, task_id="thing")
        assert t.id == "thing"
        assert t.name == "Thing"
        assert t.body == "Do the thing."
        assert t.length_hint == "long"
        assert t.key_concepts == ("alpha", "beta", "gamma")
        assert t.failure_modes == ("hand-wave", "ignores latency")

    def test_bullet_list_for_concepts(self):
        raw = (
            "# Task: B\n\n"
            "Body\n\n"
            "## Expected response shape (for eval reference only, not shown to pipeline)\n"
            "- Length: medium\n"
            "- Key concepts:\n"
            "  - foo\n"
            "  - bar baz\n"
            "- Failure modes:\n"
            "  - too short\n"
        )
        t = parse_task(raw, task_id="b")
        assert t.key_concepts == ("foo", "bar baz")
        assert t.failure_modes == ("too short",)

    def test_rubric_is_not_in_body(self):
        """The pipeline must never receive the grading rubric."""
        raw = (
            "# Task: Hidden rubric\n\n"
            "Please do X.\n\n"
            "## Expected response shape (for eval reference only, not shown to pipeline)\n"
            "- Length: short\n"
            "- Key concepts: X\n"
        )
        t = parse_task(raw, task_id="hidden")
        assert "Expected response shape" not in t.body
        assert "Key concepts" not in t.body

    def test_missing_rubric_defaults(self):
        t = parse_task("# Task: Tiny\n\nJust do it.\n", task_id="tiny")
        assert t.length_hint == "medium"
        assert t.key_concepts == ()
        assert t.failure_modes == ()

    def test_missing_title_uses_id_as_name(self):
        t = parse_task("a body with no title\n", task_id="untitled")
        assert t.name == "untitled"
        assert "a body" in t.body


class TestLoadCorpus:
    def test_loads_sorted(self, tmp_path):
        _write(tmp_path / "z.md", "# Task: Z\n\nZ body\n")
        _write(tmp_path / "a.md", "# Task: A\n\nA body\n")
        tasks = load_corpus(tmp_path)
        assert [t.id for t in tasks] == ["a", "z"]

    def test_missing_dir_raises(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            load_corpus(tmp_path / "nope")


class TestDefaultCorpus:
    def test_default_corpus_loads(self):
        tasks = load_corpus(DEFAULT_CORPUS_DIR)
        assert len(tasks) >= 5, "Plan calls for at least 5 tasks"
        ids = {t.id for t in tasks}
        assert any(tid.startswith("sanity_") for tid in ids), "need sanity-check tasks"

    def test_every_task_has_body_and_at_least_one_concept(self):
        tasks = load_corpus(DEFAULT_CORPUS_DIR)
        for t in tasks:
            assert t.body.strip(), f"{t.id}: empty body"
            assert t.key_concepts, f"{t.id}: no key concepts — concept_coverage will be meaningless"
