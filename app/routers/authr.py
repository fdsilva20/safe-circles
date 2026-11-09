"""Sign in by magic link, profile (display name + age attestation), sign out."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE,
    close_session,
    get_or_create_account,
    issue_magic_link,
    open_session,
    redeem_magic_link,
    require_account,
)
from app.config import get_settings
from app.db import get_db
from app.deps import render, request_lang
from app.models import Account
from app.services import email as email_svc

router = APIRouter()
settings = get_settings()


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    return render(request, "login.html", next_url=next)


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), next: str = Form("/"), db: Session = Depends(get_db)):
    email = email.strip().lower()
    if "@" not in email or len(email) > 320:
        return render(request, "login.html", next_url=next, error=True)
    acct = get_or_create_account(db, email)
    if acct.lang != request_lang(request):
        acct.lang = request_lang(request)
        db.commit()
    link = issue_magic_link(db, acct, next)
    email_svc.send(email, "Your Safe Circles sign-in link", f"Tap to sign in (valid 20 minutes, works once):\n\n{link}\n")
    # In dev with the console channel, show the link so the flow can be tried without a mailbox.
    dev_link = link if (settings.env == "dev" and not settings.smtp_host) else None
    return render(request, "login_sent.html", dev_link=dev_link)


@router.get("/auth/verify")
def verify(request: Request, token: str, db: Session = Depends(get_db)):
    result = redeem_magic_link(db, token)
    if result is None:
        return render(request, "login.html", next_url="/", expired=True, status_code=400)
    acct, next_url = result
    raw = open_session(db, acct)
    dest = next_url if (acct.display_name and acct.age_attested) else f"/profile?next={next_url}"
    resp = RedirectResponse(dest, status_code=303)
    resp.set_cookie(SESSION_COOKIE, raw, httponly=True, samesite="lax", secure=settings.env == "prod", max_age=60 * 60 * 24 * 30)
    return resp


@router.get("/profile")
def profile_form(request: Request, next: str = "/", account: Account = Depends(require_account)):
    return render(request, "profile.html", next_url=next)


@router.post("/profile")
def profile_submit(
    request: Request,
    display_name: str = Form(...),
    age_attest: str = Form(""),
    next: str = Form("/"),
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
):
    name = display_name.strip()[:60]
    if not name or age_attest != "on":
        return render(request, "profile.html", next_url=next, error=True)
    acct = db.get(Account, account.id)
    acct.display_name = name
    acct.age_attested = True
    db.commit()
    return RedirectResponse(next if next.startswith("/") else "/", status_code=303)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    close_session(db, request.cookies.get(SESSION_COOKIE))
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp
