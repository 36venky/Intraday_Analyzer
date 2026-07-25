import { useState, useCallback, useEffect } from "react";
import { RefreshCw } from "lucide-react";
import Sidebar from "../components/Sidebar";
import TickerCard from "../components/TickerCard";
import { useMarketStatus } from "../hooks/useMarketStatus";
import { useInterval } from "../hooks/useInterval";

const INTERVALS = ["1m", "5m", "15m", "1h", "1d"];

const PERIODS_BY_INTERVAL = {
  "1m"  : ["1d", "5d"],
  "5m"  : ["1d", "2d", "5d", "15d", "1mo"],
  "15m" : ["1d", "2d", "5d", "15d", "1mo"],
  "1h"  : ["1d", "5d", "1mo", "3mo"],
  "1d"  : ["1mo", "3mo", "6mo", "1y"],
};

const DEFAULT_SETTINGS = {
  showLine        : false,
  showEma         : false,
  showVwap        : false,
  showPdhPdl      : false,
  showSwings      : false,
  showSwingZones  : false,
  showSupports    : false,
  showResistance  : false,
  showTrendlines  : false,
  showFvg         : false,
  showRsi         : false,
};

export default function GraphPage() {
  const [tickerInput,   setTickerInput]   = useState("ETERNAL.NS");
  const [interval,      setInterval]      = useState("15m");
  const [period,        setPeriod]        = useState("5d");
  const [refreshRate,   setRefreshRate]   = useState(30);
  const [settings,      setSettings]      = useState(DEFAULT_SETTINGS);
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [columns,       setColumns]       = useState(2);

  const status = useMarketStatus();

  const tickers = tickerInput
    .split(",")
    .map(t => t.trim().toUpperCase())
    .filter(Boolean);

  const validPeriods = PERIODS_BY_INTERVAL[interval] || ["5d"];

  // Auto-correct period when interval changes
  useEffect(() => {
    if (!validPeriods.includes(period)) setPeriod(validPeriods[0]);
  }, [interval]); // eslint-disable-line

  // Auto-refresh
  const handleRefresh = useCallback(() => setRefreshSignal(s => s + 1), []);
  useInterval(handleRefresh, status.open ? refreshRate * 1000 : null);

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "#0d0d0d" }}>
      <Sidebar settings={settings} onChange={setSettings} />

      <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
        {/* ── Controls ── */}
        <div style={{
          display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end",
          background: "#111", padding: "12px 16px", borderRadius: 8,
          border: "1px solid #222", marginBottom: 16,
        }}>
          {/* Ticker input */}
          <div style={{ flex: 2, minWidth: 200 }}>
            <label style={labelStyle}>Tickers (comma-separated)</label>
            <input
              value={tickerInput}
              onChange={e => setTickerInput(e.target.value)}
              style={inputStyle}
              placeholder="e.g. RELIANCE.NS, TCS.NS"
            />
          </div>

          {/* Interval */}
          <div>
            <label style={labelStyle}>Interval</label>
            <select value={interval} onChange={e => setInterval(e.target.value)} style={inputStyle}>
              {INTERVALS.map(i => <option key={i}>{i}</option>)}
            </select>
          </div>

          {/* Period */}
          <div>
            <label style={labelStyle}>Period</label>
            <select value={period} onChange={e => setPeriod(e.target.value)} style={inputStyle}>
              {validPeriods.map(p => <option key={p}>{p}</option>)}
            </select>
          </div>

          {/* Refresh rate */}
          <div>
            <label style={labelStyle}>Refresh (s)</label>
            <input
              type="number" min={5} max={300} value={refreshRate}
              onChange={e => setRefreshRate(Number(e.target.value))}
              style={{ ...inputStyle, width: 70 }}
            />
          </div>

          {/* Columns */}
          <div>
            <label style={labelStyle}>Columns</label>
            <select value={columns} onChange={e => setColumns(Number(e.target.value))} style={inputStyle}>
              {[1, 2, 3].map(c => <option key={c}>{c}</option>)}
            </select>
          </div>

          {/* Refresh button */}
          <button onClick={handleRefresh} style={btnStyle} title="Refresh now">
            <RefreshCw size={14} />
            <span>Refresh</span>
          </button>
        </div>

        {/* ── Market status banner ── */}
        <div style={{
          marginBottom: 12, fontSize: 12,
          color: status.open ? "#26a69a" : "#ef5350",
        }}>
          {status.open
            ? `🟢 Market open — auto-refresh every ${refreshRate}s`
            : `🔴 Market closed (${status.now_ist}) — live refresh paused`}
        </div>

        {/* ── Charts grid ── */}
        {tickers.length === 0 ? (
          <div style={{ color: "#555", textAlign: "center", paddingTop: 80 }}>
            Enter one or more NSE tickers above to get started.
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: `repeat(${columns}, 1fr)`,
            gap: 16,
          }}>
            {tickers.map(t => (
              <TickerCard
                key={t}
                ticker={t}
                interval={interval}
                period={period}
                settings={settings}
                refreshSignal={refreshSignal}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const labelStyle = { display: "block", fontSize: 10, color: "#555", marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 };
const inputStyle = {
  background: "#1a1a1a", border: "1px solid #333", color: "#e0e0e0",
  borderRadius: 5, padding: "6px 10px", fontSize: 13, outline: "none", width: "100%",
};
const btnStyle = {
  display: "flex", alignItems: "center", gap: 6,
  background: "#26a69a22", border: "1px solid #26a69a55", color: "#26a69a",
  borderRadius: 5, padding: "6px 14px", fontSize: 12, cursor: "pointer",
  transition: "background 0.15s",
};
