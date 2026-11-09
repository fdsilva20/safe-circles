"""AI support for facilitators only.

Two uses, both bounded:
1. `helper()` answers a facilitator's question about handling a situation,
   grounded in the safeguarding protocol, listening guidelines and the
   referral directory for their city.
2. `draft_topic()` writes a weekly-topic draft that goes to the admin
   review queue. Nothing it writes reaches the toolkit until a human
   approves it.

Participants never interact with this module, and nothing said inside a
circle is ever sent here. If the Anthropic client is not configured, both
functions return None and the pages fall back to static content.
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.services.content import plain_text, referrals_for

log = logging.getLogger("safecircles.ai")
settings = get_settings()

try:  # the SDK is optional at runtime
    import anthropic
except Exception:  # pragma: no cover
    anthropic = None  # type: ignore


HELPER_SYSTEM = """You support adult volunteer facilitators of Safe Circles: confidential,
peer-led listening circles for mental wellbeing, gender equality and violence
prevention, run with Red Dot Foundation in India.

You speak only to the facilitator, never to participants. You do not diagnose,
treat or give clinical advice. You help the facilitator hold the space, follow
the group guidelines, recognise when something is beyond a peer circle, and
use the safeguarding protocol and referral directory below. If the facilitator
describes a risk of immediate harm, the first thing you say is to call 112 or
local emergency services and follow the protocol's escalation steps. Keep
answers short, practical and warm. Answer in the facilitator's language.

If you are asked about anything outside facilitating a circle, say so and
bring the conversation back to the facilitator's role."""


def _client():
    if not settings.ai_enabled or anthropic is None:
        return None
    try:
        return anthropic.Anthropic()
    except Exception as exc:  # no credentials resolvable
        log.info("AI client unavailable: %s", exc)
        return None


def _text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


def helper(question: str, city: str | None, lang: str) -> str | None:
    client = _client()
    if client is None:
        return None
    refs = referrals_for(city)
    context = (
        "## Safeguarding protocol\n" + plain_text("safeguarding-protocol", lang)
        + "\n\n## Listening guidelines\n" + plain_text("listening-guidelines", lang)
        + "\n\n## Referral directory\n" + _format_refs(refs)
    )
    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=2000,
            output_config={"effort": "low"},
            system=[
                {"type": "text", "text": HELPER_SYSTEM},
                {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": f"(facilitator language: {lang}; city: {city or 'unknown'})\n\n{question}"}],
        )
    except Exception as exc:
        log.warning("AI helper failed: %s", exc)
        return None
    if response.stop_reason == "refusal":
        return None
    return _text(response) or None


DRAFT_SYSTEM = """You write draft material for the Safe Circles facilitator toolkit, used by
trained adult volunteers who run peer listening circles in India on mental
wellbeing, gender equality and violence prevention. A human reviewer at Red
Dot Foundation will edit and approve or reject what you write; it is never
published directly.

Write one weekly topic in Markdown with these sections: a title as a level-2
heading, "Why this topic", "Opening question", "Three deeper questions",
"Closing round", and "Facilitator notes" (including when to pause the topic and
refer to the safeguarding protocol). Be culturally grounded for Maharashtra,
avoid clinical language, and never ask participants to disclose details of
violence. Write in the requested language."""


def draft_topic(theme: str, lang: str) -> tuple[str, str] | None:
    client = _client()
    if client is None:
        return None
    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=3000,
            output_config={"effort": "medium"},
            system=DRAFT_SYSTEM,
            messages=[{"role": "user", "content": f"Language: {lang}. Theme: {theme}"}],
        )
    except Exception as exc:
        log.warning("AI draft failed: %s", exc)
        return None
    if response.stop_reason == "refusal":
        return None
    body = _text(response)
    if not body:
        return None
    title = next((l.lstrip("# ").strip() for l in body.splitlines() if l.startswith("## ")), theme[:120])
    return title, body


def _format_refs(refs: dict) -> str:
    lines = []
    for r in refs.get("national", []):
        lines.append(f"- {r['name']} ({r.get('phone', '')}) — {r.get('what', '')}")
    if refs.get("local"):
        lines.append(f"\nLocal to {refs['city']}:")
        for r in refs["local"]:
            lines.append(f"- {r['name']} ({r.get('phone', '')}) — {r.get('what', '')}")
    return "\n".join(lines)
