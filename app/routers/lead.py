"""Lead a Safe Circle: apply, training, approval status, facilitator dashboard,
create circles and sessions, record attendance as a count."""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_account, require_facilitator
from app.db import get_db
from app.deps import render, request_lang
from app.models import Account, Circle, CircleSession, FacilitatorApplication, utcnow
from app.services.content import TOOLKIT_PAGES, load_page, topics

router = APIRouter(prefix="/lead")

TRAINING_MODULES = ["listening-guidelines", "safeguarding-protocol", "attendance-and-feedback"]


def _slugify(name: str, db: Session) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "circle"
    slug, n = base, 2
    while db.scalar(select(Circle.id).where(Circle.slug == slug)):
        slug = f"{base}-{n}"
        n += 1
    return slug


@router.get("")
def lead_home(request: Request, db: Session = Depends(get_db)):
    acct = request.state.account
    application = None
    if acct:
        application = db.scalar(select(FacilitatorApplication).where(FacilitatorApplication.account_id == acct.id))
    return render(request, "lead/index.html", application=application)


@router.get("/apply")
def apply_form(request: Request, account: Account = Depends(require_account), db: Session = Depends(get_db)):
    if db.scalar(select(FacilitatorApplication).where(FacilitatorApplication.account_id == account.id)):
        return RedirectResponse("/lead", status_code=303)
    return render(request, "lead/apply.html")


@router.post("/apply")
def apply_submit(
    request: Request,
    city: str = Form(...),
    languages: list[str] = Form([]),
    motivation: str = Form(...),
    experience: str = Form(""),
    reference_contact: str = Form(""),
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
):
    if not account.age_attested or not account.display_name:
        return RedirectResponse("/profile?next=/lead/apply", status_code=303)
    if db.scalar(select(FacilitatorApplication).where(FacilitatorApplication.account_id == account.id)):
        return RedirectResponse("/lead", status_code=303)
    db.add(
        FacilitatorApplication(
            account_id=account.id,
            city=city.strip()[:80],
            languages=",".join(l for l in languages if l in ("en", "hi", "mr")) or "en",
            motivation=motivation.strip()[:3000],
            experience=experience.strip()[:3000],
            reference_contact=reference_contact.strip()[:200],
        )
    )
    db.commit()
    return RedirectResponse("/lead/training", status_code=303)


@router.get("/training")
def training(request: Request, account: Account = Depends(require_account), db: Session = Depends(get_db)):
    application = db.scalar(select(FacilitatorApplication).where(FacilitatorApplication.account_id == account.id))
    if application is None:
        return RedirectResponse("/lead/apply", status_code=303)
    lang = request_lang(request)
    modules = [load_page(slug, lang) for slug in TRAINING_MODULES]
    return render(request, "lead/training.html", application=application, modules=[m for m in modules if m])


@router.post("/training/complete")
def training_complete(request: Request, confirm: str = Form(""), account: Account = Depends(require_account), db: Session = Depends(get_db)):
    application = db.scalar(select(FacilitatorApplication).where(FacilitatorApplication.account_id == account.id))
    if application is None:
        return RedirectResponse("/lead/apply", status_code=303)
    if confirm == "on" and application.training_completed_at is None:
        application.training_completed_at = utcnow()
        db.commit()
    return RedirectResponse("/lead", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request, account: Account = Depends(require_facilitator), db: Session = Depends(get_db)):
    circles = db.scalars(
        select(Circle)
        .options(selectinload(Circle.sessions).selectinload(CircleSession.registrations))
        .where(Circle.facilitator_id == account.id)
        .order_by(Circle.name)
    ).all()
    now = utcnow()
    for c in circles:
        c.upcoming = [s for s in c.sessions if s.status == "scheduled" and s.starts_at >= now]
        c.to_record = [s for s in c.sessions if s.status == "scheduled" and s.starts_at < now]
        c.held = [s for s in c.sessions if s.status == "held"]
    return render(request, "lead/dashboard.html", circles=circles)


@router.get("/circles/new")
def circle_new(request: Request, account: Account = Depends(require_facilitator)):
    return render(request, "lead/circle_form.html", circle=None)


@router.post("/circles/new")
def circle_create(
    request: Request,
    name: str = Form(...),
    city: str = Form(...),
    area: str = Form(""),
    venue_private: str = Form(""),
    languages: list[str] = Form([]),
    format: str = Form("in_person"),
    age_band: str = Form("all_adults"),
    capacity: int = Form(10),
    description: str = Form(""),
    account: Account = Depends(require_facilitator),
    db: Session = Depends(get_db),
):
    c = Circle(
        slug=_slugify(name, db),
        name=name.strip()[:120],
        city=city.strip()[:80],
        area=area.strip()[:120],
        venue_private=venue_private.strip()[:1000],
        languages=",".join(l for l in languages if l in ("en", "hi", "mr")) or "en",
        format=format if format in ("in_person", "online", "hybrid") else "in_person",
        age_band=age_band if age_band in ("all_adults", "18_24", "25_40", "40_plus") else "all_adults",
        capacity=max(2, min(50, capacity)),
        description=description.strip()[:3000],
        facilitator_id=account.id,
    )
    db.add(c)
    db.commit()
    return RedirectResponse("/lead/dashboard", status_code=303)


def _own_circle(db: Session, circle_id: int, account: Account) -> Circle | None:
    c = db.get(Circle, circle_id)
    if c is None or (c.facilitator_id != account.id and not account.is_admin):
        return None
    return c


@router.get("/circles/{circle_id}/sessions/new")
def session_new(circle_id: int, request: Request, account: Account = Depends(require_facilitator), db: Session = Depends(get_db)):
    c = _own_circle(db, circle_id, account)
    if c is None:
        return render(request, "error.html", status=404, detail="circle not found", status_code=404)
    return render(request, "lead/session_form.html", circle=c, topics=topics(request_lang(request)))


@router.post("/circles/{circle_id}/sessions/new")
def session_create(
    circle_id: int,
    request: Request,
    starts_at: str = Form(...),
    duration_min: int = Form(90),
    topic_slug: str = Form(""),
    online_link_private: str = Form(""),
    account: Account = Depends(require_facilitator),
    db: Session = Depends(get_db),
):
    c = _own_circle(db, circle_id, account)
    if c is None:
        return render(request, "error.html", status=404, detail="circle not found", status_code=404)
    try:
        when = datetime.fromisoformat(starts_at)
    except ValueError:
        return render(request, "lead/session_form.html", circle=c, topics=topics(request_lang(request)), error=True)
    db.add(CircleSession(circle_id=c.id, starts_at=when, duration_min=max(30, min(240, duration_min)), topic_slug=topic_slug[:80], online_link_private=online_link_private.strip()[:300]))
    db.commit()
    return RedirectResponse("/lead/dashboard", status_code=303)


@router.post("/sessions/{session_id}/attendance")
def attendance(session_id: int, request: Request, attendance_count: int = Form(...), account: Account = Depends(require_facilitator), db: Session = Depends(get_db)):
    s = db.get(CircleSession, session_id)
    if s is None or _own_circle(db, s.circle_id, account) is None:
        return render(request, "error.html", status=404, detail="session not found", status_code=404)
    s.attendance_count = max(0, min(200, attendance_count))
    s.status = "held"
    db.commit()
    return RedirectResponse("/lead/dashboard", status_code=303)


@router.post("/sessions/{session_id}/cancel")
def cancel_session(session_id: int, request: Request, account: Account = Depends(require_facilitator), db: Session = Depends(get_db)):
    s = db.get(CircleSession, session_id)
    if s is None or _own_circle(db, s.circle_id, account) is None:
        return render(request, "error.html", status=404, detail="session not found", status_code=404)
    s.status = "cancelled"
    db.commit()
    return RedirectResponse("/lead/dashboard", status_code=303)
