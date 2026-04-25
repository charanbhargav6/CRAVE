"use client";
import { useState, useEffect, useCallback } from "react";
import { createClient } from "@supabase/supabase-js";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Area, AreaChart
} from "recharts";

// ── CONFIG — replace with your Supabase values ──────────────────────────────
const SUPABASE_URL  = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://YOUR_PROJECT.supabase.co";
const SUPABASE_ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "YOUR_ANON_KEY";
const supabase      = createClient(SUPABASE_URL, SUPABASE_ANON);

// ── DESIGN SYSTEM ─────────────────────────────────────────────────────────
// Aesthetic: Military-grade trading terminal. Dark slate + amber warnings
// + acid green for profits. Monospace + geometric sans. No rounded softness.
// Think Bloomberg terminal meets street-level hustle.

const css = `
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Barlow:wght@300;400;500;600;700;900&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #080c10;
    --bg2:       #0d1117;
    --bg3:       #111820;
    --border:    #1c2836;
    --border2:   #243040;
    --text:      #c8d8e8;
    --muted:     #4a6070;
    --accent:    #00c896;   /* profit green */
    --loss:      #ff3d57;   /* loss red */
    --warn:      #f5a623;   /* amber warning */
    --blue:      #3d8eff;   /* info blue */
    --mono:      'Space Mono', monospace;
    --sans:      'Barlow', sans-serif;
  }

  html, body { background: var(--bg); color: var(--text); font-family: var(--sans); }

  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: var(--bg2); }
  ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

  .dashboard {
    min-height: 100vh;
    padding: 0;
    background: var(--bg);
    background-image:
      linear-gradient(var(--border) 1px, transparent 1px),
      linear-gradient(90deg, var(--border) 1px, transparent 1px);
    background-size: 48px 48px;
    background-position: -1px -1px;
  }

  .topbar {
    position: sticky; top: 0; z-index: 100;
    background: rgba(8,12,16,0.92);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 0 24px;
    height: 56px;
    display: flex; align-items: center; justify-content: space-between;
  }

  .logo {
    font-family: var(--mono);
    font-size: 13px;
    letter-spacing: 4px;
    color: var(--accent);
    text-transform: uppercase;
  }

  .logo span { color: var(--muted); }

  .status-row {
    display: flex; align-items: center; gap: 16px;
    font-family: var(--mono); font-size: 11px;
  }

  .dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 5px; }
  .dot.green  { background: var(--accent); box-shadow: 0 0 8px var(--accent); animation: pulse 2s infinite; }
  .dot.red    { background: var(--loss); }
  .dot.amber  { background: var(--warn); box-shadow: 0 0 8px var(--warn); animation: pulse 2s infinite; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.4; }
  }

  .main { max-width: 1440px; margin: 0 auto; padding: 24px; }

  .grid-4 {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 16px;
  }

  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 16px;
  }

  .grid-3 {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 12px;
    margin-bottom: 16px;
  }

  .card {
    background: var(--bg2);
    border: 1px solid var(--border);
    padding: 16px 20px;
    position: relative;
    overflow: hidden;
  }

  .card::before {
    content: '';
    position: absolute; top: 0; left: 0;
    width: 3px; height: 100%;
    background: var(--border2);
  }

  .card.green::before  { background: var(--accent); }
  .card.red::before    { background: var(--loss); }
  .card.amber::before  { background: var(--warn); }
  .card.blue::before   { background: var(--blue); }

  .card-label {
    font-family: var(--mono);
    font-size: 9px;
    letter-spacing: 3px;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  .card-value {
    font-family: var(--mono);
    font-size: 28px;
    font-weight: 700;
    line-height: 1;
    color: var(--text);
  }

  .card-value.green { color: var(--accent); }
  .card-value.red   { color: var(--loss); }
  .card-value.amber { color: var(--warn); }

  .card-sub {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    margin-top: 4px;
  }

  .section-title {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }

  /* Trade table */
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th {
    font-family: var(--mono);
    font-size: 9px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--muted);
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    font-weight: 400;
  }

  td {
    padding: 10px 12px;
    font-family: var(--mono);
    font-size: 11px;
    border-bottom: 1px solid rgba(28,40,54,0.5);
    color: var(--text);
  }

  tr:hover td { background: rgba(255,255,255,0.02); }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    font-family: var(--mono);
    font-size: 9px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  .badge-long  { background: rgba(0,200,150,0.12); color: var(--accent); border: 1px solid rgba(0,200,150,0.2); }
  .badge-short { background: rgba(255,61,87,0.12);  color: var(--loss);   border: 1px solid rgba(255,61,87,0.2); }
  .badge-paper { background: rgba(61,142,255,0.12); color: var(--blue);   border: 1px solid rgba(61,142,255,0.2); }
  .badge-live  { background: rgba(245,166,35,0.12); color: var(--warn);   border: 1px solid rgba(245,166,35,0.2); }

  .r-positive { color: var(--accent); }
  .r-negative { color: var(--loss); }
  .r-zero     { color: var(--muted); }

  /* Kill switch */
  .kill-zone {
    background: rgba(255,61,87,0.04);
    border: 1px solid rgba(255,61,87,0.2);
    padding: 16px 20px;
    margin-bottom: 16px;
    display: flex; align-items: center; justify-content: space-between;
  }

  .kill-btn {
    background: transparent;
    border: 1px solid var(--loss);
    color: var(--loss);
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 2px;
    padding: 8px 20px;
    cursor: pointer;
    text-transform: uppercase;
    transition: all 0.15s;
  }

  .kill-btn:hover {
    background: var(--loss);
    color: #fff;
  }

  .kill-btn.pause {
    border-color: var(--warn);
    color: var(--warn);
  }
  .kill-btn.pause:hover { background: var(--warn); color: #000; }

  .kill-btn.resume {
    border-color: var(--accent);
    color: var(--accent);
  }
  .kill-btn.resume:hover { background: var(--accent); color: #000; }

  /* Heat bar */
  .heat-bar-bg { background: var(--border); height: 4px; width: 100%; margin-top: 8px; }
  .heat-bar-fill { height: 4px; transition: width 1s; background: var(--accent); }
  .heat-bar-fill.warn  { background: var(--warn); }
  .heat-bar-fill.crit  { background: var(--loss); }

  /* Bias pills */
  .bias-grid { display: flex; flex-wrap: wrap; gap: 8px; }
  .bias-pill {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 10px;
    border: 1px solid var(--border);
    font-family: var(--mono); font-size: 10px;
  }
  .bias-pill.buy  { border-color: rgba(0,200,150,0.3); }
  .bias-pill.sell { border-color: rgba(255,61,87,0.3); }
  .bias-pill.no_trade { opacity: 0.4; }

  .star { color: var(--warn); }

  /* Tooltip */
  .custom-tooltip {
    background: var(--bg3);
    border: 1px solid var(--border2);
    padding: 10px 14px;
    font-family: var(--mono);
    font-size: 11px;
  }

  /* Stat comparison table */
  .compare-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1px;
    background: var(--border);
  }
  .compare-cell {
    background: var(--bg2);
    padding: 12px 16px;
    font-family: var(--mono);
    font-size: 11px;
  }
  .compare-cell .label { color: var(--muted); font-size: 9px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 4px; }
  .compare-cell .crave { color: var(--accent); font-size: 16px; font-weight: 700; }
  .compare-cell .target { color: var(--muted); font-size: 11px; }

  .updated-time { font-family: var(--mono); font-size: 9px; color: var(--muted); }
`;

// ── HOOKS ──────────────────────────────────────────────────────────────────

function useSupabaseTable(table, refreshMs = 10000) {
  const [data, setData] = useState(null);

  const fetch = useCallback(async () => {
    const { data: rows } = await supabase.from(table).select("*").limit(500);
    if (rows) setData(rows);
  }, [table]);

  useEffect(() => {
    fetch();
    const interval = setInterval(fetch, refreshMs);
    // Also subscribe to realtime
    const sub = supabase.channel(table)
      .on("postgres_changes", { event: "*", schema: "public", table }, fetch)
      .subscribe();
    return () => { clearInterval(interval); supabase.removeChannel(sub); };
  }, [fetch, table, refreshMs]);

  return data;
}

// ── FORMATTERS ─────────────────────────────────────────────────────────────

const fmt = {
  currency:  (v) => v != null ? `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—",
  pct:       (v) => v != null ? `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(2)}%` : "—",
  r:         (v) => v != null ? `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(2)}R` : "—",
  num2:      (v) => v != null ? Number(v).toFixed(2) : "—",
  time:      (v) => v ? new Date(v).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: false, month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—",
  duration:  (h) => h == null ? "—" : h < 1 ? `${Math.round(h * 60)}m` : `${Number(h).toFixed(1)}h`,
};

// ── COMPONENTS ─────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color = "", size = "28px" }) {
  return (
    <div className={`card ${color}`}>
      <div className="card-label">{label}</div>
      <div className="card-value" style={{ fontSize: size, color: color === "green" ? "var(--accent)" : color === "red" ? "var(--loss)" : color === "amber" ? "var(--warn)" : undefined }}>
        {value ?? "—"}
      </div>
      {sub && <div className="card-sub">{sub}</div>}
    </div>
  );
}

function EquityChart({ curve }) {
  if (!curve || curve.length < 2) return (
    <div style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 11 }}>
      NO EQUITY DATA — START PAPER TRADING
    </div>
  );

  const start = curve[0]?.equity ?? 10000;
  const data  = curve.map((r, i) => ({
    i,
    equity: r.equity,
    delta:  r.equity - start,
  }));

  const CustomTip = ({ active, payload }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
      <div className="custom-tooltip">
        <div style={{ color: d.equity >= start ? "var(--accent)" : "var(--loss)" }}>
          {fmt.currency(d.equity)}
        </div>
        <div style={{ color: "var(--muted)", fontSize: 10 }}>
          {d.delta >= 0 ? "+" : ""}{fmt.currency(d.delta)}
        </div>
      </div>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="var(--accent)" stopOpacity={0.25} />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" strokeOpacity={0.6} />
        <XAxis dataKey="i" hide />
        <YAxis tickFormatter={v => `$${(v/1000).toFixed(1)}k`} tick={{ fill: "var(--muted)", fontSize: 9, fontFamily: "var(--mono)" }} axisLine={false} tickLine={false} width={48} />
        <Tooltip content={<CustomTip />} />
        <ReferenceLine y={start} stroke="var(--border2)" strokeDasharray="4 4" />
        <Area type="monotone" dataKey="equity" stroke="var(--accent)" strokeWidth={1.5} fill="url(#eq)" dot={false} activeDot={{ r: 4, fill: "var(--accent)" }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function PositionsTable({ positions }) {
  if (!positions?.length) return (
    <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 11 }}>
      NO OPEN POSITIONS
    </div>
  );

  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            {["Symbol","Dir","Grade","Entry","SL","TP","Remain","Unreal R","Opened","Mode"].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map(p => {
            const r = p.unrealised_r ?? 0;
            return (
              <tr key={p.trade_id}>
                <td><strong>{p.symbol?.replace("=X","")}</strong></td>
                <td>
                  <span className={`badge badge-${p.direction === "buy" || p.direction === "long" ? "long" : "short"}`}>
                    {p.direction?.toUpperCase()}
                  </span>
                </td>
                <td style={{ color: p.grade === "A+" ? "var(--accent)" : "var(--text)" }}>{p.grade}</td>
                <td>{p.entry_price?.toFixed(4)}</td>
                <td style={{ color: "var(--loss)" }}>{p.current_sl?.toFixed(4)}</td>
                <td style={{ color: "var(--accent)" }}>{p.current_tp?.toFixed(4)}</td>
                <td>{p.remaining_pct?.toFixed(0)}%{p.tp1_hit ? " ✓" : ""}</td>
                <td className={r >= 0.1 ? "r-positive" : r <= -0.1 ? "r-negative" : "r-zero"}>
                  {fmt.r(r)}
                </td>
                <td style={{ color: "var(--muted)" }}>{fmt.time(p.open_time)}</td>
                <td><span className={`badge badge-${p.is_paper ? "paper" : "live"}`}>{p.is_paper ? "PAPER" : "LIVE"}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TradesTable({ trades }) {
  if (!trades?.length) return (
    <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 11 }}>
      NO CLOSED TRADES YET
    </div>
  );

  const sorted = [...trades].sort((a, b) =>
    new Date(b.close_time || 0) - new Date(a.close_time || 0)
  ).slice(0, 50);

  return (
    <div style={{ overflowX: "auto", maxHeight: 400, overflowY: "auto" }}>
      <table>
        <thead>
          <tr>
            {["Symbol","Dir","Grade","Entry","Exit","SL","R","Outcome","Hold","Closed","Mode"].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(t => {
            const r = t.r_multiple ?? 0;
            return (
              <tr key={t.trade_id}>
                <td><strong>{t.symbol?.replace("=X","")}</strong></td>
                <td>
                  <span className={`badge badge-${t.direction === "buy" || t.direction === "long" ? "long" : "short"}`}>
                    {t.direction?.slice(0,1).toUpperCase()}
                  </span>
                </td>
                <td style={{ color: t.grade === "A+" ? "var(--accent)" : "var(--text)" }}>{t.grade}</td>
                <td>{t.entry_price?.toFixed(4)}</td>
                <td>{t.exit_price?.toFixed(4)}</td>
                <td style={{ color: "var(--loss)", fontSize: 10 }}>{t.stop_loss?.toFixed(4)}</td>
                <td className={r >= 0.1 ? "r-positive" : r <= -0.1 ? "r-negative" : "r-zero"} style={{ fontWeight: 700 }}>
                  {fmt.r(r)}
                </td>
                <td style={{ color: "var(--muted)", fontSize: 10 }}>{t.outcome?.replace(/_/g," ")}</td>
                <td style={{ color: "var(--muted)" }}>{fmt.duration(t.hold_duration_h)}</td>
                <td style={{ color: "var(--muted)", fontSize: 10 }}>{fmt.time(t.close_time)}</td>
                <td><span className={`badge badge-${t.is_paper ? "paper" : "live"}`}>{t.is_paper ? "P" : "L"}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function BiasPanel({ bias }) {
  if (!bias?.length) return <div style={{ color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 11 }}>NO BIAS DATA</div>;

  return (
    <div className="bias-grid">
      {bias.map(b => (
        <div key={b.symbol} className={`bias-pill ${b.bias?.toLowerCase()}`}>
          <span style={{ color: b.bias === "BUY" ? "var(--accent)" : b.bias === "SELL" ? "var(--loss)" : "var(--muted)" }}>
            {b.bias === "BUY" ? "▲" : b.bias === "SELL" ? "▼" : "—"}
          </span>
          <span style={{ fontWeight: 700 }}>{b.symbol?.replace("=X","").replace("-USD","")}</span>
          <span className="star">{"★".repeat(b.strength ?? 0)}</span>
        </div>
      ))}
    </div>
  );
}

function KillSwitch({ status }) {
  const [confirming, setConfirming] = useState(false);
  const [action, setAction]         = useState(null);

  const trigger = async (act) => {
    if (!confirming) { setAction(act); setConfirming(true); return; }
    if (action !== act) { setAction(act); return; }
    // Insert kill command
    await supabase.from("crave_kill_switch").insert({
      triggered_at: new Date().toISOString(),
      triggered_by: "dashboard",
      action:       act,
      executed:     false,
    });
    setConfirming(false);
    setAction(null);
    alert(`Kill switch sent: ${act.toUpperCase()}`);
  };

  const paused = status?.can_trade === false;

  return (
    <div className="kill-zone">
      <div>
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--loss)", letterSpacing: 2, marginBottom: 4 }}>
          ⚠ KILL SWITCH
        </div>
        <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--muted)" }}>
          {confirming
            ? `CLICK AGAIN TO CONFIRM: ${action?.toUpperCase()}`
            : "All commands execute within 5 seconds via Supabase → Bot polling."}
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {paused ? (
          <button className="kill-btn resume" onClick={() => trigger("resume")}>
            {confirming && action === "resume" ? "CONFIRM RESUME" : "▶ RESUME"}
          </button>
        ) : (
          <button className="kill-btn pause" onClick={() => trigger("pause")}>
            {confirming && action === "pause" ? "CONFIRM PAUSE" : "⏸ PAUSE"}
          </button>
        )}
        <button className="kill-btn" onClick={() => trigger("close_all")}>
          {confirming && action === "close_all" ? "⚠ CONFIRM CLOSE ALL" : "✕ CLOSE ALL"}
        </button>
      </div>
    </div>
  );
}

function ComparisonPanel({ stats }) {
  const wr      = stats?.win_rate ?? 0;
  const pf      = stats?.profit_factor ?? 0;
  const sharpe  = stats?.sharpe_ratio ?? 0;
  const exp     = stats?.expectancy_r ?? 0;

  const rows = [
    { label: "Win Rate",      crave: fmt.pct(wr),      target: "> 50%",  good: wr >= 50 },
    { label: "Profit Factor", crave: fmt.num2(pf),     target: "> 1.5",  good: pf >= 1.5 },
    { label: "Sharpe Ratio",  crave: fmt.num2(sharpe), target: "> 0.8",  good: sharpe >= 0.8 },
    { label: "Expectancy",    crave: fmt.r(exp),       target: "> 0.1R", good: exp >= 0.1 },
  ];

  return (
    <div>
      <div className="section-title">vs Prop Firm Benchmarks</div>
      <div className="compare-grid">
        {rows.map(r => (
          <div key={r.label} className="compare-cell">
            <div className="label">{r.label}</div>
            <div className="crave" style={{ color: r.good ? "var(--accent)" : "var(--loss)" }}>
              {r.crave}
            </div>
            <div className="target">Target: {r.target}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── MAIN APP ───────────────────────────────────────────────────────────────

export default function CRAVEDashboard() {
  const statsArr   = useSupabaseTable("crave_account_stats",  10000);
  const equityCurve = useSupabaseTable("crave_equity_curve",  30000);
  const positions  = useSupabaseTable("crave_open_positions", 10000);
  const trades     = useSupabaseTable("crave_trades",         30000);
  const sysStatus  = useSupabaseTable("crave_system_status",  10000);
  const dailyBias  = useSupabaseTable("crave_daily_bias",     60000);

  const stats  = statsArr?.[0]  ?? {};
  const sys    = sysStatus?.[0] ?? {};

  const equity        = stats.equity ?? 10000;
  const startEquity   = stats.starting_equity ?? 10000;
  const totalReturn   = stats.total_return_pct ?? 0;
  const maxDD         = stats.max_drawdown_pct ?? 0;
  const totalTrades   = stats.total_trades ?? 0;
  const minTrades     = 30;
  const readiness     = totalTrades >= minTrades && (stats.win_rate ?? 0) >= 50;
  const heatPct       = Math.min((positions?.length ?? 0) * 1.5, 6.5);

  // Today's bias
  const todayStr  = new Date().toISOString().slice(0, 10);
  const todayBias = (dailyBias ?? []).filter(b => b.date === todayStr);

  return (
    <>
      <style>{css}</style>
      <div className="dashboard">

        {/* ── TOP BAR ── */}
        <div className="topbar">
          <div className="logo">CRAVE<span>/</span>v10.3</div>
          <div className="status-row">
            <span>
              <span className={`dot ${sys.bot_running ? "green" : "red"}`}></span>
              {sys.bot_running ? "ONLINE" : "OFFLINE"}
            </span>
            <span style={{ color: "var(--muted)" }}>|</span>
            <span>
              <span className={`dot ${sys.ws_connected ? "green" : "amber"}`}></span>
              WS {sys.ws_connected ? "LIVE" : "POLLING"}
            </span>
            <span style={{ color: "var(--muted)" }}>|</span>
            <span style={{ color: stats.trading_mode === "live" ? "var(--warn)" : "var(--blue)" }}>
              {stats.trading_mode?.toUpperCase() ?? "PAPER"}
            </span>
            <span style={{ color: "var(--muted)" }}>|</span>
            <span style={{ color: "var(--muted)" }}>{sys.active_node ?? "—"}</span>
            <span style={{ color: "var(--muted)" }}>|</span>
            <span className="updated-time">
              {sys.last_heartbeat ? `HB ${fmt.time(sys.last_heartbeat)}` : "NO HEARTBEAT"}
            </span>
          </div>
        </div>

        <div className="main">

          {/* ── KILL SWITCH ── */}
          <KillSwitch status={stats} />

          {/* ── TOP STATS ── */}
          <div className="grid-4">
            <StatCard
              label="Portfolio Equity"
              value={fmt.currency(equity)}
              sub={`Started at ${fmt.currency(startEquity)}`}
              color={totalReturn >= 0 ? "green" : "red"}
            />
            <StatCard
              label="Total Return"
              value={fmt.pct(totalReturn)}
              sub={`${totalTrades} trades closed`}
              color={totalReturn >= 0 ? "green" : "red"}
            />
            <StatCard
              label="Max Drawdown"
              value={`-${Number(maxDD).toFixed(2)}%`}
              sub="Peak-to-trough"
              color={maxDD > 8 ? "red" : maxDD > 4 ? "amber" : ""}
            />
            <StatCard
              label="Circuit Breaker"
              value={stats.circuit_breaker ? "ACTIVE" : "CLEAR"}
              sub={`Streak: ${stats.streak_state ?? "neutral"}`}
              color={stats.circuit_breaker ? "red" : "green"}
            />
          </div>

          <div className="grid-4">
            <StatCard
              label="Win Rate"
              value={fmt.pct(stats.win_rate)}
              sub={`${stats.wins ?? 0}W / ${stats.losses ?? 0}L`}
              color={(stats.win_rate ?? 0) >= 50 ? "green" : "amber"}
            />
            <StatCard
              label="Profit Factor"
              value={fmt.num2(stats.profit_factor)}
              sub="Gross profit / loss"
              color={(stats.profit_factor ?? 0) >= 1.5 ? "green" : "amber"}
            />
            <StatCard
              label="Sharpe Ratio"
              value={fmt.num2(stats.sharpe_ratio)}
              sub="Annualised"
              color={(stats.sharpe_ratio ?? 0) >= 0.8 ? "green" : "amber"}
            />
            <StatCard
              label="Expectancy"
              value={fmt.r(stats.expectancy_r)}
              sub={`Risk A+: ${stats.risk_a_plus ?? "?"}%`}
              color={(stats.expectancy_r ?? 0) >= 0.1 ? "green" : "amber"}
            />
          </div>

          {/* ── READINESS GATE ── */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div className="section-title" style={{ margin: 0, border: "none", padding: 0 }}>
                READINESS GATE — PAPER TO LIVE
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 700, color: readiness ? "var(--accent)" : "var(--muted)" }}>
                {readiness ? "✅ GATE PASSED" : `${totalTrades} / ${minTrades} TRADES`}
              </div>
            </div>
            <div className="heat-bar-bg">
              <div
                className={`heat-bar-fill ${readiness ? "" : totalTrades / minTrades > 0.8 ? "" : "warn"}`}
                style={{ width: `${Math.min(totalTrades / minTrades * 100, 100)}%` }}
              />
            </div>
          </div>

          {/* ── EQUITY CURVE + COMPARISON ── */}
          <div className="grid-3">
            <div className="card">
              <div className="section-title">EQUITY CURVE</div>
              <EquityChart curve={equityCurve} />
            </div>
            <div className="card">
              <ComparisonPanel stats={stats} />
              <div style={{ marginTop: 16 }}>
                <div className="section-title">PORTFOLIO HEAT</div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 22, fontWeight: 700, color: heatPct > 5 ? "var(--loss)" : heatPct > 3 ? "var(--warn)" : "var(--accent)" }}>
                  {heatPct.toFixed(1)}%
                </div>
                <div className="heat-bar-bg">
                  <div
                    className={`heat-bar-fill ${heatPct > 5 ? "crit" : heatPct > 3 ? "warn" : ""}`}
                    style={{ width: `${Math.min(heatPct / 6.5 * 100, 100)}%` }}
                  />
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--muted)", marginTop: 6 }}>
                  MAX 6.0% TOTAL · 3.0% PER MARKET · EMERGENCY AT 6.5%
                </div>
              </div>
            </div>
          </div>

          {/* ── DAILY BIAS ── */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="section-title">TODAY'S BIAS — {todayStr}</div>
            <BiasPanel bias={todayBias} />
          </div>

          {/* ── OPEN POSITIONS ── */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="section-title">
              OPEN POSITIONS ({positions?.length ?? 0})
            </div>
            <PositionsTable positions={positions} />
          </div>

          {/* ── TRADE JOURNAL ── */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="section-title">
              TRADE JOURNAL — LAST 50 CLOSED
            </div>
            <TradesTable trades={trades} />
          </div>

          {/* ── SYSTEM STATUS ── */}
          <div className="grid-4">
            <StatCard label="Active Node"    value={sys.active_node ?? "—"}           />
            <StatCard label="Uptime"         value={sys.uptime_h ? `${Number(sys.uptime_h).toFixed(1)}h` : "—"} />
            <StatCard label="Open Positions" value={sys.open_positions ?? 0}           />
            <StatCard label="Python"         value={sys.python_version ?? "—"}         />
          </div>

          {/* ── FOOTER ── */}
          <div style={{ marginTop: 24, padding: "16px 0", borderTop: "1px solid var(--border)", fontFamily: "var(--mono)", fontSize: 9, color: "var(--muted)", letterSpacing: 2, display: "flex", justifyContent: "space-between" }}>
            <span>CRAVE v10.3 · SMC ALGORITHMIC TRADING · PAPER MODE</span>
            <span>DATA PUSHES EVERY 10s · KILL SWITCH POLLS EVERY 5s</span>
            <span>CHARANBHARGAV6 / CRAVE</span>
          </div>

        </div>
      </div>
    </>
  );
}
