import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../api";
import CandleChart from "./CandleChart";
import RsiChart from "./RsiChart";

export default function TickerCard({ ticker, interval, period, settings, refreshSignal }) {
  const [candles,    setCandles]    = useState(null);
  const [indicators, setIndicators] = useState(null);
  const [structure,  setStructure]  = useState(null);
  const [pdh,        setPdh]        = useState(null);
  const [pdl,        setPdl]        = useState(null);
  const [error,      setError]      = useState(null);
  const [loading,    setLoading]    = useState(true);

  const lastFetch = useRef(0);

  const fetchAll = useCallback(async () => {
    const now = Date.now();
    if (now - lastFetch.current < 4000) return; // debounce
    lastFetch.current = now;
    setLoading(true);
    setError(null);
    try {
      const [ohlcRes, indRes] = await Promise.all([
        api.ohlc(ticker, interval, period),
        api.indicators(ticker, interval, period),
      ]);
      setCandles(ohlcRes.candles);
      setIndicators(indRes);

      // structure & PDH/PDL in background
      api.structure(ticker, interval, period).then(setStructure).catch(() => {});
      api.pdh_pdl(ticker).then(r => { setPdh(r.pdh); setPdl(r.pdl); }).catch(() => {});
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [ticker, interval, period]);

  useEffect(() => { fetchAll(); }, [fetchAll, refreshSignal]);

  const latest = candles?.at(-1);
  const prev   = candles?.at(-2);
  const delta  = latest && prev ? (latest.c - prev.c) : null;
  const pct    = delta !== null && prev ? (delta / prev.c * 100) : null;
  const isUp   = delta === null ? null : delta >= 0;

  return (
    <div style={{
      background: "#1a1a1a", border: "1px solid #2a2a2a", borderRadius: 8,
      padding: "12px 16px", marginBottom: 16,
    }}>
      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ color: "#e0e0e0", fontWeight: 700, fontSize: 15 }}>{ticker}</span>
          <span style={{ color: "#666", fontSize: 12 }}>{interval} · {period}</span>
        </div>
        {latest && (
          <div style={{ textAlign: "right" }}>
            <span style={{ fontSize: 16, fontWeight: 700, color: isUp ? "#26a69a" : "#ef5350" }}>
              ₹{latest.c?.toFixed(2)}
            </span>
            {delta !== null && (
              <span style={{ marginLeft: 8, fontSize: 12, color: isUp ? "#26a69a" : "#ef5350" }}>
                {isUp ? "▲" : "▼"} {Math.abs(delta).toFixed(2)} ({Math.abs(pct).toFixed(2)}%)
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── OHLC row ── */}
      {latest && (
        <div style={{ display: "flex", gap: 16, fontSize: 11, color: "#888", marginBottom: 8 }}>
          <span>O <b style={{ color: "#ccc" }}>{latest.o?.toFixed(2)}</b></span>
          <span>H <b style={{ color: "#26a69a" }}>{latest.h?.toFixed(2)}</b></span>
          <span>L <b style={{ color: "#ef5350" }}>{latest.l?.toFixed(2)}</b></span>
          <span>C <b style={{ color: "#ccc" }}>{latest.c?.toFixed(2)}</b></span>
          {latest.v && <span>Vol <b style={{ color: "#ccc" }}>{(latest.v / 1000).toFixed(1)}K</b></span>}
          {pdh && <span>PDH <b style={{ color: "#ffb74d" }}>{pdh.toFixed(2)}</b></span>}
          {pdl && <span>PDL <b style={{ color: "#81d4fa" }}>{pdl.toFixed(2)}</b></span>}
        </div>
      )}

      {/* ── States ── */}
      {loading && <div style={{ color: "#555", padding: "60px 0", textAlign: "center", fontSize: 13 }}>Loading {ticker}…</div>}
      {error   && <div style={{ color: "#ef5350", padding: "20px 0", textAlign: "center", fontSize: 13 }}>⚠ {error}</div>}

      {!loading && !error && candles?.length && (
        <>
          <CandleChart
            ticker={ticker}
            candles={candles}
            indicators={indicators}
            structure={structure}
            pdh={pdh}
            pdl={pdl}
            settings={settings}
            showLine={settings?.showLine}
          />

          {/* RSI sub-chart */}
          {settings?.showRsi && indicators?.rsi?.length && (
            <div style={{ marginTop: 4 }}>
              <div style={{ fontSize: 10, color: "#555", marginBottom: 2, paddingLeft: 4 }}>RSI (14)</div>
              <RsiChart rsiData={indicators.rsi} />
            </div>
          )}

          {/* FVG table */}
          {settings?.showFvg && structure?.fvg?.length > 0 && (
            <FvgTable fvg={structure.fvg} />
          )}
        </>
      )}
    </div>
  );
}

function FvgTable({ fvg }) {
  const active = fvg.filter(f => !f.mitigated);
  if (!active.length) return null;
  return (
    <div style={{ marginTop: 10, overflowX: "auto" }}>
      <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>Active FVGs ({active.length})</div>
      <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ color: "#666" }}>
            {["Time", "Direction", "Top", "Bottom"].map(h => (
              <th key={h} style={{ padding: "2px 8px", textAlign: "left", borderBottom: "1px solid #2a2a2a" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {active.slice(-10).map((f, i) => (
            <tr key={i} style={{ color: f.direction === "Bullish" ? "#26a69a" : "#ef5350" }}>
              <td style={{ padding: "2px 8px" }}>{new Date(f.t).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</td>
              <td style={{ padding: "2px 8px" }}>{f.direction === "Bullish" ? "▲ Bull" : "▼ Bear"}</td>
              <td style={{ padding: "2px 8px" }}>{f.top.toFixed(2)}</td>
              <td style={{ padding: "2px 8px" }}>{f.bottom.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
