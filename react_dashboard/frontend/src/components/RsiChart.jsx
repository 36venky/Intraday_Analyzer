import { useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";

function isoToUnix(iso) {
  return Math.floor(new Date(iso).getTime() / 1000);
}

export default function RsiChart({ rsiData }) {
  const containerRef = useRef(null);
  const chartRef     = useRef(null);

  useEffect(() => () => { if (chartRef.current) chartRef.current.remove(); }, []);

  useEffect(() => {
    if (!containerRef.current || !rsiData?.length) return;
    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }

    const chart = createChart(containerRef.current, {
      layout     : { background: { color: "#141414" }, textColor: "#aaaaaa" },
      grid       : { vertLines: { color: "rgba(255,255,255,0.04)" }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      timeScale  : { timeVisible: true, secondsVisible: false, borderColor: "#333" },
      rightPriceScale: { borderColor: "#333" },
      width      : containerRef.current.clientWidth,
      height     : 130,
      crosshair  : { mode: 1 },
    });
    chartRef.current = chart;

    const ro = new ResizeObserver(e => { if (chartRef.current) chartRef.current.applyOptions({ width: e[0].contentRect.width }); });
    ro.observe(containerRef.current);

    const rsiSeries = chart.addLineSeries({ color: "#64b5f6", lineWidth: 1 });
    rsiSeries.setData(rsiData.map(d => ({ time: isoToUnix(d.t), value: d.v })));

    // OB/OS reference lines
    rsiSeries.createPriceLine({ price: 70, color: "#ef535080", lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "70" });
    rsiSeries.createPriceLine({ price: 30, color: "#26a69a80", lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "30" });

    chart.timeScale().fitContent();
    return () => ro.disconnect();
  }, [rsiData]);

  return <div ref={containerRef} style={{ width: "100%" }} />;
}
