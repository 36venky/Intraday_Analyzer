import { useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";

const COLORS = {
  bull      : "#26a69a",
  bear      : "#ef5350",
  ema9      : "#ffd54f",
  ema21     : "#ce93d8",
  vwap      : "#80cbc4",
  pdh       : "#ffb74d",
  pdl       : "#81d4fa",
  swingHigh : "#ef5350",
  swingLow  : "#26a69a",
};

function isoToUnix(iso) {
  return Math.floor(new Date(iso).getTime() / 1000);
}

export default function CandleChart({
  ticker, candles, indicators, structure, pdh, pdl, settings, showLine,
}) {
  const containerRef = useRef(null);
  const chartRef     = useRef(null);
  const seriesRef    = useRef({});
  const infoRef      = useRef(null);

  // ── destroy on unmount ───────────────────────────────────────────────────
  useEffect(() => {
    return () => { if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; } };
  }, []);

  // ── build / rebuild chart when candles change ────────────────────────────
  useEffect(() => {
    if (!containerRef.current || !candles?.length) return;

    // Remove old chart
    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
    seriesRef.current = {};

    const chart = createChart(containerRef.current, {
      layout: { background: { color: "#141414" }, textColor: "#aaaaaa" },
      grid  : {
        vertLines: { color: "rgba(255,255,255,0.05)" },
        horzLines: { color: "rgba(255,255,255,0.05)" },
      },
      crosshair       : { mode: 1 },
      timeScale       : { timeVisible: true, secondsVisible: false, borderColor: "#333333" },
      rightPriceScale : { borderColor: "#333333" },
      width           : containerRef.current.clientWidth,
      height          : 480,
    });
    chartRef.current = chart;

    // ── resize ────────────────────────────────────────────────────────────
    const ro = new ResizeObserver(entries => {
      if (chartRef.current) {
        chartRef.current.applyOptions({ width: entries[0].contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    const priceData = candles.map(c => ({
      time: isoToUnix(c.t), open: c.o, high: c.h, low: c.l, close: c.c,
    }));

    // ── main price series ─────────────────────────────────────────────────
    if (showLine) {
      const ls = chart.addLineSeries({ color: COLORS.bull, lineWidth: 2 });
      ls.setData(priceData.map(d => ({ time: d.time, value: d.close })));
      seriesRef.current.price = ls;
    } else {
      const cs = chart.addCandlestickSeries({
        upColor         : COLORS.bull, downColor         : COLORS.bear,
        borderUpColor   : COLORS.bull, borderDownColor   : COLORS.bear,
        wickUpColor     : COLORS.bull, wickDownColor     : COLORS.bear,
      });
      cs.setData(priceData);
      seriesRef.current.price = cs;
    }

    // ── volume histogram ──────────────────────────────────────────────────
    if (indicators?.volume?.length) {
      const volSeries = chart.addHistogramSeries({
        priceFormat  : { type: "volume" },
        priceScaleId : "vol",
      });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      volSeries.setData(
        indicators.volume.map((d, i) => {
          const c = candles[i];
          const color = c && c.c >= c.o
            ? "rgba(38,166,154,0.5)"
            : "rgba(239,83,80,0.5)";
          return { time: isoToUnix(d.t), value: d.v, color };
        })
      );
      seriesRef.current.volume = volSeries;
    }

    // ── crosshair info bar ────────────────────────────────────────────────
    chart.subscribeCrosshairMove(param => {
      if (!infoRef.current) return;
      if (!param.time || !param.seriesData) { infoRef.current.innerHTML = ""; return; }
      const d = param.seriesData.get(seriesRef.current.price);
      if (!d) return;
      const close = d.close ?? d.value;
      const open  = d.open  ?? d.value;
      const delta = close !== undefined ? (close - open) : 0;
      const clr   = delta >= 0 ? "#26a69a" : "#ef5350";
      infoRef.current.innerHTML =
        `<span style="color:#aaa">${ticker}</span>&nbsp; ` +
        `O <b>${(d.open ?? d.value)?.toFixed(2)}</b>&nbsp; ` +
        (d.high  != null ? `H <b>${d.high.toFixed(2)}</b>&nbsp; `  : "") +
        (d.low   != null ? `L <b>${d.low.toFixed(2)}</b>&nbsp; `   : "") +
        `C <b>${close?.toFixed(2)}</b>&nbsp; ` +
        `<span style="color:${clr}">${delta >= 0 ? "▲" : "▼"} <b>${Math.abs(delta).toFixed(2)}</b></span>`;
    });

    chart.timeScale().fitContent();
    return () => ro.disconnect();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candles, showLine, ticker]);

  // ── EMA / VWAP overlays ───────────────────────────────────────────────────
  useEffect(() => {
    removeOverlay(chartRef, seriesRef, "ema9");
    removeOverlay(chartRef, seriesRef, "ema21");
    if (!settings?.showEma || !chartRef.current) return;
    if (indicators?.ema9?.length) {
      const s = chartRef.current.addLineSeries({ color: COLORS.ema9,  lineWidth: 1 });
      s.setData(indicators.ema9.map(d => ({ time: isoToUnix(d.t), value: d.v })));
      seriesRef.current.ema9 = s;
    }
    if (indicators?.ema21?.length) {
      const s = chartRef.current.addLineSeries({ color: COLORS.ema21, lineWidth: 1 });
      s.setData(indicators.ema21.map(d => ({ time: isoToUnix(d.t), value: d.v })));
      seriesRef.current.ema21 = s;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings?.showEma, indicators?.ema9, indicators?.ema21]);

  useEffect(() => {
    removeOverlay(chartRef, seriesRef, "vwap");
    if (!settings?.showVwap || !chartRef.current || !indicators?.vwap?.length) return;
    const s = chartRef.current.addLineSeries({ color: COLORS.vwap, lineWidth: 1, lineStyle: 2 });
    s.setData(indicators.vwap.map(d => ({ time: isoToUnix(d.t), value: d.v })));
    seriesRef.current.vwap = s;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings?.showVwap, indicators?.vwap]);

  // ── PDH / PDL price lines ─────────────────────────────────────────────────
  useEffect(() => {
    const price = seriesRef.current.price;
    if (!price) return;
    const lines = [];
    if (settings?.showPdhPdl && pdh) {
      lines.push(price.createPriceLine({
        price: pdh, color: COLORS.pdh, lineWidth: 1, lineStyle: 2,
        axisLabelVisible: true, title: `PDH ${pdh.toFixed(2)}`,
      }));
    }
    if (settings?.showPdhPdl && pdl) {
      lines.push(price.createPriceLine({
        price: pdl, color: COLORS.pdl, lineWidth: 1, lineStyle: 2,
        axisLabelVisible: true, title: `PDL ${pdl.toFixed(2)}`,
      }));
    }
    return () => lines.forEach(l => { try { price.removePriceLine(l); } catch (_) {} });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdh, pdl, settings?.showPdhPdl, candles]);

  // ── Swing markers ─────────────────────────────────────────────────────────
  useEffect(() => {
    const price = seriesRef.current.price;
    if (!price || !candles?.length) return;
    if (!settings?.showSwings) { try { price.setMarkers([]); } catch (_) {} return; }
    const markers = [];
    structure?.swing_highs?.forEach(s => markers.push({
      time: isoToUnix(s.t), position: "aboveBar",
      color: COLORS.swingHigh, shape: "arrowDown",
      text: `${s.price.toFixed(1)}`, size: 1,
    }));
    structure?.swing_lows?.forEach(s => markers.push({
      time: isoToUnix(s.t), position: "belowBar",
      color: COLORS.swingLow, shape: "arrowUp",
      text: `${s.price.toFixed(1)}`, size: 1,
    }));
    markers.sort((a, b) => a.time - b.time);
    try { price.setMarkers(markers); } catch (_) {}
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structure?.swing_highs, structure?.swing_lows, settings?.showSwings, candles]);

  return (
    <div style={{ position: "relative" }}>
      <div
        ref={infoRef}
        style={{
          position: "absolute", top: 6, left: 8, zIndex: 10,
          fontSize: 12, color: "#e0e0e0", pointerEvents: "none",
          background: "rgba(20,20,20,0.75)", padding: "2px 8px", borderRadius: 4,
        }}
      />
      <div ref={containerRef} style={{ width: "100%" }} />
    </div>
  );
}

function removeOverlay(chartRef, seriesRef, key) {
  if (seriesRef.current[key]) {
    try { chartRef.current?.removeSeries(seriesRef.current[key]); } catch (_) {}
    seriesRef.current[key] = null;
  }
}
