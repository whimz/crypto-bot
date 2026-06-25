import { useCallback, useEffect, useRef, useState } from "react";
import { CandlestickSeries, ColorType, LineSeries, createChart } from "lightweight-charts";
import { getChart } from "../api.js";
import { showToast } from "../toastBus.js";

const SYMBOLS = [
  { value: "BTCUSDT", label: "BTC" },
  { value: "ETHUSDT", label: "ETH" },
  { value: "LTCUSDT", label: "LTC" },
];
const INTERVALS = ["15m", "1h", "4h"];
const POLL_INTERVAL_MS = 30_000;
const SWITCH_DEBOUNCE_MS = 500;

function themeColor(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function readThemeColors() {
  return {
    textColor: themeColor("--text", "#e6edf3"),
    gridColor: themeColor("--border", "#2a313c"),
    upColor: themeColor("--green", "#3fb950"),
    downColor: themeColor("--red", "#f85149"),
    accentColor: themeColor("--accent", "#58a6ff"),
  };
}

export default function Chart() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setIntervalValue] = useState("15m");

  const mainContainerRef = useRef(null);
  const rsiContainerRef = useRef(null);
  const mainChartRef = useRef(null);
  const rsiChartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const rsiSeriesRef = useRef(null);

  useEffect(() => {
    const { textColor, gridColor, upColor, downColor, accentColor } = readThemeColors();

    const chartOptions = {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      timeScale: { timeVisible: true, borderColor: gridColor },
      rightPriceScale: { borderColor: gridColor },
    };

    const mainChart = createChart(mainContainerRef.current, chartOptions);
    const candleSeries = mainChart.addSeries(CandlestickSeries, {
      upColor,
      downColor,
      borderVisible: false,
      wickUpColor: upColor,
      wickDownColor: downColor,
    });

    const rsiChart = createChart(rsiContainerRef.current, chartOptions);
    const rsiSeries = rsiChart.addSeries(LineSeries, { color: accentColor, lineWidth: 2 });

    // Keep the two time scales (price + RSI) panning/zooming together.
    const syncFromMain = (range) => range && rsiChart.timeScale().setVisibleLogicalRange(range);
    const syncFromRsi = (range) => range && mainChart.timeScale().setVisibleLogicalRange(range);
    mainChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromMain);
    rsiChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromRsi);

    mainChartRef.current = mainChart;
    rsiChartRef.current = rsiChart;
    candleSeriesRef.current = candleSeries;
    rsiSeriesRef.current = rsiSeries;

    return () => {
      mainChart.remove();
      rsiChart.remove();
    };
  }, []);

  // App.jsx toggles data-theme on <html> without remounting this component, so re-apply
  // colors on every theme flip instead of only reading them once at chart creation.
  useEffect(() => {
    const repaint = () => {
      const { textColor, gridColor, upColor, downColor, accentColor } = readThemeColors();
      const chartOptions = {
        layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor },
        grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
        timeScale: { borderColor: gridColor },
        rightPriceScale: { borderColor: gridColor },
      };
      mainChartRef.current?.applyOptions(chartOptions);
      rsiChartRef.current?.applyOptions(chartOptions);
      candleSeriesRef.current?.applyOptions({
        upColor,
        downColor,
        wickUpColor: upColor,
        wickDownColor: downColor,
      });
      rsiSeriesRef.current?.applyOptions({ color: accentColor });
    };

    const observer = new MutationObserver(repaint);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  const refresh = useCallback(async () => {
    try {
      const data = await getChart(symbol, interval, 100);
      candleSeriesRef.current?.setData(data.candles);
      rsiSeriesRef.current?.setData(data.rsi);
    } catch (err) {
      showToast({
        title: "Failed to load chart data",
        description: err.message,
        requestId: err.requestId,
        retry: refresh,
      });
    }
  }, [symbol, interval]);

  // Debounce so rapidly clicking through symbols/intervals doesn't fire a Binance
  // request per click.
  useEffect(() => {
    const timeoutId = setTimeout(refresh, SWITCH_DEBOUNCE_MS);
    return () => clearTimeout(timeoutId);
  }, [refresh]);

  useEffect(() => {
    const intervalId = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, [refresh]);

  return (
    <div className="card">
      <h2>Price Chart</h2>
      <div className="chart-controls">
        <div className="chart-toggle-group">
          {SYMBOLS.map((s) => (
            <button
              key={s.value}
              className={symbol === s.value ? "active" : ""}
              onClick={() => setSymbol(s.value)}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="chart-toggle-group">
          {INTERVALS.map((i) => (
            <button
              key={i}
              className={interval === i ? "active" : ""}
              onClick={() => setIntervalValue(i)}
            >
              {i}
            </button>
          ))}
        </div>
      </div>
      <div ref={mainContainerRef} className="chart-main" />
      <div className="chart-rsi-label">RSI(14)</div>
      <div ref={rsiContainerRef} className="chart-rsi" />
    </div>
  );
}
