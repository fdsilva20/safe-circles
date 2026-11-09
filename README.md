# Safe Circles

Open-source, mobile-first platform for finding, attending and leading **Safe Circles**: confidential, peer-led listening spaces for mental wellbeing, gender equality and violence prevention. A Murmur AI and Red Dot Foundation project.

**Status: prototype (November 2026).** Working end to end with demo data; not yet piloted.

## What it does

| Pillar | Prototype |
|---|---|
| **Find** | Search circles by city, language, age group and format. Public pages show the area, not the venue. |
| **Attend** | Sign in by email link, choose a display name, confirm you are 18+, register. The exact venue is shared on confirmation. Optional anonymous feedback afterwards. |
| **Lead** | Apply, read the training modules, get approved by Red Dot Foundation, create circles and sessions, record attendance as a count. |
| **Toolkit** | Weekly topics, icebreakers, arts-based activities, listening guidelines, safeguarding protocol, attendance and feedback guidance, referral directory. Works offline once opened. English, with Hindi and Marathi for the safety-critical pages. |
| **Open data** | `/data` and `/data.json`: live anonymised totals with small-count suppression. |
| **AI (facilitators only)** | A helper grounded in the safeguarding protocol and referral directory, and AI-drafted weekly topics that go to an admin review queue. Off unless an Anthropic key is configured. Never faces participants. |

## Privacy posture

- Adults only. Age attested at sign-in; no accounts for minors.
- Participants are an email (for the sign-in link) and a display name. No legal name, phone or address.
- Only hashes of sign-in tokens and session cookies are stored.
- Venues are private until registration. Nothing said in a circle is stored. Attendance is a number.
- Feedback has no account column. A separate receipt table prevents double submission without linking answers to people. Aggregates appear only above a minimum response count.

## Run it

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
cp .env.example .env
.venv/bin/python -m scripts.seed --reset
.venv/bin/uvicorn app.main:app --reload
```

Open http://localhost:8000. Sign in with any seeded address (for example `admin@safecircles.test`, `meera@safecircles.test`, `p1@safecircles.test`); in dev the sign-in link is shown on the page because no mail server is configured.

Tests: `.venv/bin/pytest -q`

Production: PostgreSQL via `DATABASE_URL`, SMTP via `SMTP_HOST`, `ENV=prod`. See `compose.yml` and `Dockerfile`.

## Layout

- `app/` FastAPI application: `routers/` (public, auth, attend, lead, toolkit, admin, data), `services/` (content, metrics, email, ai), `models.py`, `auth.py`, `i18n.py`
- `templates/` server-rendered Jinja2 pages, mobile-first
- `static/` stylesheet, service worker, manifest, icons
- `content/toolkit/<lang>/` toolkit pages as Markdown; `content/referrals.json`
- `scripts/seed.py` demo data; `tests/` end-to-end flow tests
- `wiki/` the project knowledge base (proposal, fund assessment, decisions). Kept out of the public repository via `.gitignore`.

## Licence

Apache 2.0. See `LICENSE`.
