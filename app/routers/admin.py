"""Admin (Red Dot Foundation): approve facilitators, review AI drafts, read concerns."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin
from app.db import get_db
from app.deps import render
from app.models import Account, ConcernReport, FacilitatorApplication, ToolkitDraft, utcnow

router = APIRouter(prefix="/admin")


@router.get("")
def index(request: Request, account: Account = Depends(require_admin), db: Session = Depends(get_db)):
    applications = db.scalars(
        select(FacilitatorApplication).options(selectinload(FacilitatorApplication.account)).order_by(FacilitatorApplication.created_at.desc())
    ).all()
    drafts = db.scalars(select(ToolkitDraft).where(ToolkitDraft.status == "draft").order_by(ToolkitDraft.created_at)).all()
    concerns = db.scalars(select(ConcernReport).where(ConcernReport.status == "open").order_by(ConcernReport.created_at.desc())).all()
    return render(request, "admin/index.html", applications=applications, drafts=drafts, concerns=concerns)


@router.post("/applications/{app_id}/decide")
def decide(app_id: int, decision: str = Form(...), note: str = Form(""), account: Account = Depends(require_admin), db: Session = Depends(get_db)):
    a = db.get(FacilitatorApplication, app_id)
    if a is None:
        return RedirectResponse("/admin", status_code=303)
    if decision == "approve" and a.training_completed_at is not None:
        a.status = "approved"
        applicant = db.get(Account, a.account_id)
        if applicant.role == "participant":
            applicant.role = "facilitator"
    elif decision == "decline":
        a.status = "declined"
    a.reviewed_by = account.id
    a.reviewed_at = utcnow()
    a.review_note = note.strip()[:1000]
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/drafts/{draft_id}/decide")
def decide_draft(draft_id: int, decision: str = Form(...), account: Account = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(ToolkitDraft, draft_id)
    if d is not None and decision in ("approve", "reject"):
        d.status = "approved" if decision == "approve" else "rejected"
        d.reviewed_by = account.id
        d.reviewed_at = utcnow()
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/concerns/{concern_id}/close")
def close_concern(concern_id: int, account: Account = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(ConcernReport, concern_id)
    if c is not None:
        c.status = "closed"
        c.closed_at = utcnow()
        db.commit()
    return RedirectResponse("/admin", status_code=303)
