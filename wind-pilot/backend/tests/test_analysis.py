import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import analysis as an  # noqa: E402


def fc_rows(rows):
    df = pd.DataFrame(rows, columns=["startTime", "publishTime", "generation"])
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    return df


def test_picks_latest_before_cutoff_and_ignores_later_publications():
    fc = fc_rows([
        ("2026-01-10 12:00", "2026-01-08 20:00", 100),  # older
        ("2026-01-10 12:00", "2026-01-09 08:59", 200),  # latest usable (cutoff 09:00 on D-1)
        ("2026-01-10 12:00", "2026-01-09 09:01", 999),  # published after cutoff -> unusable
    ])
    sel = an.select_latest(fc, "09:00")
    assert len(sel) == 1 and sel.generation.iloc[0] == 200


def test_no_forecast_before_cutoff_means_no_row():
    fc = fc_rows([("2026-01-10 12:00", "2026-01-09 10:00", 1)])
    assert an.select_latest(fc, "09:00").empty


def test_cutoff_is_configurable():
    fc = fc_rows([("2026-01-10 12:00", "2026-01-09 08:00", 1), ("2026-01-10 12:00", "2026-01-09 11:00", 2)])
    assert an.select_latest(fc, "12:00").generation.iloc[0] == 2


def test_dates_outside_january_dropped():
    fc = fc_rows([("2026-02-03 12:00", "2026-02-02 06:00", 1)])
    assert an.select_latest(fc).empty


def test_metrics_sign_and_values():
    df = pd.DataFrame({"actual": [100.0, 200.0, 300.0], "forecast": [110.0, 180.0, 330.0]})
    df["error"] = df.forecast - df.actual
    df["abs_error"] = df.error.abs()
    m = an.metrics(df)
    assert m["bias_mw"] == (10 - 20 + 30) / 3
    assert m["mae_mw"] == 20
    assert round(m["nmae_pct"], 6) == 10.0
    assert m["buffer_p90_mw"] >= 0
