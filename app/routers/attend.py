"""Attend a Safe Circle: register, confirmation, my circles, cancel, anonymous feedback."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_account
from app.db import get_db
from app.deps import render
from app.models import Account, CircleSession, Feedback, FeedbackReceipt, Registration, utcnow
from app.services import email as email_svc

router = APIRouter()


def _session(db: Session, session_id: int) -> CircleSession | None:
    return db.scalar(
        select(CircleSession)
        .options(selectinload(CircleSession.circle), selectinload(CircleSession.registrations))
        .where(CircleSession.id == session_id)
    )


@router.post("/sessions/{session_id}/register")
def register(session_id: int, request: Request, account: Account = Depends(require_account), db: Session = Depends(get_db)):
    s = _session(db, session_id)
    if s is None or s.status != "scheduled":
        return render(request, "error.html", status=404, detail="session not available", status_code=404)
    if not account.age_attested or not account.display_name:
        return RedirectResponse(f"/profile?next=/circles/{s.circle.slug}", status_code=303)
    existing = next((r for r in s.registrations if r.account_id == account.id), None)
    if existing and existing.status == "confirmed":
        return RedirectResponse(f"/sessions/{s.id}/confirmed", status_code=303)
    if s.spaces_left <= 0:
        return render(request, "circle.html", circle=s.circle, upcoming=[x for x in s.circle.sessions if x.status == "scheduled"], my_session_ids=set(), full_session=s.id)
    if existing:
        existing.status = "confirmed"
    else:
        db.add(Registration(session_id=s.id, account_id=account.id))
    db.commit()
    when = s.starts_at.strftime("%a %d %b %Y, %H:%M")
    where = s.circle.venue_private if s.circle.format != "online" else s.online_link_private
    email_svc.send(
        account.email,
        f"You're registered: {s.circle.name}, {when}",
        f"Hello {account.display_name},\n\nYou are registered for {s.circle.name} on {when}.\n"
        f"Where: {where}\n\nPlease read the group guidelines before you come: /guidelines\n"
        f"To cancel: /me\n",
    )
    return RedirectResponse(f"/sessions/{s.id}/confirmed", status_code=303)


@router.get("/sessions/{session_id}/confirmed")
def confirmed(session_id: int, request: Request, account: Account = Depends(require_account), db: Session = Depends(get_db)):
    s = _session(db, session_id)
    reg = s and next((r for r in s.registrations if r.account_id == account.id and r.status == "confirmed"), None)
    if not reg:
        return render(request, "error.html", status=404, detail="registration not found", status_code=404)
    return render(request, "registered.html", session=s, circle=s.circle)


@router.post("/sessions/{session_id}/cancel")
def cancel(session_id: int, account: Account = Depends(require_account), db: Session = Depends(get_db)):
    reg = db.scalar(select(Registration).where(Registration.session_id == session_id, Registration.account_id == account.id))
    if reg:
        reg.status = "cancelled"
        db.commit()
    return RedirectResponse("/me", status_code=303)


@router.get("/me")
def me(request: Request, account: Account = Depends(require_account), db: Session = Depends(get_db)):
    regs = db.scalars(
        select(Registration)
        .options(selectinload(Registration.session).selectinload(CircleSession.circle))
        .where(Registration.account_id == account.id, Registration.status == "confirmed")
    ).all()
    now = utcnow()
    upcoming = sorted([r for r in regs if r.session.starts_at >= now and r.session.status == "scheduled"], key=lambda r: r.session.starts_at)
    past = sorted([r for r in regs if r.session.starts_at < now or r.session.status == "held"], key=lambda r: r.session.starts_at, reverse=True)
    given = {fr.session_id for fr in db.scalars(select(FeedbackReceipt).where(FeedbackReceipt.account_id == account.id)).all()}
    return render(request, "me.html", upcoming=upcoming, past=past, feedback_given=given)


@router.get("/sessions/{session_id}/feedback")
def feedback_form(session_id: int, request: Request, account: Account = Depends(require_account), db: Session = Depends(get_db)):
    s = _session(db, session_id)
    if s is None:
        return render(request, "error.html", status=404, detail="session not found", status_code=404)
    already = db.scalar(select(FeedbackReceipt).where(FeedbackReceipt.session_id == s.id, FeedbackReceipt.account_id == account.id))
    return render(request, "feedback.html", session=s, circle=s.circle, already=bool(already))


@router.post("/sessions/{session_id}/feedback")
def feedback_submit(
    session_id: int,
    request: Request,
    felt_safe: int = Form(...),
    felt_heard: int = Form(...),
    would_return: str = Form(""),
    comment: str = Form(""),
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
):
    s = _session(db, session_id)
    if s is None:
        return render(request, "error.html", status=404, detail="session not found", status_code=404)
    # Must have been registered, and only once. The receipt is the only link to the account.
    registered = any(r.account_id == account.id and r.status == "confirmed" for r in s.registrations)
    already = db.scalar(select(FeedbackReceipt).where(FeedbackReceipt.session_id == s.id, FeedbackReceipt.account_id == account.id))
    if not registered or already:
        return render(request, "feedback.html", session=s, circle=s.circle, already=True)
    db.add(Feedback(session_id=s.id, felt_safe=max(1, min(5, felt_safe)), felt_heard=max(1, min(5, felt_heard)), would_return=(would_return == "on"), comment=comment.strip()[:2000]))
    db.add(FeedbackReceipt(session_id=s.id, account_id=account.id))
    db.commit()
    return render(request, "feedback.html", session=s, circle=s.circle, done=True)
