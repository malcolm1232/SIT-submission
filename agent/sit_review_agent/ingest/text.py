"""Canonical text normalisation and the page-marker format (ADR-006).

The same :func:`normalise` is applied to the extracted PDF text (once, at ingest) and to every
quote before anchor matching, so "quote not found" is a property of the agent, not of the pipeline.
"""

from __future__ import annotations

import re
import unicodedata

#: Bump when :func:`normalise` changes; recorded in the manifest (``normalisation_version``).
NORMALISATION_VERSION = "1"

#: Page marker written before each page's text. Same format as spec/validate_examples.py, the
#: grader input and the robustness oracles (ADR-006, grading README §5).
PAGE_MARKER_TEMPLATE = "[[PAGE {n}]]"
PAGE_MARKER_LABEL = "[[PAGE n]]"
PAGE_MARKER_RE = re.compile(r"\[\[PAGE (\d+)\]\]")

_TYPOGRAPHIC = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", "​": "",
    "­": "",  # soft hyphen
})
_HYPHEN_BREAK = re.compile(r"(?<=[a-z])-\n(?=[a-z])")
_HSPACE = re.compile(r"[ \t\f\v]+")
_MULTI_NL = re.compile(r"\n{2,}")


def normalise(text: str) -> str:
    """Canonical form: NFKC (expands ligatures), typographic quotes and dashes to ASCII, end-of-line
    de-hyphenation (lower-case on both sides), horizontal whitespace collapsed, lines stripped,
    blank lines removed. Newlines are kept so headings stay on their own lines."""
    t = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHIC)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = _HYPHEN_BREAK.sub("", t)
    t = "\n".join(_HSPACE.sub(" ", line).strip() for line in t.split("\n"))
    return _MULTI_NL.sub("\n", t).strip("\n")


def normalise_quote(quote: str) -> str:
    """A quote in canonical form on a single line (all whitespace collapsed to one space)."""
    return " ".join(normalise(quote).split())


def flatten_for_match(text: str) -> str:
    """Replace newlines by spaces. Same length as ``text``, so match offsets map back 1:1."""
    return text.replace("\n", " ")


def quote_tokens(quote: str) -> int:
    """Number of whitespace-separated tokens (taxonomy ``anchor_rules.min_quote_tokens``)."""
    return len(quote.split())


def page_marker(n: int) -> str:
    return PAGE_MARKER_TEMPLATE.format(n=n)
