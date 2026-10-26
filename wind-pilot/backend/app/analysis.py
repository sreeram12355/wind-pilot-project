"""Core logic: pick the forecast a trader actually had, then measure its error.

Conventions
-----------
* All timestamps are UTC internally; UK local time (Europe/London) is used only to
  decide which delivery day a half-hour belongs to and when the D-1 cutoff falls.
* error = forecast - actual.  Positive => wind was OVER-forecast, i.e. the buyer
  procured too little thermal/other power and is exposed to a shortfall.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

LONDON = "Europe/London"
WINDOW_START = date(2026, 1, 1)
WINDOW_END = date(2026, 1, 31)
DEFAULT_CUTOFF = "09:00"  # UK local time on D-1 (configurable)


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    act = pd.read_csv(data_dir / "actuals.csv.gz")
    fc = pd.read_csv(data_dir / "forecasts.csv.gz")
    act["startTime"] = pd.to_datetime(act["startTime"], utc=True)
    fc["startTime"] = pd.to_datetime(fc["startTime"], utc=True)
    fc["publishTime"] = pd.to_datetime(fc["publishTime"], utc=True)
    return act.drop_duplicates("startTime"), fc.drop_duplicates(["startTime", "publishTime"])


def parse_cutoff(cutoff: str) -> tuple[int, int]:
    try:
        h, m = (int(x) for x in cutoff.split(":"))
    except ValueError as e:
        raise ValueError("cutoff must look like HH:MM") from e
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("cutoff must be a valid time of day")
    return h, m


def add_delivery_fields(fc: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    """Add delivery_date (UK local) and cutoff_utc (D-1 at `cutoff` UK time)."""
    h, m = parse_cutoff(cutoff)
    df = fc.copy()
    df["delivery_date"] = df["startTime"].dt.tz_convert(LONDON).dt.date
    df = df[(df["delivery_date"] >= WINDOW_START) & (df["delivery_date"] <= WINDOW_END)]
    cut = {
        d: (pd.Timestamp(d) - pd.Timedelta(days=1) + pd.Timedelta(hours=h, minutes=m))
        .tz_localize(LONDON, ambiguous=True, nonexistent="shift_forward")
        .tz_convert("UTC")
        for d in df["delivery_date"].unique()
    }
    df["cutoff_utc"] = pd.to_datetime(df["delivery_date"].map(cut), utc=True)
    return df


def select_latest(fc: pd.DataFrame, cutoff: str = DEFAULT_CUTOFF) -> pd.DataFrame:
    """For each target half-hour: the latest forecast published at/before the D-1 cutoff."""
    df = add_delivery_fields(fc, cutoff)
    df = df[df["publishTime"] <= df["cutoff_utc"]]
    df = df.sort_values(["startTime", "publishTime"]).drop_duplicates("startTime", keep="last")
    df["horizon_h"] = (df["startTime"] - df["publishTime"]).dt.total_seconds() / 3600
    return df.reset_index(drop=True)


def join_actuals(sel: pd.DataFrame, act: pd.DataFrame) -> pd.DataFrame:
    out = sel.merge(act[["startTime", "generation"]].rename(columns={"generation": "actual"}),
                    on="startTime", how="left")
    out = out.rename(columns={"generation": "forecast"})
    out["error"] = out["forecast"] - out["actual"]
    out["abs_error"] = out["error"].abs()
    return out


def metrics(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["actual", "forecast"])
    if d.empty:
        return {"n": 0}
    mean_actual = float(d["actual"].mean())
    mae = float(d["abs_error"].mean())
    return {
        "n": int(len(d)),
        "mean_actual_mw": mean_actual,
        "bias_mw": float(d["error"].mean()),
        "mae_mw": mae,
        "rmse_mw": float(np.sqrt((d["error"] ** 2).mean())),
        "nmae_pct": mae / mean_actual * 100 if mean_actual else None,
        "p50_abs_mw": float(d["abs_error"].quantile(0.5)),
        "p90_abs_mw": float(d["abs_error"].quantile(0.9)),
        "p95_abs_mw": float(d["abs_error"].quantile(0.95)),
        # Shortfall buffer: wind over-forecast exceeded this only 10% / 5% of half-hours.
        "buffer_p90_mw": float(max(d["error"].quantile(0.9), 0)),
        "buffer_p95_mw": float(max(d["error"].quantile(0.95), 0)),
    }


def _group(df: pd.DataFrame, key, name: str) -> list[dict]:
    rows = []
    for k, g in df.dropna(subset=["actual"]).groupby(key):
        m = metrics(g)
        rows.append({name: str(k) if name == "date" else int(k),
                     "n": m["n"], "mae_mw": m["mae_mw"], "bias_mw": m["bias_mw"],
                     "p90_abs_mw": m["p90_abs_mw"], "mean_actual_mw": m["mean_actual_mw"]})
    return rows


def by_day(df: pd.DataFrame) -> list[dict]:
    return _group(df, df["delivery_date"], "date")


def by_hour(df: pd.DataFrame) -> list[dict]:
    hour = df["startTime"].dt.tz_convert(LONDON).dt.hour
    return _group(df, hour, "hour")


def by_horizon_all(fc: pd.DataFrame, act: pd.DataFrame, cutoff: str, bin_h: int = 6) -> list[dict]:
    """Error vs lead time across ALL January forecasts (not just the latest-before-cutoff)."""
    df = join_actuals(add_delivery_fields(fc, cutoff), act)
    df["horizon_h"] = (df["startTime"] - df["publishTime"]).dt.total_seconds() / 3600
    df = df[(df["horizon_h"] >= 0) & (df["horizon_h"] < 48)]
    df["bucket"] = (df["horizon_h"] // bin_h * bin_h).astype(int)
    rows = _group(df, df["bucket"], "horizon_from_h")
    for r in rows:
        r["horizon_to_h"] = r["horizon_from_h"] + bin_h
    return rows


def _f(x):
    return None if x is None or pd.isna(x) else round(float(x), 1)


def day_series(df: pd.DataFrame, day: date) -> list[dict]:
    d = df[df["delivery_date"] == day].sort_values("startTime")
    return [
        {
            "startTime": r.startTime.isoformat(),
            "local": r.startTime.tz_convert(LONDON).strftime("%H:%M"),
            "forecast": _f(r.forecast), "actual": _f(r.actual), "error": _f(r.error),
            "publishTime": r.publishTime.isoformat(),
            "horizon_h": round(r.horizon_h, 1),
        }
        for r in d.itertuples()
    ]
