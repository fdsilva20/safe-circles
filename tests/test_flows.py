"""End-to-end flow tests against a throwaway SQLite database."""

from __future__ import annotations

import os
import re
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["ENV"] = "dev"
os.environ["ADMIN_EMAILS"] = "admin@test.local"
os.environ["AI_ENABLED"] = "false"
os.environ["FEEDBACK_MIN_RESPONSES"] = "2"

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def sign_in(client: TestClient, email: str, name: str = "Demo") -> None:
    r = client.post("/login", data={"email": email, "next": "/"})
    assert r.status_code == 200
    link = re.search(r'href="(http://[^"]+/auth/verify\?token=[^"]+)"', r.text).group(1)
    r = client.get(link.replace("http://localhost:8000", ""), follow_redirects=False)
    assert r.status_code == 303
    client.post("/profile", data={"display_name": name, "age_attest": "on", "next": "/"})


def test_public_pages(client):
    for path in ["/", "/find", "/guidelines", "/about", "/toolkit", "/toolkit/safeguarding-protocol", "/toolkit/referrals", "/data", "/data.json", "/concern"]:
        r = client.get(path)
        assert r.status_code == 200, path


def test_language_switch_and_fallback(client):
    r = client.get("/toolkit/safeguarding-protocol?lang=mr")
    assert "सुरक्षा" in r.text
    r = client.get("/toolkit/icebreakers?lang=mr")
    assert "translation pending" in r.text  # English fallback is declared
    client.get("/?lang=en")  # reset the language cookie for the tests that follow


def test_full_lead_and_attend_flow(client):
    # Facilitator applies, trains, is approved, creates a circle and a session.
    sign_in(client, "fac@test.local", "Meera")
    r = client.post("/lead/apply", data={"city": "Pune", "languages": ["en", "mr"], "motivation": "x"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/lead/dashboard").status_code == 403  # not yet approved
    client.post("/lead/training/complete", data={"confirm": "on"})
    client.post("/logout")

    sign_in(client, "admin@test.local", "Admin")
    r = client.get("/admin")
    assert "Meera" in r.text
    app_id = re.search(r"/admin/applications/(\d+)/decide", r.text).group(1)
    client.post(f"/admin/applications/{app_id}/decide", data={"decision": "approve"})
    client.post("/logout")

    sign_in(client, "fac@test.local")
    assert client.get("/lead/dashboard").status_code == 200
    r = client.post("/lead/circles/new", data={"name": "Test Circle", "city": "Pune", "area": "Kothrud", "venue_private": "Secret hall", "languages": ["en"], "format": "in_person", "age_band": "all_adults", "capacity": 3, "description": "d"}, follow_redirects=False)
    assert r.status_code == 303
    r = client.get("/circles/test-circle")
    assert "Secret hall" not in r.text  # venue is private until registered
    from datetime import datetime, timedelta

    circle_id = re.search(r"/lead/circles/(\d+)/sessions/new", client.get("/lead/dashboard").text).group(1)
    when = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    client.post(f"/lead/circles/{circle_id}/sessions/new", data={"starts_at": when, "duration_min": 90, "topic_slug": "saying-no"})
    client.post("/logout")

    # Participants register; capacity is enforced; venue appears after registering.
    sid = None
    for i in range(4):
        sign_in(client, f"p{i}@test.local", f"P{i}")
        page = client.get("/circles/test-circle").text
        sid = sid or re.search(r"/sessions/(\d+)/register", page).group(1)
        r = client.post(f"/sessions/{sid}/register", follow_redirects=False)
        if i < 3:
            assert r.status_code == 303
            assert "Secret hall" in client.get(f"/sessions/{sid}/confirmed").text
        else:
            assert r.status_code == 200  # full; re-rendered circle page
        client.post("/logout")

    # Facilitator records attendance as a count; registered participants give feedback once.
    sign_in(client, "fac@test.local")
    client.post(f"/lead/sessions/{sid}/attendance", data={"attendance_count": 3})
    client.post("/logout")
    for i in range(3):
        sign_in(client, f"p{i}@test.local")
        r = client.post(f"/sessions/{sid}/feedback", data={"felt_safe": 5, "felt_heard": 4, "would_return": "on", "comment": "ok"})
        assert "recorded anonymously" in r.text
        r = client.post(f"/sessions/{sid}/feedback", data={"felt_safe": 1, "felt_heard": 1})
        assert "recorded anonymously" in r.text  # second attempt is a no-op
        client.post("/logout")
    sign_in(client, "p3@test.local")
    r = client.post(f"/sessions/{sid}/feedback", data={"felt_safe": 1, "felt_heard": 1})
    client.post("/logout")

    data = client.get("/data.json").json()
    assert data["sessions_held"] == 1 and data["total_attendance"] == 3
    assert data["feedback"]["responses"] == 3  # unregistered p3 could not add a 4th
    assert data["feedback"]["felt_safe"] == 5.0


def test_helper_requires_facilitator(client):
    client.post("/logout")
    assert client.get("/toolkit/helper").status_code == 401
    sign_in(client, "someone@test.local")
    assert client.get("/toolkit/helper").status_code == 403
    client.post("/logout")


def test_helper_falls_back_without_ai(client):
    sign_in(client, "fac@test.local")
    r = client.post("/toolkit/helper", data={"question": "Someone is crying"})
    assert r.status_code == 200 and "Safeguarding protocol" in r.text
    client.post("/logout")
