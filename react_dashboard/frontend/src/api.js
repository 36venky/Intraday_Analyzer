const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function get(path, params = {}) {
  const url = new URL(BASE + path);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  });
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const api = {
  marketStatus: () => get("/api/market_status"),
  ohlc: (ticker, interval, period) =>
    get("/api/ohlc", { ticker, interval, period }),
  indicators: (ticker, interval, period) =>
    get("/api/indicators", { ticker, interval, period }),
  structure: (ticker, interval, period) =>
    get("/api/structure", { ticker, interval, period }),
  pdh_pdl: (ticker) => get("/api/pdh_pdl", { ticker }),
  signalFiles: () => get("/api/signal_files"),
  signals: (file, limit, signal, search) =>
    get("/api/signals", { file, limit, signal, search }),
};
