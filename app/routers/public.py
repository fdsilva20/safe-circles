"""Find a Safe Circle: home, search, circle and session pages, guidelines, about, concerns."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import render, request_lang
from app.models import Circle, CircleSession, ConcernReport, utcnow
from app.services.content import load_page

router = APIRouter()

AGE_BANDS = ["all_adults", "18_24", "25_40", "40_plus"]
FORMATS = ["in_person", "online", "hybrid"]


def _cities(db: Session) -> list[str]:
    return [c for (c,) in db.execute(select(Circle.city).where(Circle.status == "active").distinct().order_by(Circle.city)).all()]


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    upcoming = db.scalars(
        select(CircleSession)
        .join(Circle)
        .options(selectinload(CircleSession.circle), selectinload(CircleSession.registrations))
        .where(CircleSession.status == "scheduled", CircleSession.starts_at >= utcnow(), Circle.status == "active")
        .order_by(CircleSession.starts_at)
        .limit(4)
    ).all()
    return render(request, "home.html", upcoming=upcoming, cities=_cities(db))


@router.get("/find")
def find(
    request: Request,
    city: str = "",
    language: str = "",
    age: str = "",
    format: str = "",
    db: Session = Depends(get_db),
):
    q = select(Circle).options(selectinload(Circle.sessions).selectinload(CircleSession.registrations)).where(Circle.status == "active")
    if city:
        q = q.where(Circle.city == city)
    if language:
        q = q.where(Circle.languages.contains(language))
    if age in AGE_BANDS:
        q = q.where(Circle.age_band.in_([age, "all_adults"]) if age != "all_adults" else Circle.age_band == age)
    if format in FORMATS:
        q = q.where(Circle.format == format)
    circles = db.scalars(q.order_by(Circle.city, Circle.name)).all()
    now = utcnow()
    for c in circles:
        c.next_sessions = [s for s in c.sessions if s.status == "scheduled" and s.starts_at >= now][:3]
    return render(
        request,
        "find.html",
        circles=circles,
        cities=_cities(db),
        age_bands=AGE_BANDS,
        formats=FORMATS,
        f={"city": city, "language": language, "age": age, "format": format},
    )


@router.get("/circles/{slug}")
def circle(slug: str, request: Request, db: Session = Depends(get_db)):
    c = db.scalar(select(Circle).options(selectinload(Circle.sessions).selectinload(CircleSession.registrations)).where(Circle.slug == slug))
    if c is None:
        return render(request, "error.html", status=404, detail="circle not found", status_code=404)
    now = utcnow()
    upcoming = [s for s in c.sessions if s.status == "scheduled" and s.starts_at >= now]
    my_session_ids = set()
    if request.state.account:
        my_session_ids = {r.session_id for s in upcoming for r in s.registrations if r.account_id == request.state.account.id and r.status == "confirmed"}
    return render(request, "circle.html", circle=c, upcoming=upcoming, my_session_ids=my_session_ids)


@router.get("/guidelines")
def guidelines(request: Request):
    page = load_page("group-guidelines", request_lang(request))
    return render(request, "guidelines.html", page=page)


@router.get("/about")
def about(request: Request):
    return render(request, "about.html")


@router.get("/concern")
def concern_form(request: Request, circle: int | None = None, db: Session = Depends(get_db)):
    c = db.get(Circle, circle) if circle else None
    return render(request, "concern.html", circle=c)


@router.post("/concern")
def concern_submit(request: Request, text: str = Form(...), circle_id: str = Form(""), db: Session = Depends(get_db)):
    acct = request.state.account
    db.add(
        ConcernReport(
            circle_id=int(circle_id) if circle_id.isdigit() else None,
            reporter_account_id=acct.id if acct else None,
            text=text.strip()[:5000],
        )
    )
    db.commit()
    return render(request, "concern.html", sent=True, circle=None)
