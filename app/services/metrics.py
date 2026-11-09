"""Anonymised aggregates for the open data page.

Rules: counts only, no names; per-city counts below the threshold are
suppressed; feedback is reported only for circles with enough responses."""

from __future__ import annotations

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Account, Circle, CircleSession, FacilitatorApplication, Feedback

settings = get_settings()


def summary(db: Session) -> dict:
    active_circles = db.scalar(select(func.count()).select_from(Circle).where(Circle.status == "active")) or 0
    sessions_held = db.scalar(select(func.count()).select_from(CircleSession).where(CircleSession.status == "held")) or 0
    attendance = db.scalar(select(func.coalesce(func.sum(CircleSession.attendance_count), 0)).where(CircleSession.status == "held")) or 0
    facilitators = db.scalar(select(func.count()).select_from(Account).where(Account.role.in_(["facilitator", "admin"]))) or 0
    trained = db.scalar(
        select(func.count()).select_from(FacilitatorApplication).where(FacilitatorApplication.training_completed_at.is_not(None))
    ) or 0
    upcoming = db.scalar(select(func.count()).select_from(CircleSession).where(CircleSession.status == "scheduled")) or 0

    by_city_rows = db.execute(
        select(Circle.city, func.count()).where(Circle.status == "active").group_by(Circle.city).order_by(func.count().desc())
    ).all()
    by_city = []
    for city, n in by_city_rows:
        by_city.append({"city": city, "circles": n if n >= settings.open_data_min_count else None})

    # Feedback: per circle, only above the threshold; then averaged across those circles.
    fb_rows = db.execute(
        select(
            Circle.id,
            func.count(Feedback.id),
            func.avg(Feedback.felt_safe),
            func.avg(Feedback.felt_heard),
            func.avg(cast(Feedback.would_return, Integer)),
        )
        .join(CircleSession, CircleSession.circle_id == Circle.id)
        .join(Feedback, Feedback.session_id == CircleSession.id)
        .group_by(Circle.id)
    ).all()
    eligible = [r for r in fb_rows if r[1] >= settings.feedback_min_responses]
    feedback = None
    if eligible:
        n = sum(r[1] for r in eligible)
        feedback = {
            "responses": n,
            "circles_reporting": len(eligible),
            "felt_safe": round(sum(r[2] * r[1] for r in eligible) / n, 2),
            "felt_heard": round(sum(r[3] * r[1] for r in eligible) / n, 2),
            "would_return_pct": round(100 * sum(r[4] * r[1] for r in eligible) / n),
        }

    return {
        "active_circles": active_circles,
        "upcoming_sessions": upcoming,
        "sessions_held": sessions_held,
        "total_attendance": int(attendance),
        "facilitators": facilitators,
        "facilitators_trained": trained,
        "by_city": by_city,
        "feedback": feedback,
        "thresholds": {
            "feedback_min_responses": settings.feedback_min_responses,
            "open_data_min_count": settings.open_data_min_count,
        },
    }
