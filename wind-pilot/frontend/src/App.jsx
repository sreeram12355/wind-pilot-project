import { useEffect, useMemo, useState } from "react";
import { Cell } from "recharts";
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

const C = { actual: "#0e7c86", forecast: "#4a3fd1", band: "#c9cff0", grid: "#d5dde3", over: "#b4432f", under: "#0e7c86" };
const mw = (v) => (v == null ? "–" : Math.round(v).toLocaleString("en-GB"));
const fmtTime = (iso) =>
  new Date(iso).toLocaleString("en-GB", { timeZone: "Europe/London", weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}

function Stat({ label, value, unit, note }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{value}<span>{unit}</span></dd>
      {note && <p>{note}</p>}
    </div>
  );
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [date, setDate] = useState("2026-01-15");
  const [cutoff, setCutoff] = useState("09:00");
  const [day, setDay] = useState(null);
  const [sum, setSum] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => { api("/api/meta").then((m) => { setMeta(m); setCutoff(m.default_cutoff); }).catch((e) => setErr(e.message)); }, []);
  useEffect(() => {
    if (!meta) return;
    setErr(null);
    api(`/api/day?date=${date}&cutoff=${cutoff}`).then(setDay).catch((e) => { setDay(null); setErr(e.message); });
  }, [meta, date, cutoff]);
  useEffect(() => {
    if (!meta) return;
    api(`/api/summary?cutoff=${cutoff}`).then(setSum).catch((e) => setErr(e.message));
  }, [meta, cutoff]);

  const series = useMemo(
    () => (day?.series || []).map((r) => ({ ...r, band: r.forecast == null || !day.metrics.p90_abs_mw ? null : [Math.max(0, r.forecast - day.metrics.p90_abs_mw), r.forecast + day.metrics.p90_abs_mw] })),
    [day]
  );
  const o = sum?.overall;
  const m = day?.metrics;

  return (
    <div className="page">
      <header>
        <h1>Day-ahead wind forecast desk</h1>
        <p>For each January 2026 delivery day: the wind forecast you had when you had to buy, and how far off it usually is.</p>
        {meta?.data_source?.startsWith("SYNTHETIC") && <p className="warn">Showing synthetic demo data, not Elexon data.</p>}
      </header>

      <section className="controls" aria-label="Decision settings">
        <label>Delivery day
          <input type="date" min={meta?.window_start} max={meta?.window_end} value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
        <label>Purchase cutoff on the day before (UK time)
          <input type="time" value={cutoff} onChange={(e) => e.target.value && setCutoff(e.target.value)} />
        </label>
        {day && <p className="decision">You decide at <b>{fmtTime(day.decision_time_utc)}</b>. The newest forecast you can use was published <b>{fmtTime(day.latest_publish_time)}</b>.</p>}
      </section>

      {err && <p className="error" role="alert">{err}</p>}

      <section>
        <h2>Wind on {date}: forecast against what happened</h2>
        <div className="chart tall">
          <ResponsiveContainer>
            <ComposedChart data={series} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="local" interval={5} tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={(v) => `${v / 1000}`} label={{ value: "GW", angle: -90, position: "insideLeft" }} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v, n) => (Array.isArray(v) ? `${mw(v[0])} to ${mw(v[1])} MW` : `${mw(v)} MW`)} />
              <Legend />
              <Area dataKey="band" name="Typical error range (P90)" fill={C.band} stroke="none" fillOpacity={0.6} isAnimationActive={false} />
              <Line dataKey="forecast" name="Forecast at decision time" stroke={C.forecast} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="actual" name="Actual" stroke={C.actual} strokeWidth={2} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        {m?.n > 0 && (
          <dl className="stats">
            <Stat label="Average miss" value={mw(m.mae_mw)} unit=" MW" note={`${m.nmae_pct.toFixed(1)}% of average output`} />
            <Stat label="Bias" value={`${m.bias_mw > 0 ? "+" : ""}${mw(m.bias_mw)}`} unit=" MW" note={m.bias_mw > 0 ? "Wind over-forecast: risk of buying too little" : "Wind under-forecast: risk of buying too much"} />
            <Stat label="Miss on 9 in 10 half-hours" value={mw(m.p90_abs_mw)} unit=" MW" note="P90 absolute error" />
            <Stat label="Shortfall buffer" value={mw(m.buffer_p90_mw)} unit=" MW" note="Extra supply to cover wind falling short 9 times in 10" />
          </dl>
        )}
      </section>

      {o?.n > 0 && (
        <section>
          <h2>How reliable the forecast was across January</h2>
          <p className="lede">
            Using the same cutoff, the forecast missed by <b>{mw(o.mae_mw)} MW</b> on average ({o.nmae_pct.toFixed(1)}% of output) and by more than <b>{mw(o.p90_abs_mw)} MW</b> in one half-hour in ten.
            Wind fell short of forecast by more than <b>{mw(o.buffer_p90_mw)} MW</b> in one half-hour in ten. RMSE is {mw(o.rmse_mw)} MW.
          </p>
          <div className="grid">
            <figure>
              <figcaption>Average miss by delivery day (MW)</figcaption>
              <div className="chart">
                <ResponsiveContainer><BarChart data={sum.by_day} onClick={(e) => e?.activeLabel && setDate(e.activeLabel)}>
                  <CartesianGrid stroke={C.grid} vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(d) => d.slice(8)} tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => `${mw(v)} MW`} />
                  <Bar dataKey="mae_mw" name="Average miss" fill={C.forecast} isAnimationActive={false} />
                </BarChart></ResponsiveContainer>
              </div>
              <p className="hint">Click a bar to open that day.</p>
            </figure>
            <figure>
              <figcaption>Bias by time of day (MW, above zero = over-forecast)</figcaption>
              <div className="chart">
                <ResponsiveContainer><BarChart data={sum.by_hour}>
                  <CartesianGrid stroke={C.grid} vertical={false} />
                  <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <ReferenceLine y={0} stroke="#44525c" />
                  <Tooltip formatter={(v) => `${mw(v)} MW`} labelFormatter={(h) => `${String(h).padStart(2, "0")}:00 UK`} />
                  <Bar dataKey="bias_mw" name="Bias" isAnimationActive={false}>
                    {sum.by_hour.map((r) => <CellBar key={r.hour} v={r.bias_mw} />)}
                  </Bar>
                </BarChart></ResponsiveContainer>
              </div>
            </figure>
            <figure>
              <figcaption>Average miss by how far ahead the forecast was published (MW)</figcaption>
              <div className="chart">
                <ResponsiveContainer><BarChart data={sum.by_horizon.map((r) => ({ ...r, label: `${r.horizon_from_h}–${r.horizon_to_h}h` }))}>
                  <CartesianGrid stroke={C.grid} vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => `${mw(v)} MW`} />
                  <Bar dataKey="mae_mw" name="Average miss" fill={C.actual} isAnimationActive={false} />
                </BarChart></ResponsiveContainer>
              </div>
            </figure>
          </div>
        </section>
      )}
      <footer>Source: Elexon BMRS, national wind (FUELHH actuals, WINDFOR forecasts). Error = forecast minus actual.</footer>
    </div>
  );
}

function CellBar({ v }) { return <Cell fill={v > 0 ? C.over : C.under} />; }
