"""ORM models.

Privacy posture, in the schema itself:
- Participants are known by email (for the magic link) and a display name.
  No legal name, no phone, no address.
- A circle's exact venue is a private column; the public side is the area.
- Feedback rows carry no account id. A separate receipt table records only
  that an account has given feedback for a session, so it cannot be given
  twice, without linking the account to the answers.
- Nothing stores what was said in a circle.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(60), default="")
    role: Mapped[str] = mapped_column(String(20), default="participant")  # participant|facilitator|admin
    age_attested: Mapped[bool] = mapped_column(Boolean, default=False)
    lang: Mapped[str] = mapped_column(String(5), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    registrations: Mapped[list["Registration"]] = relationship(back_populates="account")
    application: Mapped["FacilitatorApplication | None"] = relationship(
        back_populates="account", uselist=False, foreign_keys="FacilitatorApplication.account_id"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_facilitator(self) -> bool:
        return self.role in ("facilitator", "admin")


class AuthToken(Base):
    """Magic-link token. Only the SHA-256 hash is stored."""

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_url: Mapped[str] = mapped_column(String(300), default="/")


class AuthSession(Base):
    """Opaque server-side session. Only the hash of the cookie value is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Circle(Base):
    __tablename__ = "circles"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80), index=True)
    area: Mapped[str] = mapped_column(String(120), default="")  # general location, public
    venue_private: Mapped[str] = mapped_column(Text, default="")  # shared with confirmed registrants only
    languages: Mapped[str] = mapped_column(String(80), default="en")  # comma-separated codes
    format: Mapped[str] = mapped_column(String(20), default="in_person")  # in_person|online|hybrid
    age_band: Mapped[str] = mapped_column(String(20), default="all_adults")  # all_adults|18_24|25_40|40_plus
    description: Mapped[str] = mapped_column(Text, default="")
    capacity: Mapped[int] = mapped_column(Integer, default=10)
    facilitator_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|paused
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    facilitator: Mapped[Account] = relationship()
    sessions: Mapped[list["CircleSession"]] = relationship(back_populates="circle", order_by="CircleSession.starts_at")

    @property
    def language_list(self) -> list[str]:
        return [l for l in self.languages.split(",") if l]


class CircleSession(Base):
    __tablename__ = "circle_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    circle_id: Mapped[int] = mapped_column(ForeignKey("circles.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_min: Mapped[int] = mapped_column(Integer, default=90)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # overrides circle capacity
    topic_slug: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled|held|cancelled
    attendance_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # a count, never names
    online_link_private: Mapped[str] = mapped_column(String(300), default="")

    circle: Mapped[Circle] = relationship(back_populates="sessions")
    registrations: Mapped[list["Registration"]] = relationship(back_populates="session")

    @property
    def effective_capacity(self) -> int:
        return self.capacity if self.capacity is not None else self.circle.capacity

    @property
    def confirmed_count(self) -> int:
        return sum(1 for r in self.registrations if r.status == "confirmed")

    @property
    def spaces_left(self) -> int:
        return max(0, self.effective_capacity - self.confirmed_count)


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("session_id", "account_id", name="uq_registration"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("circle_sessions.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")  # confirmed|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    session: Mapped[CircleSession] = relationship(back_populates="registrations")
    account: Mapped[Account] = relationship(back_populates="registrations")


class Feedback(Base):
    """Anonymous by construction: no account column."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("circle_sessions.id"), index=True)
    felt_safe: Mapped[int] = mapped_column(Integer)  # 1-5
    felt_heard: Mapped[int] = mapped_column(Integer)  # 1-5
    would_return: Mapped[bool] = mapped_column(Boolean, default=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FeedbackReceipt(Base):
    """Records that an account has given feedback for a session. Not joinable to Feedback."""

    __tablename__ = "feedback_receipts"
    __table_args__ = (UniqueConstraint("session_id", "account_id", name="uq_feedback_receipt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("circle_sessions.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)


class FacilitatorApplication(Base):
    __tablename__ = "facilitator_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), unique=True, index=True)
    city: Mapped[str] = mapped_column(String(80))
    languages: Mapped[str] = mapped_column(String(80), default="en")
    motivation: Mapped[str] = mapped_column(Text, default="")
    experience: Mapped[str] = mapped_column(Text, default="")
    reference_contact: Mapped[str] = mapped_column(String(200), default="")
    training_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted")  # submitted|approved|declined
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    account: Mapped[Account] = relationship(back_populates="application", foreign_keys=[account_id])


class ConcernReport(Base):
    __tablename__ = "concern_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    circle_id: Mapped[int | None] = mapped_column(ForeignKey("circles.id"), nullable=True)
    reporter_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|closed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ToolkitDraft(Base):
    """AI-drafted toolkit content awaiting human review. Nothing here is shown
    to facilitators until an admin approves it."""

    __tablename__ = "toolkit_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    lang: Mapped[str] = mapped_column(String(5), default="en")
    kind: Mapped[str] = mapped_column(String(30), default="weekly_topic")  # weekly_topic|icebreaker|activity
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|approved|rejected
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
