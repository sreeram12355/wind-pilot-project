import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)


def test_day_endpoint_respects_cutoff():
    r = c.get("/api/day", params={"date": "2026-01-15", "cutoff": "09:00"}).json()
    assert r["decision_time_utc"].startswith("2026-01-14T09:00")
    assert r["latest_publish_time"] <= r["decision_time_utc"]
    assert len(r["series"]) in (24, 48)  # WINDFOR is hourly; synthetic demo data is half-hourly


def test_validation():
    assert c.get("/api/day", params={"date": "2026-02-01"}).status_code == 422
    assert c.get("/api/summary", params={"cutoff": "25:99"}).status_code == 422
