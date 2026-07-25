import { useState, useEffect, useCallback } from "react";
import { Search, RefreshCw } from "lucide-react";
import { api } from "../api";
import { useInterval } from "../hooks/useInterval";

const SIGNAL_COLORS = {
  BUY : "#26a69a",
  SELL: "#ef5350",
};

const COL_ORDER = ["Time", "Ticker", "Signal", "SignalType", "Score", "Price", "Value", "Metric1", "Metric2", "Metric3", "Array", "FinalScore", "Source"];

export default function SignalsPage() {
  const [files,         setFiles]         = useState([]);
  const [selectedFile,  setSelectedFile]  = useState("");
  const [signalFilter,  setSignalFilter]  = useState("");
  const [search,        setSearch]        = useState("");
  const [limit,         setLimit]         = useState(200);
  const [signals,       setSignals]       = useState([]);
  const [loading,       setLoading]       = useState(false);
  const [lastUpdate,    setLastUpdate]    = useState(null);

  // Load file list once
  useEffect(() => {
    api.signalFiles().then(r => setFiles(r.files)).catch(() => {});
  }, []);

  const fetchSignals = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.signals(selectedFile || undefined, limit, signalFilter || undefined, search || undefined);
      setSignals(r.signals);
      setLastUpdate(new Date().toLocaleTimeString("en-IN"));
    } catch (_) {}
    setLoading(false);
  }, [selectedFile, limit, signalFilter, search]);

  useEffect(() => { fetchSignals(); }, [fetchSignals]);
  useInterval(fetchSignals, 3000); // auto-poll every 3s

  // All unique columns across data
  const cols = signals.length
    ? COL_ORDER.filter(c => signals.some(s => s[c] !== undefined))
    : [];

  return (
    <div style={{ background: "#0d0d0d", minHeight: "100vh", padding: "16px 20px" }}>
      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 style={{ color: "#e0e0e0", fontSize: 18, margin: 0 }}>📋 Signals Dashboard</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {lastUpdate && <span style={{ fontSize: 11, color: "#555" }}>Updated {lastUpdate}</span>}
          <button onClick={fetchSignals} style={btnStyle}>
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* ── Filters ── */}
      <div style={{
        display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end",
        background: "#111", padding: "12px 16px", borderRadius: 8,
        border: "1px solid #222", marginBottom: 16,
      }}>
        {/* Search */}
        <div style={{ flex: 2, minWidth: 160, position: "relative" }}>
          <Search size={12} style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: "#555" }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search…"
            style={{ ...inputStyle, paddingLeft: 26 }}
          />
        </div>

        {/* Signal type */}
        <div>
          <label style={labelStyle}>Signal</label>
          <select value={signalFilter} onChange={e => setSignalFilter(e.target.value)} style={inputStyle}>
            <option value="">All</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </div>

        {/* File */}
        <div style={{ minWidth: 160 }}>
          <label style={labelStyle}>File</label>
          <select value={selectedFile} onChange={e => setSelectedFile(e.target.value)} style={inputStyle}>
            <option value="">All files</option>
            {files.map(f => <option key={f}>{f}</option>)}
          </select>
        </div>

        {/* Limit */}
        <div>
          <label style={labelStyle}>Rows / file</label>
          <input
            type="number" min={10} max={1000} value={limit}
            onChange={e => setLimit(Number(e.target.value))}
            style={{ ...inputStyle, width: 70 }}
          />
        </div>
      </div>

      {/* ── Status ── */}
      <div style={{ fontSize: 12, color: "#555", marginBottom: 10 }}>
        {loading ? "Loading…" : `${signals.length} signal${signals.length !== 1 ? "s" : ""} — auto-refresh every 3s`}
      </div>

      {/* ── Table ── */}
      {signals.length === 0 && !loading ? (
        <div style={{ color: "#444", textAlign: "center", paddingTop: 60, fontSize: 14 }}>
          No signals found. Make sure the Signals/ folder contains .txt files.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ position: "sticky", top: 0, background: "#161616", zIndex: 2 }}>
                {cols.map(c => (
                  <th key={c} style={{
                    padding: "8px 10px", textAlign: "left",
                    color: "#555", fontWeight: 600, textTransform: "uppercase",
                    fontSize: 10, letterSpacing: 0.5,
                    borderBottom: "1px solid #1e1e1e",
                  }}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {signals.map((row, i) => {
                const sig = row.SignalType || row.Score || "";
                const isBuy  = sig === "BUY"  || sig === "Buy";
                const isSell = sig === "SELL" || sig === "Sell";
                return (
                  <tr
                    key={i}
                    style={{
                      background: i % 2 === 0 ? "#111" : "#131313",
                      borderBottom: "1px solid #1a1a1a",
                      transition: "background 0.1s",
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "#1a2a1a"}
                    onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "#111" : "#131313"}
                  >
                    {cols.map(c => (
                      <td key={c} style={{
                        padding: "6px 10px",
                        color: c === "SignalType" || c === "Score"
                          ? (isBuy ? SIGNAL_COLORS.BUY : isSell ? SIGNAL_COLORS.SELL : "#888")
                          : c === "Ticker" ? "#e0e0e0"
                          : c === "Source" ? "#444"
                          : "#888",
                        fontWeight: c === "Ticker" || c === "SignalType" ? 600 : 400,
                        whiteSpace: "nowrap",
                      }}>
                        {row[c] ?? "—"}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
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
  background: "#1a1a1a", border: "1px solid #333", color: "#888",
  borderRadius: 5, padding: "6px 8px", cursor: "pointer",
};
