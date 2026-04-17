"""Task corpus loader.

Each task lives in a markdown file with a strict section layout:

    # Task: <name>
    <free-form task body, shown to the pipeline>

    ## Expected response shape (for eval reference only, not shown to pipeline)
    - Length: short | medium | long
    - Key concepts: foo, bar, baz
    - Failure modes:
      - <one per line>

The "Expected response shape" section is stripped before the body is handed
to the pipeline — the pipeline must never see the grading rubric.

Key-concept lines accept comma-separated tokens on one line OR bullet lists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

LengthHint = Literal["short", "medium", "long"]

_EXPECTED_HEADER = "## Expected response shape"
# Note: these patterns use ``[ \t]*`` rather than ``\s*`` between tokens on
# the SAME line, so a bullet with no inline value ("- Key concepts:") does
# NOT accidentally consume the newline and then capture the first nested
# bullet as its value. The multiline ``$`` anchor still lets patterns apply
# per-line; intra-line whitespace just can't cross line boundaries.
_TITLE_RE = re.compile(r"^[ \t]*#[ \t]*Task[ \t]*:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_LENGTH_RE = re.compile(
    r"^[ \t]*-[ \t]*Length[ \t]*:[ \t]*(short|medium|long)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_CONCEPT_LINE_RE = re.compile(
    r"^[ \t]*-[ \t]*Key concepts[ \t]*:[ \t]*(.+?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_CONCEPT_HEADER_RE = re.compile(
    r"^[ \t]*-[ \t]*Key concepts[ \t]*:[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_FAILURE_LINE_RE = re.compile(
    r"^[ \t]*-[ \t]*Failure modes[ \t]*:[ \t]*(.+?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_FAILURE_HEADER_RE = re.compile(
    r"^[ \t]*-[ \t]*Failure modes[ \t]*:[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Task:
    id: str
    name: str
    body: str  # text shown to the pipeline — rubric stripped
    length_hint: LengthHint
    key_concepts: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    source_path: str | None = None


def _split_on_expected(raw: str) -> tuple[str, str]:
    """Return ``(body_before_rubric, rubric_section)``."""
    idx = raw.find(_EXPECTED_HEADER)
    if idx == -1:
        return raw, ""
    return raw[:idx], raw[idx:]


def _extract_nested_bullets(section: str, header_re: re.Pattern) -> list[str]:
    """When the key/failure line is just a header, scan following bullet lines.

    Requires nested bullets to be indented strictly MORE than the header
    line; a sibling-or-higher top-level bullet (e.g. ``- Failure modes:``
    appearing after ``- Key concepts:``) marks the end of the nested block.
    """
    match = header_re.search(section)
    if not match:
        return []

    # Find the indent of the header line to know what counts as "nested".
    line_start = section.rfind("\n", 0, match.start()) + 1
    header_line = section[line_start:match.end()]
    header_indent = len(header_line) - len(header_line.lstrip())

    tail = section[match.end():]
    items: list[str] = []
    for line in tail.splitlines():
        if not line.strip():
            if items:
                break
            continue
        current_indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if not stripped.startswith("-"):
            break
        if current_indent <= header_indent:
            # Sibling or higher-level bullet — we've left the nested block.
            break
        item = stripped.lstrip("-").strip()
        if item:
            items.append(item)
    return items


def parse_task(raw: str, *, task_id: str, source_path: str | None = None) -> Task:
    """Parse the markdown body of a task file into a ``Task``."""
    body_part, rubric = _split_on_expected(raw)

    title_match = _TITLE_RE.search(body_part)
    name = title_match.group(1).strip() if title_match else task_id

    # Body: everything after the title line, stripped.
    if title_match:
        body = body_part[title_match.end():].strip()
    else:
        body = body_part.strip()

    # Rubric fields — all optional with safe defaults.
    length_match = _LENGTH_RE.search(rubric)
    length_hint: LengthHint = (
        length_match.group(1).lower() if length_match else "medium"  # type: ignore[assignment]
    )

    concepts: list[str] = []
    inline = _CONCEPT_LINE_RE.search(rubric)
    if inline and inline.group(1).strip():
        concepts = [c.strip() for c in inline.group(1).split(",") if c.strip()]
    else:
        concepts = _extract_nested_bullets(rubric, _CONCEPT_HEADER_RE)

    failure_modes: list[str] = []
    fi = _FAILURE_LINE_RE.search(rubric)
    if fi and fi.group(1).strip():
        failure_modes = [c.strip() for c in fi.group(1).split(",") if c.strip()]
    else:
        failure_modes = _extract_nested_bullets(rubric, _FAILURE_HEADER_RE)

    return Task(
        id=task_id,
        name=name,
        body=body,
        length_hint=length_hint,
        key_concepts=tuple(concepts),
        failure_modes=tuple(failure_modes),
        source_path=source_path,
    )


def load_task(path: Path | str) -> Task:
    """Load a single task from a markdown file. ``task_id`` is the filename stem."""
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    return parse_task(raw, task_id=p.stem, source_path=str(p))


def load_corpus(directory: Path | str) -> list[Task]:
    """Load every ``*.md`` file in ``directory`` (non-recursive), sorted by id."""
    d = Path(directory)
    if not d.is_dir():
        raise FileNotFoundError(f"Corpus directory not found: {d}")
    files = sorted(d.glob("*.md"))
    return [load_task(f) for f in files]


DEFAULT_CORPUS_DIR = Path(__file__).parent / "corpus"
