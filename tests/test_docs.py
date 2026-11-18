"""The docs stay consistent with the repository: shown files match, links resolve.

These tests need no database.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_FILES = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]

# Repository files that a chapter shows in full. Each must appear as a code block, word for word.
SHOWN_FILES = [
    ".env.example",
    "compose.yaml",
    "psqlrc/pg1",
    "py/01_basics.py",
    "py/02_transactions.py",
    "py/03_bulk.py",
    "py/04_orm.py",
    "py/settings.py",
    "sql/schema.sql",
    "sql/seed.sql",
]

# The comment that opens a block to say where it runs, for example "-- pg1 psql" or "# Mac".
LOCATION_COMMENT = re.compile(r"^(-- pg[12] psql|# Mac)")
FENCE = re.compile(r"^```[a-z]*\n(.*?)^```", re.DOTALL | re.MULTILINE)
LINK = re.compile(r"\]\(([^)\s]+)\)")


def code_blocks() -> list[str]:
    """Return every fenced code block in the docs, without a leading location comment.

    Returns:
        The blocks' contents.
    """
    blocks: list[str] = []
    for doc in DOC_FILES:
        for match in FENCE.finditer(doc.read_text()):
            block = match.group(1)
            first_line, _, rest = block.partition("\n")
            if LOCATION_COMMENT.match(first_line):
                block = rest
            blocks.append(block)
    return blocks


def heading_anchor(heading: str) -> str:
    """Turn a Markdown heading into the anchor GitHub generates for it.

    Args:
        heading: Heading text without the leading # characters.

    Returns:
        The anchor, for example "34-loading-and-reading-lots-of-rows".
    """
    text = heading.strip().lower().replace("\\", "")
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors_in(doc: Path) -> set[str]:
    """Collect the heading anchors of one Markdown file, ignoring code blocks.

    Args:
        doc: The Markdown file.

    Returns:
        Every anchor a link may point to.
    """
    without_code = FENCE.sub("", doc.read_text())
    anchors: set[str] = set()
    for line in without_code.splitlines():
        if line.startswith("#"):
            anchors.add(heading_anchor(line.lstrip("#")))
    return anchors


@pytest.mark.parametrize("relative_path", SHOWN_FILES)
def test_shown_file_matches_repository(relative_path: str) -> None:
    """A file the docs print in full is shown exactly as it is in the repository."""
    content = (REPO_ROOT / relative_path).read_text()
    assert content in code_blocks(), f"{relative_path} differs from the copy shown in the docs"


@pytest.mark.parametrize("doc", DOC_FILES, ids=lambda path: path.name)
def test_relative_links_resolve(doc: Path) -> None:
    """Every relative link points at an existing file and, if given, an existing heading."""
    text_without_code = FENCE.sub("", doc.read_text())
    broken: list[str] = []
    for target in LINK.findall(text_without_code):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part, _, anchor = target.partition("#")
        # A link that is only "#anchor" points into the same file.
        linked = doc
        if path_part:
            linked = (doc.parent / path_part).resolve()
        missing_file = not linked.exists()
        missing_anchor = (
            not missing_file
            and anchor != ""
            and linked.suffix == ".md"
            and anchor not in anchors_in(linked)
        )
        if missing_file or missing_anchor:
            broken.append(target)
    assert broken == []
