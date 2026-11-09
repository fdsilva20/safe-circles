"""Facilitator toolkit: content pages, referral directory, AI helper, topic drafts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_facilitator
from app.config import get_settings
from app.db import get_db
from app.deps import render, request_lang
from app.models import Account, Circle, FacilitatorApplication, ToolkitDraft
from app.services import ai
from app.services.content import list_pages, load_page, plain_text, referrals, referrals_for

router = APIRouter(prefix="/toolkit")
settings = get_settings()


def _facilitator_city(db: Session, account: Account) -> str | None:
    c = db.scalar(select(Circle.city).where(Circle.facilitator_id == account.id).limit(1))
    if c:
        return c
    app_ = db.scalar(select(FacilitatorApplication.city).where(FacilitatorApplication.account_id == account.id))
    return app_


@router.get("")
def index(request: Request):
    lang = request_lang(request)
    approved = []
    return render(request, "toolkit/index.html", pages=list_pages(lang), approved_drafts=approved)


@router.get("/referrals")
def referral_directory(request: Request):
    return render(request, "toolkit/referrals.html", data=referrals())


@router.get("/helper")
def helper_form(request: Request, account: Account = Depends(require_facilitator), db: Session = Depends(get_db)):
    return render(request, "toolkit/helper.html", city=_facilitator_city(db, account), ai_available=ai._client() is not None)


@router.post("/helper")
def helper_ask(request: Request, question: str = Form(...), account: Account = Depends(require_facilitator), db: Session = Depends(get_db)):
    lang = request_lang(request)
    city = _facilitator_city(db, account)
    answer = ai.helper(question.strip()[:2000], city, lang) if question.strip() else None
    fallback = None
    if answer is None:
        fallback = {"protocol": load_page("safeguarding-protocol", lang), "refs": referrals_for(city)}
    return render(request, "toolkit/helper.html", city=city, question=question, answer=answer, fallback=fallback, ai_available=ai._client() is not None)


@router.get("/drafts")
def drafts(request: Request, account: Account = Depends(require_facilitator), db: Session = Depends(get_db)):
    mine = db.scalars(select(ToolkitDraft).where(ToolkitDraft.requested_by == account.id).order_by(ToolkitDraft.created_at.desc())).all()
    approved = db.scalars(select(ToolkitDraft).where(ToolkitDraft.status == "approved").order_by(ToolkitDraft.created_at.desc())).all()
    return render(request, "toolkit/drafts.html", mine=mine, approved=approved, ai_available=ai._client() is not None)


@router.post("/drafts")
def draft_create(request: Request, theme: str = Form(...), account: Account = Depends(require_facilitator), db: Session = Depends(get_db)):
    lang = request_lang(request)
    result = ai.draft_topic(theme.strip()[:500], lang)
    if result is None:
        return RedirectResponse("/toolkit/drafts?failed=1", status_code=303)
    title, body = result
    db.add(ToolkitDraft(lang=lang, kind="weekly_topic", title=title[:200], body=body, prompt=theme.strip()[:500], requested_by=account.id))
    db.commit()
    return RedirectResponse("/toolkit/drafts?sent=1", status_code=303)


@router.get("/drafts/{draft_id}")
def draft_view(draft_id: int, request: Request, account: Account = Depends(require_facilitator), db: Session = Depends(get_db)):
    d = db.get(ToolkitDraft, draft_id)
    if d is None or (d.status != "approved" and d.requested_by != account.id and not account.is_admin):
        return render(request, "error.html", status=404, detail="draft not found", status_code=404)
    import markdown as md

    return render(request, "toolkit/draft.html", draft=d, html=md.markdown(d.body))


@router.get("/{slug}")
def page(slug: str, request: Request):
    p = load_page(slug, request_lang(request))
    if p is None:
        return render(request, "error.html", status=404, detail="page not found", status_code=404)
    return render(request, "toolkit/page.html", page=p)
