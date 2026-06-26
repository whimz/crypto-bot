import { useCallback, useEffect, useRef, useState } from "react";
import { ColorType, LineSeries, createChart } from "lightweight-charts";
import { getPortfolioHistory } from "../api.js";
import { showToast } from "../toastBus.js";

const PERIODS = [
  { value: 1, label: "1д" },
  { value: 7, label: "7д" },
  { value: 30, label: "30д" },
];
const POLL_INTERVAL_MS = 30_000;

function themeColor(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export default function DepositChart() {
  const [days, setDays] = useState(7);
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);

  useEffect(() => {
    const textColor = themeColor("--text", "#e6edf3");
    const gridColor = themeColor("--border", "#2a313c");
    const accentColor = themeColor("--accent", "#58a6ff");

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      timeScale: { timeVisible: true, borderColor: gridColor },
      rightPriceScale: { borderColor: gridColor },
    });
    const series = chart.addSeries(LineSeries, { color: accentColor, lineWidth: 2 });

    chartRef.current = chart;
    seriesRef.current = series;

    return () => chart.remove();
  }, []);

  useEffect(() => {
    const repaint = () => {
      const textColor = themeColor("--text", "#e6edf3");
      const gridColor = themeColor("--border", "#2a313c");
      const accentColor = themeColor("--accent", "#58a6ff");
      chartRef.current?.applyOptions({
        layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor },
        grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
        timeScale: { borderColor: gridColor },
        rightPriceScale: { borderColor: gridColor },
      });
      seriesRef.current?.applyOptions({ color: accentColor });
    };

    const observer = new MutationObserver(repaint);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  const refresh = useCallback(async () => {
    try {
      const data = await getPortfolioHistory(days);
      const points = data.map((row) => ({
        time: Math.floor(new Date(row.timestamp).getTime() / 1000),
        value: row.deposit_usdt,
      }));
      seriesRef.current?.setData(points);
    } catch (err) {
      showToast({
        title: "Failed to load deposit history",
        description: err.message,
        requestId: err.requestId,
        retry: refresh,
      });
    }
  }, [days]);

  useEffect(() => {
    refresh();
    const intervalId = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, [refresh]);

  return (
    <div className="card">
      <h2>Deposit History</h2>
      <div className="chart-controls">
        <div className="chart-toggle-group">
          {PERIODS.map((p) => (
            <button key={p.value} className={days === p.value ? "active" : ""} onClick={() => setDays(p.value)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="chart-main" />
    </div>
  );
}
