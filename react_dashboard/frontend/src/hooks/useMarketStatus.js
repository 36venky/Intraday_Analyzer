import { useState, useEffect } from "react";
import { api } from "../api";
import { useInterval } from "./useInterval";

export function useMarketStatus() {
  const [status, setStatus] = useState({ open: false, now_ist: "" });

  const fetch = async () => {
    try {
      const data = await api.marketStatus();
      setStatus(data);
    } catch (_) {}
  };

  useEffect(() => { fetch(); }, []);
  useInterval(fetch, 30_000);

  return status;
}
