import os
from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import analysis as an

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
STATIC_DIR = Path(os.getenv("STATIC_DIR", ROOT / "frontend" / "dist"))

app = FastAPI(title="Wind forecast pilot")
ACT, FC = an.load_data(DATA_DIR)
SRC_FILE = DATA_DIR / "SOURCE.txt"
SOURCE = SRC_FILE.read_text().strip() if SRC_FILE.exists() else "unknown"


@lru_cache(maxsize=64)
def _joined(cutoff: str):
    return an.join_actuals(an.select_latest(FC, cutoff), ACT)


def _check_cutoff(cutoff: str) -> str:
    try:
        an.parse_cutoff(cutoff)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return cutoff


@app.get("/api/meta")
def meta():
    return {"window_start": str(an.WINDOW_START), "window_end": str(an.WINDOW_END),
            "default_cutoff": an.DEFAULT_CUTOFF, "data_source": SOURCE, "timezone": an.LONDON}


@app.get("/api/day")
def day(date_: date = Query(..., alias="date"), cutoff: str = an.DEFAULT_CUTOFF):
    _check_cutoff(cutoff)
    if not (an.WINDOW_START <= date_ <= an.WINDOW_END):
        raise HTTPException(422, "date must be in January 2026")
    df = _joined(cutoff)
    d = df[df["delivery_date"] == date_]
    if d.empty:
        raise HTTPException(404, "no forecast available before the cutoff for this day")
    return {"date": str(date_), "cutoff": cutoff,
            "decision_time_utc": d["cutoff_utc"].iloc[0].isoformat(),
            "latest_publish_time": d["publishTime"].max().isoformat(),
            "oldest_publish_time": d["publishTime"].min().isoformat(),
            "metrics": an.metrics(d), "series": an.day_series(df, date_)}


@app.get("/api/summary")
def summary(cutoff: str = an.DEFAULT_CUTOFF):
    _check_cutoff(cutoff)
    df = _joined(cutoff)
    return {"cutoff": cutoff, "overall": an.metrics(df), "by_day": an.by_day(df),
            "by_hour": an.by_hour(df), "by_horizon": an.by_horizon_all(FC, ACT, cutoff)}


@app.get("/api/health")
def health():
    return {"ok": True}


if (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = STATIC_DIR / path
        return FileResponse(f if f.is_file() else STATIC_DIR / "index.html")
