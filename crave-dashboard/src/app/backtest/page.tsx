"use client";
import { useState, useEffect, useCallback, useRef } from "react";

// ── Types ──────────────────────────────────────────────────────────────────
interface WindowResult {
  fold: number;
  train_rows: number;
  test_rows: number;
  accuracy: number;
  regime_acc: Record<string, number | null>;
}

interface InstrumentResult {
  symbol: string;
  dataset: string;
  total_rows: number;
  mean_accuracy: number;
  std_accuracy: number;
  min_accuracy: number;
  max_accuracy: number;
  degradation: number;
  n_folds: number;
  windows: WindowResult[];
}

interface StatusPayload {
  status: "idle" | "running" | "done" | "error";
  progress: number;
  message: string;
  updated_at?: string;
  results: InstrumentResult[];
  source?: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────
const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const clr = (v: number) =>
  v >= 0.72 ? "#00e5a0" : v >= 0.60 ? "#f5c842" : "#ff4466";
const degClr = (v: number) => (v >= -0.02 ? "#00e5a0" : v >= -0.06 ? "#f5c842" : "#ff4466");

// ── Radar (SVG) ────────────────────────────────────────────────────────────
function RadarChart({ data }: { data: { label: string; value: number }[] }) {
  const cx = 120, cy = 110, r = 80;
  const n = data.length;
  const pts = (scale: number) =>
    data
      .map((_, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
        return `${cx + Math.cos(angle) * r * scale},${cy + Math.sin(angle) * r * scale}`;
      })
      .join(" ");

  const valuePts = data
    .map((d, i) => {
      const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
      return `${cx + Math.cos(angle) * r * d.value},${cy + Math.sin(angle) * r * d.value}`;
    })
    .join(" ");

  return (
    <svg width={240} height={220} style={{ overflow: "visible" }}>
      {[0.25, 0.5, 0.75, 1].map((s) => (
        <polygon
          key={s}
          points={pts(s)}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={1}
        />
      ))}
      {data.map((_, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={cx + Math.cos(angle) * r}
            y2={cy + Math.sin(angle) * r}
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={1}
          />
        );
      })}
      <polygon points={valuePts} fill="rgba(0,229,160,0.15)" stroke="#00e5a0" strokeWidth={1.5} />
      {data.map((d, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
        const lx = cx + Math.cos(angle) * (r + 20);
        const ly = cy + Math.sin(angle) * (r + 20);
        return (
          <text
            key={i}
            x={lx}
            y={ly}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize={9}
            fill="rgba(255,255,255,0.55)"
            fontFamily="'Space Mono', monospace"
          >
            {d.label}
          </text>
        );
      })}
    </svg>
  );
}

// ── Mini fold chart ────────────────────────────────────────────────────────
function FoldChart({ windows }: { windows: WindowResult[] }) {
  const max = 0.95, min = 0.4, h = 48, w = 200;
  const pts = windows.map((wn, i) => {
    const x = (i / (windows.length - 1 || 1)) * w;
    const y = h - ((wn.accuracy - min) / (max - min)) * h;
    return `${x},${y}`;
  });

  return (
    <svg width={w} height={h + 4} style={{ overflow: "visible" }}>
      <polyline
        points={pts.join(" ")}
        fill="none"
        stroke="#00e5a0"
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
      {windows.map((wn, i) => {
        const x = (i / (windows.length - 1 || 1)) * w;
        const y = h - ((wn.accuracy - min) / (max - min)) * h;
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={3}
            fill={clr(wn.accuracy)}
            stroke="#080c10"
            strokeWidth={1}
          />
        );
      })}
    </svg>
  );
}

// ── Progress bar ───────────────────────────────────────────────────────────
function ProgressBar({ pct: p, pulse }: { pct: number; pulse: boolean }) {
  return (
    <div style={{ position: "relative", height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          height: "100%",
          width: `${p}%`,
          background: "linear-gradient(90deg,#00e5a0,#3d8eff)",
          borderRadius: 3,
          transition: "width 0.5s ease",
          animation: pulse ? "shimmer 1.5s infinite" : "none",
        }}
      />
      <style>{`@keyframes shimmer{0%,100%{opacity:1}50%{opacity:0.6}}`}</style>
    </div>
  );
}

// ── Dataset badges ─────────────────────────────────────────────────────────
const DATASETS: Record<string, { name: string; color: string; years: string; note: string }> = {
  binance:  { name: "Binance", color: "#f0b90b", years: "4yr", note: "No API key needed · Public REST" },
  yfinance: { name: "Yahoo Finance", color: "#6001d2", years: "5yr", note: "Free · yfinance wrapper" },
};

// ══════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ══════════════════════════════════════════════════════════════════════════
export default function BacktestPage() {
  const [state, setState] = useState<StatusPayload>({
    status: "idle", progress: 0, message: "", results: [],
  });
  const [selected, setSelected] = useState<number | null>(null);
  const [launching, setLaunching] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res  = await fetch("/api/backtest-results");
      const data = await res.json();
      setState(data);
      if (data.status === "done" || data.status === "error") {
        if (pollRef.current) clearInterval(pollRef.current);
      }
    } catch {/* ignore */}
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Start polling while running
  useEffect(() => {
    if (state.status === "running") {
      if (!pollRef.current) {
        pollRef.current = setInterval(fetchStatus, 4000);
      }
    } else {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [state.status, fetchStatus]);

  const triggerRun = async () => {
    setLaunching(true);
    await fetch("/api/backtest-results", { method: "POST" });
    setTimeout(() => {
      setLaunching(false);
      fetchStatus();
      pollRef.current = setInterval(fetchStatus, 4000);
    }, 800);
  };

  const selResult = selected !== null ? state.results[selected] : null;

  const REGIMES = ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE"];
  const REGIME_SHORT: Record<string, string> = {
    TRENDING_UP: "↑ TREND", TRENDING_DOWN: "↓ TREND",
    RANGING: "RANGE", VOLATILE: "VOLAT",
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "#080c10",
      backgroundImage: "linear-gradient(rgba(255,255,255,0.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.025) 1px,transparent 1px)",
      backgroundSize: "40px 40px",
      color: "#c8d8e8",
      fontFamily: "'Barlow', sans-serif",
      padding: "0 0 80px",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Barlow:wght@300;400;500;600;700;900&display=swap');
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: #0d1117; }
        ::-webkit-scrollbar-thumb { background: #243040; border-radius: 2px; }
        .card { background: rgba(13,17,23,0.9); border: 1px solid #1c2836; border-radius: 4px; }
        .card:hover { border-color: #243040; }
        .mono { font-family: 'Space Mono', monospace; }
        .btn { background: transparent; border: 1px solid #00e5a0; color: #00e5a0; padding: 10px 24px;
               border-radius: 2px; cursor: pointer; font-family: 'Space Mono',monospace; font-size: 12px;
               letter-spacing: 0.08em; text-transform: uppercase; transition: all 0.15s; }
        .btn:hover:not(:disabled) { background: #00e5a0; color: #080c10; }
        .btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .tag { display: inline-block; padding: 2px 8px; border-radius: 2px; font-size: 10px;
               font-family: 'Space Mono',monospace; font-weight: 700; letter-spacing: 0.05em; }
        .row-sel { cursor: pointer; transition: background 0.1s; }
        .row-sel:hover { background: rgba(0,229,160,0.04) !important; }
        .row-sel.active { background: rgba(0,229,160,0.07) !important; border-left: 2px solid #00e5a0; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .spin { animation: spin 1.2s linear infinite; display: inline-block; }
      `}</style>

      {/* ── TOP BAR ─────────────────────────────────────────────────────── */}
      <div style={{
        position: "sticky", top: 0, zIndex: 100,
        background: "rgba(8,12,16,0.95)", backdropFilter: "blur(12px)",
        borderBottom: "1px solid #1c2836",
        padding: "0 32px",
        display: "flex", alignItems: "center", gap: 24, height: 56,
      }}>
        <span style={{ color: "#00e5a0", fontSize: 11, fontFamily: "Space Mono", letterSpacing: "0.15em" }}>
          CRAVE
        </span>
        <span style={{ color: "#1c2836", fontSize: 18 }}>|</span>
        <span style={{ fontSize: 12, color: "#4a6070", letterSpacing: "0.08em" }}>
          ML BACKTEST RESULTS
        </span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
          {state.status === "running" && (
            <span style={{ fontSize: 11, color: "#f5c842", fontFamily: "Space Mono" }}>
              <span className="spin">⟳</span> {state.progress}% — {state.message}
            </span>
          )}
          {state.status === "done" && (
            <span style={{ fontSize: 11, color: "#00e5a0", fontFamily: "Space Mono" }}>
              ✓ COMPLETE
            </span>
          )}
          <button className="btn" onClick={triggerRun}
            disabled={launching || state.status === "running"}>
            {launching ? "LAUNCHING…" : state.status === "running" ? "RUNNING…" : "▶ RUN BACKTEST"}
          </button>
        </div>
      </div>

      <div style={{ padding: "28px 32px", maxWidth: 1280, margin: "0 auto" }}>

        {/* ── DATASETS INFO ─────────────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))", gap: 12, marginBottom: 28 }}>
          {[
            { name: "Binance (Public)", color: "#f0b90b", note: "BTCUSDT + ETHUSDT · 1H · 4yr · No API key", icon: "₿" },
            { name: "Yahoo Finance", color: "#6001d2", note: "Gold, EUR/USD, NIFTY50, SPY · 1H · 5yr · Free", icon: "📈" },
            { name: "XGBoost Classifier", color: "#3d8eff", note: "6-fold walk-forward · StandardScaler · 150 trees", icon: "🤖" },
            { name: "Ground-Truth Labels", color: "#00e5a0", note: "10-bar forward EMA alignment · session-tagged", icon: "🏷" },
          ].map((d) => (
            <div key={d.name} className="card" style={{ padding: "14px 16px", display: "flex", gap: 12, alignItems: "flex-start" }}>
              <span style={{ fontSize: 20 }}>{d.icon}</span>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: d.color, marginBottom: 3 }}>{d.name}</div>
                <div style={{ fontSize: 11, color: "#4a6070" }}>{d.note}</div>
              </div>
            </div>
          ))}
        </div>

        {/* ── PROGRESS BAR ──────────────────────────────────────────────── */}
        {(state.status === "running" || state.status === "done") && (
          <div className="card" style={{ padding: "16px 20px", marginBottom: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: 11, fontFamily: "Space Mono", color: "#4a6070" }}>PROGRESS</span>
              <span style={{ fontSize: 11, fontFamily: "Space Mono", color: "#c8d8e8" }}>{state.progress}%</span>
            </div>
            <ProgressBar pct={state.progress} pulse={state.status === "running"} />
            <div style={{ marginTop: 8, fontSize: 11, color: "#4a6070" }}>{state.message}</div>
          </div>
        )}

        {/* ── IDLE STATE ────────────────────────────────────────────────── */}
        {state.status === "idle" && state.results.length === 0 && (
          <div className="card" style={{ padding: "60px 40px", textAlign: "center" }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🧠</div>
            <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>No backtest run yet</div>
            <div style={{ fontSize: 13, color: "#4a6070", marginBottom: 28, maxWidth: 480, margin: "0 auto 28px" }}>
              Click <strong style={{ color: "#00e5a0" }}>▶ RUN BACKTEST</strong> to download datasets, train the XGBoost
              regime classifier, and run 6-fold walk-forward validation on all instruments.
              Results post here automatically when complete.
            </div>
            <button className="btn" onClick={triggerRun} disabled={launching}>
              {launching ? "LAUNCHING…" : "▶ RUN BACKTEST"}
            </button>
          </div>
        )}

        {/* ── RESULTS TABLE + DETAIL PANEL ──────────────────────────────── */}
        {state.results.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: selResult ? "1fr 360px" : "1fr", gap: 16 }}>

            {/* Table */}
            <div className="card" style={{ overflow: "hidden" }}>
              <div style={{ padding: "14px 20px", borderBottom: "1px solid #1c2836", fontSize: 11,
                fontFamily: "Space Mono", color: "#4a6070", letterSpacing: "0.1em" }}>
                INSTRUMENT RESULTS
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "#0d1117" }}>
                    {["INSTRUMENT","DATASET","ROWS","MEAN ACC","±STD","MIN","MAX","TREND","FOLDS"].map(h => (
                      <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 10,
                        color: "#4a6070", fontFamily: "Space Mono", letterSpacing: "0.08em",
                        borderBottom: "1px solid #1c2836", fontWeight: 400 }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {state.results.map((r, i) => {
                    const verdict = r.mean_accuracy >= 0.72 ? "PASS" : r.mean_accuracy >= 0.60 ? "OK" : "FAIL";
                    const vColor  = r.mean_accuracy >= 0.72 ? "#00e5a0" : r.mean_accuracy >= 0.60 ? "#f5c842" : "#ff4466";
                    return (
                      <tr key={i}
                        className={`row-sel ${selected === i ? "active" : ""}`}
                        onClick={() => setSelected(selected === i ? null : i)}
                        style={{ borderBottom: "1px solid #1c2836" }}>
                        <td style={{ padding: "12px 14px" }}>
                          <div style={{ fontWeight: 700, fontSize: 13 }}>{r.symbol}</div>
                          <span className="tag" style={{ background: `${vColor}18`, color: vColor, marginTop: 4 }}>
                            {verdict}
                          </span>
                        </td>
                        <td style={{ padding: "12px 14px" }}>
                          <span className="tag" style={{
                            background: r.dataset === "binance" ? "#f0b90b18" : "#6001d218",
                            color: r.dataset === "binance" ? "#f0b90b" : "#9b59ff"
                          }}>
                            {DATASETS[r.dataset]?.name || r.dataset}
                          </span>
                        </td>
                        <td className="mono" style={{ padding: "12px 14px", color: "#4a6070", fontSize: 11 }}>
                          {r.total_rows.toLocaleString()}
                        </td>
                        <td className="mono" style={{ padding: "12px 14px", color: clr(r.mean_accuracy), fontWeight: 700, fontSize: 14 }}>
                          {pct(r.mean_accuracy)}
                        </td>
                        <td className="mono" style={{ padding: "12px 14px", color: "#4a6070", fontSize: 11 }}>
                          ±{pct(r.std_accuracy)}
                        </td>
                        <td className="mono" style={{ padding: "12px 14px", color: "#4a6070", fontSize: 11 }}>
                          {pct(r.min_accuracy)}
                        </td>
                        <td className="mono" style={{ padding: "12px 14px", color: "#4a6070", fontSize: 11 }}>
                          {pct(r.max_accuracy)}
                        </td>
                        <td style={{ padding: "12px 14px" }}>
                          {r.windows.length > 1 && <FoldChart windows={r.windows} />}
                        </td>
                        <td className="mono" style={{ padding: "12px 14px",
                          color: degClr(r.degradation), fontSize: 12 }}>
                          {r.degradation >= 0 ? "+" : ""}{(r.degradation * 100).toFixed(1)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Detail Panel */}
            {selResult && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="card" style={{ padding: "16px 20px" }}>
                  <div style={{ fontSize: 18, fontWeight: 900, marginBottom: 4 }}>{selResult.symbol}</div>
                  <div style={{ fontSize: 11, color: "#4a6070", marginBottom: 16 }}>
                    {selResult.total_rows.toLocaleString()} rows · {selResult.n_folds} folds
                  </div>

                  <RadarChart data={[
                    { label: "MEAN ACC", value: selResult.mean_accuracy },
                    { label: "MIN ACC",  value: selResult.min_accuracy  },
                    { label: "STABILITY", value: Math.max(0, 1 - selResult.std_accuracy * 5) },
                    { label: "TREND",    value: Math.max(0, 0.5 + selResult.degradation * 2) },
                    { label: "MAX ACC",  value: selResult.max_accuracy  },
                  ]} />
                </div>

                {/* Per-regime accuracy */}
                <div className="card" style={{ padding: "16px 20px" }}>
                  <div style={{ fontSize: 10, fontFamily: "Space Mono", color: "#4a6070",
                    letterSpacing: "0.1em", marginBottom: 12 }}>PER-REGIME ACCURACY</div>
                  {REGIMES.map(regime => {
                    const vals = selResult.windows
                      .map(w => w.regime_acc?.[regime])
                      .filter((v): v is number => v !== null && v !== undefined);
                    const avg = vals.length > 0 ? vals.reduce((a,b) => a+b,0)/vals.length : null;
                    return (
                      <div key={regime} style={{ marginBottom: 10 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                          <span style={{ fontSize: 11, color: "#c8d8e8" }}>{REGIME_SHORT[regime]}</span>
                          <span className="mono" style={{ fontSize: 11, color: avg ? clr(avg) : "#4a6070" }}>
                            {avg !== null ? pct(avg) : "N/A"}
                          </span>
                        </div>
                        <div style={{ height: 4, background: "rgba(255,255,255,0.06)", borderRadius: 2 }}>
                          <div style={{
                            height: "100%", borderRadius: 2,
                            width: avg !== null ? `${avg*100}%` : "0%",
                            background: avg ? clr(avg) : "#4a6070",
                            transition: "width 0.6s ease"
                          }}/>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Per fold table */}
                <div className="card" style={{ padding: "16px 20px" }}>
                  <div style={{ fontSize: 10, fontFamily: "Space Mono", color: "#4a6070",
                    letterSpacing: "0.1em", marginBottom: 12 }}>FOLD BREAKDOWN</div>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        {["Fold","Train","Test","Acc"].map(h => (
                          <th key={h} style={{ padding: "6px 8px", textAlign: "left", fontSize: 9,
                            color: "#4a6070", fontFamily: "Space Mono", borderBottom: "1px solid #1c2836" }}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {selResult.windows.map(wn => (
                        <tr key={wn.fold} style={{ borderBottom: "1px solid #1c2836" }}>
                          <td className="mono" style={{ padding: "7px 8px", fontSize: 11 }}>#{wn.fold}</td>
                          <td className="mono" style={{ padding: "7px 8px", fontSize: 10, color: "#4a6070" }}>
                            {wn.train_rows.toLocaleString()}
                          </td>
                          <td className="mono" style={{ padding: "7px 8px", fontSize: 10, color: "#4a6070" }}>
                            {wn.test_rows.toLocaleString()}
                          </td>
                          <td className="mono" style={{ padding: "7px 8px", fontSize: 12,
                            fontWeight: 700, color: clr(wn.accuracy) }}>
                            {pct(wn.accuracy)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── HOW TO INTERPRET ─────────────────────────────────────────── */}
        <div className="card" style={{ padding: "18px 24px", marginTop: 20, display: "grid",
          gridTemplateColumns: "repeat(auto-fill,minmax(200px,1fr))", gap: 16 }}>
          {[
            { label: "≥ 72%", note: "Production ready — deploy ML regime filter", color: "#00e5a0" },
            { label: "60–72%", note: "Marginal — deploy with 0.60 confidence gate", color: "#f5c842" },
            { label: "< 60%", note: "Fail — collect more paper trades before using ML", color: "#ff4466" },
            { label: "Degradation", note: "< -5% across folds = model overfitting to early data", color: "#3d8eff" },
          ].map(g => (
            <div key={g.label} style={{ display: "flex", gap: 10 }}>
              <div style={{ width: 3, background: g.color, borderRadius: 2, flexShrink: 0 }}/>
              <div>
                <div className="mono" style={{ fontSize: 12, color: g.color, fontWeight: 700 }}>{g.label}</div>
                <div style={{ fontSize: 11, color: "#4a6070", marginTop: 2 }}>{g.note}</div>
              </div>
            </div>
          ))}
        </div>

      </div>
    </div>
  );
}
