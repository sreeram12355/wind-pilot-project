"""Fetch Elexon data into data/*.csv.gz.

  python backend/ingest.py            # real data from the Elexon BMRS API
  python backend/ingest.py --demo     # synthetic data, for offline development ONLY
"""
import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
DATA = Path(__file__).resolve().parents[1] / "data"
ACT_FROM, ACT_TO = date(2025, 12, 31), date(2026, 2, 1)  # small margin around January
FC_FROM = datetime(2025, 12, 28, tzinfo=timezone.utc)
FC_TO = datetime(2026, 2, 1, tzinfo=timezone.utc)


def get(url: str, params: dict) -> list[dict]:
    r = requests.get(url, params={**params, "format": "json"}, timeout=120)
    r.raise_for_status()
    return r.json()


def fetch_actuals() -> pd.DataFrame:
    rows, d = [], ACT_FROM
    while d <= ACT_TO:
        end = min(d + timedelta(days=6), ACT_TO)
        rows += get(f"{BASE}/FUELHH/stream", {"settlementDateFrom": d.isoformat(),
                                              "settlementDateTo": end.isoformat(), "fuelType": "WIND"})
        d = end + timedelta(days=1)
    df = pd.DataFrame(rows)
    df = df[df["fuelType"] == "WIND"][["startTime", "generation"]]
    return df.drop_duplicates("startTime")


def fetch_forecasts() -> pd.DataFrame:
    rows, t = [], FC_FROM
    while t < FC_TO:
        end = min(t + timedelta(days=2), FC_TO)  # small windows keep responses under API limits
        rows += get(f"{BASE}/WINDFOR/stream", {"publishDateTimeFrom": t.strftime("%Y-%m-%dT%H:%MZ"),
                                               "publishDateTimeTo": end.strftime("%Y-%m-%dT%H:%MZ")})
        t = end
    df = pd.DataFrame(rows)[["startTime", "publishTime", "generation"]]
    return df.drop_duplicates(["startTime", "publishTime"])


def synthetic() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(42)
    idx = pd.date_range("2025-12-28", "2026-02-02", freq="30min", tz="UTC")
    x = np.cumsum(rng.normal(0, 1, len(idx)))
    x = (x - x.mean()) / x.std()
    actual = np.clip(8000 + 4500 * np.tanh(x) + rng.normal(0, 150, len(idx)), 200, 14500).round(0)
    act = pd.DataFrame({"startTime": idx, "generation": actual})
    lookup = act.set_index("startTime")["generation"]
    parts = []
    for pub in pd.date_range("2025-12-28", "2026-01-31 23:00", freq="h", tz="UTC"):
        tgt = idx[(idx > pub) & (idx <= pub + pd.Timedelta(hours=48))]
        h = (tgt - pub).total_seconds() / 3600
        f = np.clip(lookup.loc[tgt].to_numpy() + rng.normal(0, 150 + 70 * h), 0, 15000).round(0)
        parts.append(pd.DataFrame({"startTime": tgt, "publishTime": pub, "generation": f}))
    return act, pd.concat(parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    act, fc = synthetic() if args.demo else (fetch_actuals(), fetch_forecasts())
    act.to_csv(DATA / "actuals.csv.gz", index=False)
    fc.to_csv(DATA / "forecasts.csv.gz", index=False)
    (DATA / "SOURCE.txt").write_text("SYNTHETIC demo data" if args.demo else "Elexon BMRS (FUELHH, WINDFOR)")
    print(f"actuals={len(act)} forecasts={len(fc)} source={'synthetic' if args.demo else 'elexon'}")
