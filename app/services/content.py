"""Toolkit content: markdown files per language under content/toolkit/<lang>/,
plus the referral directory (content/referrals.json) and group guidelines.

A page missing in one language falls back to English and says so."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import markdown

from app.deps import BASE_DIR

CONTENT_DIR = BASE_DIR / "content"
TOOLKIT_DIR = CONTENT_DIR / "toolkit"

# Order and ids of toolkit sections. Titles come from the files' first heading.
TOOLKIT_PAGES = [
    "weekly-topics",
    "icebreakers",
    "arts-activities",
    "listening-guidelines",
    "safeguarding-protocol",
    "attendance-and-feedback",
]

_md = markdown.Markdown(extensions=["tables", "sane_lists"])


@dataclass
class Page:
    slug: str
    title: str
    html: str
    lang: str
    fallback: bool  # True when shown in English because the language is missing


def _read(lang: str, slug: str) -> str | None:
    p = TOOLKIT_DIR / lang / f"{slug}.md"
    return p.read_text(encoding="utf-8") if p.exists() else None


def _title(text: str, slug: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else slug.replace("-", " ").title()


def load_page(slug: str, lang: str) -> Page | None:
    if slug not in TOOLKIT_PAGES and slug != "group-guidelines":
        return None
    text = _read(lang, slug)
    fallback = False
    if text is None:
        text = _read("en", slug)
        fallback = lang != "en"
    if text is None:
        return None
    _md.reset()
    return Page(slug=slug, title=_title(text, slug), html=_md.convert(text), lang=lang, fallback=fallback)


def list_pages(lang: str) -> list[Page]:
    pages = [load_page(s, lang) for s in TOOLKIT_PAGES]
    return [p for p in pages if p]


def plain_text(slug: str, lang: str = "en") -> str:
    """Raw markdown for a page, used as context for the facilitator helper."""
    return _read(lang, slug) or _read("en", slug) or ""


def referrals() -> dict:
    p = CONTENT_DIR / "referrals.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"national": [], "cities": {}}


def referrals_for(city: str | None) -> dict:
    data = referrals()
    return {"national": data.get("national", []), "city": city, "local": data.get("cities", {}).get(city or "", [])}


def topics(lang: str) -> list[tuple[str, str]]:
    """(slug, title) pairs for the weekly topics, read from the ## headings."""
    text = _read(lang, "weekly-topics") or _read("en", "weekly-topics") or ""
    out = []
    for m in re.finditer(r"^##\s+(.+)$", text, re.M):
        title = m.group(1).strip()
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or f"topic-{len(out)+1}"
        out.append((slug, title))
    return out
