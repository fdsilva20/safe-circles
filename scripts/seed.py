"""Seed demo data: an admin, facilitators, circles in Satara, Pune and Mumbai,
upcoming and past sessions, registrations and anonymous feedback.

    .venv/bin/python -m scripts.seed            # adds demo data (idempotent)
    .venv/bin/python -m scripts.seed --reset    # drops and recreates the database first

Every account is a demo account; the emails are not real.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db import Base, SessionLocal, engine, init_db
from app.models import (
    Account,
    Circle,
    CircleSession,
    FacilitatorApplication,
    Feedback,
    FeedbackReceipt,
    Registration,
)

random.seed(7)

ADMIN = ("admin@safecircles.test", "RDF Safeguarding")
FACILITATORS = [
    ("meera@safecircles.test", "Meera", "Mumbai", "en,hi,mr"),
    ("asha@safecircles.test", "Asha", "Mumbai", "hi,mr"),
    ("priya@safecircles.test", "Priya", "Pune", "en,mr"),
    ("sunita@safecircles.test", "Sunita", "Pune", "mr,hi"),
    ("kavita@safecircles.test", "Kavita", "Satara", "mr"),
    ("rohan@safecircles.test", "Rohan", "Mumbai", "en,hi"),
]
PARTICIPANTS = [(f"p{i}@safecircles.test", name) for i, name in enumerate(
    ["Neha", "Pooja", "Sana", "Deepa", "Anjali", "Rina", "Farah", "Jyoti", "Shweta", "Tara", "Aarti", "Lata", "Nisha", "Vidya", "Zoya", "Gauri", "Komal", "Mina", "Rupa", "Seema"], 1)]

CIRCLES = [
    # slug, name, city, area, venue_private, languages, format, age_band, description, capacity, facilitator email, weekday, hour
    ("dadar-evening-circle", "Dadar Evening Circle", "Mumbai", "Dadar West", "Community hall, 2nd floor, next to the Portuguese Church, Dadar West. Ring bell marked 'Hall'.", "en,hi,mr", "in_person", "all_adults", "A weekly circle for women and men of all ages after work hours. We meet, listen, and leave lighter.", 12, "meera@safecircles.test", 2, 19),
    ("dharavi-women-s-circle", "Dharavi Women's Circle", "Mumbai", "Dharavi", "Sakhi Kendra room, Lane 4, near the municipal school. Ask for Asha.", "hi,mr", "in_person", "all_adults", "A circle for women in Hindi and Marathi. Children may wait in the next room with a volunteer.", 10, "asha@safecircles.test", 5, 16),
    ("young-mumbai-online", "Young Mumbai (online)", "Mumbai", "Online", "", "en,hi", "online", "18_24", "For 18 to 24 year olds across Mumbai who prefer to join from home. Camera optional.", 14, "rohan@safecircles.test", 3, 20),
    ("kothrud-saturday-circle", "Kothrud Saturday Circle", "Pune", "Kothrud", "Reading room above the library on Paud Road. Entrance from the side lane.", "en,mr", "in_person", "all_adults", "Saturday mornings. A mixed circle with an arts-based activity every other week.", 10, "priya@safecircles.test", 5, 10),
    ("hadapsar-mahila-circle", "Hadapsar Mahila Circle", "Pune", "Hadapsar", "Anganwadi hall, Sade Satra Nali. Enter from the back gate.", "mr,hi", "in_person", "25_40", "Marathi-first circle for women aged 25 to 40.", 10, "sunita@safecircles.test", 1, 15),
    ("satara-bazaar-circle", "Satara Bazaar Circle", "Satara", "Near Rajwada", "Upstairs room at the Mahila Mandal office near Rajwada bus stand.", "mr", "in_person", "all_adults", "Satara's first Safe Circle, in Marathi, every Sunday afternoon.", 10, "kavita@safecircles.test", 6, 16),
    ("satara-college-circle", "Satara College Circle", "Satara", "College area", "Seminar room B, Arts building. Only for students aged 18 and above.", "mr,en", "hybrid", "18_24", "For college students aged 18 and above. Join in person or online.", 12, "kavita@safecircles.test", 4, 17),
]

TOPICS = ["who-listens-to-me", "saying-no", "safe-and-unsafe-places", "what-i-was-told-a-girl-should-be", "when-i-feel-low", "friendship-and-solidarity"]


def account(db, email, name, role="participant", lang="en"):
    a = db.scalar(select(Account).where(Account.email == email))
    if a is None:
        a = Account(email=email, display_name=name, role=role, age_attested=True, lang=lang)
        db.add(a)
        db.flush()
    return a


def next_weekday(base: datetime, weekday: int, hour: int) -> datetime:
    days = (weekday - base.weekday()) % 7 or 7
    return (base + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)


def main(reset: bool) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    init_db()
    db = SessionLocal()
    try:
        if db.scalar(select(Circle.id)):
            print("database already has circles; nothing to do (use --reset to start over)")
            return
        admin = account(db, *ADMIN, role="admin")
        facs = {}
        for email, name, city, langs in FACILITATORS:
            a = account(db, email, name, role="facilitator", lang=langs.split(",")[0])
            facs[email] = a
            db.add(FacilitatorApplication(account_id=a.id, city=city, languages=langs, motivation="Seeded demo facilitator.", training_completed_at=datetime.now() - timedelta(days=60), status="approved", reviewed_by=admin.id, reviewed_at=datetime.now() - timedelta(days=55)))
        # one applicant mid-way, so the admin page has something to approve
        applicant = account(db, "applicant@safecircles.test", "Leela")
        db.add(FacilitatorApplication(account_id=applicant.id, city="Pune", languages="mr,en", motivation="I have run a self-help group for five years and want to bring listening circles to Wagholi.", experience="SHG coordinator since 2021.", reference_contact="Sunita (Hadapsar circle)", training_completed_at=datetime.now() - timedelta(days=2)))
        participants = [account(db, e, n) for e, n in PARTICIPANTS]
        db.flush()

        now = datetime.now()
        for slug, name, city, area, venue, langs, fmt, age, desc, cap, fac_email, weekday, hour in CIRCLES:
            c = Circle(slug=slug, name=name, city=city, area=area, venue_private=venue, languages=langs, format=fmt, age_band=age, description=desc, capacity=cap, facilitator_id=facs[fac_email].id)
            db.add(c)
            db.flush()
            # past sessions (held) with attendance and feedback
            first_future = next_weekday(now, weekday, hour)
            for k in range(6, 0, -1):
                when = first_future - timedelta(days=7 * k)
                attendance = random.randint(4, cap)
                s = CircleSession(circle_id=c.id, starts_at=when, topic_slug=TOPICS[k % len(TOPICS)], status="held", attendance_count=attendance, online_link_private="https://meet.jit.si/safecircles-demo" if fmt != "in_person" else "")
                db.add(s)
                db.flush()
                regs = random.sample(participants, min(attendance, len(participants)))
                for p in regs:
                    db.add(Registration(session_id=s.id, account_id=p.id, status="confirmed"))
                    if random.random() < 0.7:
                        db.add(Feedback(session_id=s.id, felt_safe=random.choice([4, 4, 5, 5, 5, 3]), felt_heard=random.choice([4, 5, 5, 4, 3]), would_return=random.random() < 0.9, comment=random.choice(["", "", "Thank you.", "Felt lighter afterwards.", "More time for the closing round please."])))
                        db.add(FeedbackReceipt(session_id=s.id, account_id=p.id))
            # upcoming sessions
            for k in range(0, 3):
                when = first_future + timedelta(days=7 * k)
                s = CircleSession(circle_id=c.id, starts_at=when, topic_slug=TOPICS[(k + 1) % len(TOPICS)], online_link_private="https://meet.jit.si/safecircles-demo" if fmt != "in_person" else "")
                db.add(s)
                db.flush()
                for p in random.sample(participants, random.randint(2, max(2, cap - 3))):
                    db.add(Registration(session_id=s.id, account_id=p.id, status="confirmed"))
        db.commit()
        print("seeded: 1 admin, 6 facilitators, 1 applicant, 20 participants, 7 circles, 63 sessions")
        print("sign in as admin@safecircles.test, meera@safecircles.test or p1@safecircles.test (dev shows the link)")
    finally:
        db.close()


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
