"""Passwordless auth: email magic link, opaque server-side session.

Only SHA-256 hashes of tokens and session cookies are stored, the same
discipline as the other Murmur AI products.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Account, AuthSession, AuthToken, utcnow

settings = get_settings()

SESSION_COOKIE = "sc_session"
MAGIC_LINK_TTL = timedelta(minutes=20)
SESSION_TTL = timedelta(days=30)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def get_or_create_account(db: Session, email: str) -> Account:
    email = email.strip().lower()
    acct = db.scalar(select(Account).where(Account.email == email))
    if acct is None:
        role = "admin" if email in settings.admin_email_set else "participant"
        acct = Account(email=email, role=role)
        db.add(acct)
        db.commit()
    elif email in settings.admin_email_set and acct.role != "admin":
        acct.role = "admin"
        db.commit()
    return acct


def issue_magic_link(db: Session, account: Account, next_url: str = "/") -> str:
    raw = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            account_id=account.id,
            token_hash=_hash(raw),
            expires_at=utcnow() + MAGIC_LINK_TTL,
            next_url=next_url if next_url.startswith("/") else "/",
        )
    )
    db.commit()
    return f"{settings.public_base_url}/auth/verify?token={raw}"


def redeem_magic_link(db: Session, raw: str) -> tuple[Account, str] | None:
    tok = db.scalar(select(AuthToken).where(AuthToken.token_hash == _hash(raw)))
    if tok is None or tok.used_at is not None or tok.expires_at < utcnow():
        return None
    tok.used_at = utcnow()
    acct = db.get(Account, tok.account_id)
    db.commit()
    return acct, tok.next_url


def open_session(db: Session, account: Account) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(AuthSession(account_id=account.id, token_hash=_hash(raw), expires_at=utcnow() + SESSION_TTL))
    db.commit()
    return raw


def close_session(db: Session, raw: str | None) -> None:
    if not raw:
        return
    s = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(raw)))
    if s:
        db.delete(s)
        db.commit()


def current_account(request: Request, db: Session = Depends(get_db)) -> Account | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    s = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(raw)))
    if s is None or s.expires_at < utcnow():
        return None
    return db.get(Account, s.account_id)


def require_account(account: Account | None = Depends(current_account)) -> Account:
    if account is None:
        raise HTTPException(status_code=401, detail="sign in required")
    return account


def require_facilitator(account: Account = Depends(require_account)) -> Account:
    if not account.is_facilitator:
        raise HTTPException(status_code=403, detail="facilitator role required")
    return account


def require_admin(account: Account = Depends(require_account)) -> Account:
    if not account.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")
    return account
