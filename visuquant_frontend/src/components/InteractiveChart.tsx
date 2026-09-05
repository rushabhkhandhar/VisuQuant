"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useTheme } from "./ThemeContext";
import {
  IconActivity,
  IconMaximize,
  IconMinimize,
  IconSearch,
  IconRefresh,
  IconExternalLink,
} from "./Icons";
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  AreaSeries,
  IChartApi,
  ISeriesApi,
} from "lightweight-charts";

interface InteractiveChartProps {
  initialSymbol?: string;
  initialInterval?: string;
  height?: number;
  showQuickSwitcher?: boolean;
  showControls?: boolean;
  title?: string;
  subtitle?: string;
}

interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface ChartPayload {
  status: string;
  symbol: string;
  candles: CandleData[];
  volume: { time: string; value: number; color?: string }[];
  avwap: { time: string; value: number }[];
  ema20: { time: string; value: number }[];
  ema50: { time: string; value: number }[];
  message?: string;
}

export default function InteractiveChart({
  initialSymbol = "NIFTY",
  height = 520,
  showQuickSwitcher = true,
  showControls = true,
  title = "Live Market Terminal & Candlestick Forensics",
  subtitle = "High-performance institutional canvas engine featuring real-time OHLCV, Dual Anchored VWAP, and volume dynamics.",
}: InteractiveChartProps) {
  const { theme } = useTheme();

  const sanitize = (s: string) =>
    s.replace("NSE:", "").replace("BSE:", "").replace(".NS", "").replace(".BO", "").trim().toUpperCase();

  const [symbol, setSymbol] = useState<string>(sanitize(initialSymbol));
  const [period, setPeriod] = useState<string>("6mo");
  const [chartType, setChartType] = useState<"candles" | "area">("candles");
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [customInput, setCustomInput] = useState<string>("");
  const [chartLoading, setChartLoading] = useState<boolean>(false);
  const [chartError, setChartError] = useState<string | null>(null);

  // Autocomplete Suggestions
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState<boolean>(false);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  // Indicator Toggles
  const [showAvwap, setShowAvwap] = useState<boolean>(true);
  const [showEma20, setShowEma20] = useState<boolean>(true);
  const [showEma50, setShowEma50] = useState<boolean>(true);
  const [showVolume, setShowVolume] = useState<boolean>(true);

  // Live Metrics & Crosshair HUD
  const [latestMetrics, setLatestMetrics] = useState<{
    ltp: number;
    open: number;
    high: number;
    low: number;
    change: number;
    pct: number;
    volume: number;
  }>({
    ltp: 0,
    open: 0,
    high: 0,
    low: 0,
    change: 0,
    pct: 0,
    volume: 0,
  });

  const [hoveredData, setHoveredData] = useState<{
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
    avwap?: number;
  } | null>(null);

  // Chart References & Lifecycle Guards
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const isDisposedRef = useRef<boolean>(false);
  const currentPayloadRef = useRef<ChartPayload | null>(null);

  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const areaSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const avwapSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema20SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const POPULAR_TICKERS = [
    { label: "NIFTY 50", sym: "NIFTY" },
    { label: "BANK NIFTY", sym: "BANKNIFTY" },
    { label: "TCS", sym: "TCS" },
    { label: "INFY", sym: "INFY" },
    { label: "RELIANCE", sym: "RELIANCE" },
    { label: "TATASTEEL", sym: "TATASTEEL" },
    { label: "DIXON", sym: "DIXON" },
    { label: "MTARTECH", sym: "MTARTECH" },
    { label: "HDFCBANK", sym: "HDFCBANK" },
  ];

  // Helper to populate series data safely
  const applyPayloadToChart = useCallback((payload: ChartPayload) => {
    if (isDisposedRef.current || !chartRef.current) return;
    const cSeries = candleSeriesRef.current;
    const aSeries = areaSeriesRef.current;
    const vSeries = volumeSeriesRef.current;
    const avSeries = avwapSeriesRef.current;
    const e20Series = ema20SeriesRef.current;
    const e50Series = ema50SeriesRef.current;

    if (!cSeries) return;

    try {
      if (payload.status === "success" && payload.candles && payload.candles.length > 0) {
        setChartError(null);
        cSeries.setData(payload.candles);

        if (aSeries) {
          const areaData = payload.candles.map((c: CandleData) => ({ time: c.time, value: c.close }));
          aSeries.setData(areaData);
        }

        if (vSeries && payload.volume) vSeries.setData(payload.volume);
        if (avSeries && payload.avwap) avSeries.setData(payload.avwap);
        if (e20Series && payload.ema20) e20Series.setData(payload.ema20);
        if (e50Series && payload.ema50) e50Series.setData(payload.ema50);

        chartRef.current.timeScale().fitContent();

        const lastCandle = payload.candles[payload.candles.length - 1];
        const prevCandle = payload.candles[payload.candles.length - 2] || lastCandle;
        const ltp = lastCandle.close;
        const open = lastCandle.open;
        const high = lastCandle.high;
        const low = lastCandle.low;
        const change = ltp - prevCandle.close;
        const pct = prevCandle.close > 0 ? (change / prevCandle.close) * 100 : 0;
        const lastVol = payload.volume && payload.volume.length > 0 ? payload.volume[payload.volume.length - 1].value : 0;

        setLatestMetrics({
          ltp,
          open,
          high,
          low,
          change,
          pct,
          volume: lastVol,
        });
      } else {
        handleError(payload.message || `No market candle data found for "${symbol}".`);
      }
    } catch {
      // Prevent crash if instance was concurrently closed
    }
  }, [symbol]);

  const handleError = (msg: string) => {
    setChartError(msg);
    if (isDisposedRef.current) return;
    try {
      candleSeriesRef.current?.setData([]);
      areaSeriesRef.current?.setData([]);
      volumeSeriesRef.current?.setData([]);
      avwapSeriesRef.current?.setData([]);
      ema20SeriesRef.current?.setData([]);
      ema50SeriesRef.current?.setData([]);
    } catch {
      // Ignore cleanup on disposed series
    }
    setLatestMetrics({ ltp: 0, open: 0, high: 0, low: 0, change: 0, pct: 0, volume: 0 });
    setHoveredData(null);
  };

  // Sync initialSymbol if parent updates it
  useEffect(() => {
    if (initialSymbol) {
      setSymbol(sanitize(initialSymbol));
    }
  }, [initialSymbol]);

  // Click outside listener for search autocomplete dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Fetch search suggestions as user types
  useEffect(() => {
    if (!customInput.trim()) {
      setSuggestions([]);
      return;
    }
    const timer = setTimeout(() => {
      fetch(`http://localhost:5000/api/search_symbols?q=${encodeURIComponent(customInput.trim())}`)
        .then((res) => res.json())
        .then((data) => {
          if (data.symbols) {
            setSuggestions(data.symbols);
          }
        })
        .catch(() => {
          setSuggestions([]);
        });
    }, 150);
    return () => clearTimeout(timer);
  }, [customInput]);

  // 1. Chart Initialization (MOUNT ONCE ONLY)
  useEffect(() => {
    if (!containerRef.current) return;

    isDisposedRef.current = false;
    const isDark = theme === "dark";
    const container = containerRef.current;
    container.innerHTML = "";

    const chart = createChart(container, {
      width: container.clientWidth || 800,
      height: isFullscreen ? window.innerHeight - 150 : height,
      layout: {
        background: {
          type: ColorType.Solid,
          color: isDark ? "#090d16" : "#ffffff",
        },
        textColor: isDark ? "#94a3b8" : "#475569",
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: isDark ? "rgba(255, 255, 255, 0.04)" : "rgba(0, 0, 0, 0.05)" },
        horzLines: { color: isDark ? "rgba(255, 255, 255, 0.04)" : "rgba(0, 0, 0, 0.05)" },
      },
      timeScale: {
        borderColor: isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.1)",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.1)",
        scaleMargins: {
          top: 0.1,
          bottom: 0.22,
        },
      },
      crosshair: {
        mode: 1,
      },
    });

    chartRef.current = chart;

    // Series Setup
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: isDark ? "#00ff88" : "#16a34a",
      downColor: isDark ? "#ff3366" : "#dc2626",
      borderVisible: false,
      wickUpColor: isDark ? "#00ff88" : "#16a34a",
      wickDownColor: isDark ? "#ff3366" : "#dc2626",
      visible: chartType === "candles",
    });
    candleSeriesRef.current = candleSeries;

    const areaSeries = chart.addSeries(AreaSeries, {
      topColor: isDark ? "rgba(0, 240, 255, 0.4)" : "rgba(6, 182, 212, 0.3)",
      bottomColor: isDark ? "rgba(0, 240, 255, 0.0)" : "rgba(6, 182, 212, 0.0)",
      lineColor: isDark ? "#00f0ff" : "#0284c7",
      lineWidth: 2,
      visible: chartType === "area",
    });
    areaSeriesRef.current = areaSeries;

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      visible: showVolume,
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeriesRef.current = volumeSeries;

    const avwapSeries = chart.addSeries(LineSeries, {
      color: "#00f0ff",
      lineWidth: 2,
      title: "Anchored VWAP",
      visible: showAvwap,
    });
    avwapSeriesRef.current = avwapSeries;

    const ema20Series = chart.addSeries(LineSeries, {
      color: "#c084fc",
      lineWidth: 1,
      title: "20 EMA",
      visible: showEma20,
    });
    ema20SeriesRef.current = ema20Series;

    const ema50Series = chart.addSeries(LineSeries, {
      color: "#f59e0b",
      lineWidth: 1,
      title: "50 EMA",
      visible: showEma50,
    });
    ema50SeriesRef.current = ema50Series;

    // Crosshair hover subscriber
    chart.subscribeCrosshairMove((param) => {
      if (isDisposedRef.current) return;
      if (
        !param.point ||
        !param.time ||
        param.point.x < 0 ||
        param.point.x > container.clientWidth ||
        param.point.y < 0 ||
        param.point.y > container.clientHeight
      ) {
        setHoveredData(null);
      } else {
        try {
          const cData = param.seriesData.get(candleSeries) as any;
          const vData = param.seriesData.get(volumeSeries) as any;
          const avData = param.seriesData.get(avwapSeries) as any;

          if (cData) {
            setHoveredData({
              time: String(param.time),
              open: cData.open ?? cData.value ?? 0,
              high: cData.high ?? cData.value ?? 0,
              low: cData.low ?? cData.value ?? 0,
              close: cData.close ?? cData.value ?? 0,
              volume: vData ? vData.value : undefined,
              avwap: avData ? avData.value : undefined,
            });
          }
        } catch {
          // Ignore
        }
      }
    });

    // If data arrived before canvas mounted, render it now!
    if (currentPayloadRef.current) {
      applyPayloadToChart(currentPayloadRef.current);
    }

    // ResizeObserver for continuous responsive layout
    const ro = new ResizeObserver(() => {
      if (!isDisposedRef.current && chartRef.current && containerRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: isFullscreen ? window.innerHeight - 150 : height,
        });
      }
    });
    ro.observe(container);

    return () => {
      isDisposedRef.current = true;
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      areaSeriesRef.current = null;
      volumeSeriesRef.current = null;
      avwapSeriesRef.current = null;
      ema20SeriesRef.current = null;
      ema50SeriesRef.current = null;
    };
  }, []); // Run ONCE on mount

  // 2. Dynamic Theme Updates (Never Recreates Chart)
  useEffect(() => {
    if (isDisposedRef.current || !chartRef.current) return;
    const isDark = theme === "dark";
    try {
      chartRef.current.applyOptions({
        layout: {
          background: { type: ColorType.Solid, color: isDark ? "#090d16" : "#ffffff" },
          textColor: isDark ? "#94a3b8" : "#475569",
        },
        grid: {
          vertLines: { color: isDark ? "rgba(255, 255, 255, 0.04)" : "rgba(0, 0, 0, 0.05)" },
          horzLines: { color: isDark ? "rgba(255, 255, 255, 0.04)" : "rgba(0, 0, 0, 0.05)" },
        },
      });
      candleSeriesRef.current?.applyOptions({
        upColor: isDark ? "#00ff88" : "#16a34a",
        downColor: isDark ? "#ff3366" : "#dc2626",
        wickUpColor: isDark ? "#00ff88" : "#16a34a",
        wickDownColor: isDark ? "#ff3366" : "#dc2626",
      });
      areaSeriesRef.current?.applyOptions({
        topColor: isDark ? "rgba(0, 240, 255, 0.4)" : "rgba(6, 182, 212, 0.3)",
        bottomColor: isDark ? "rgba(0, 240, 255, 0.0)" : "rgba(6, 182, 212, 0.0)",
        lineColor: isDark ? "#00f0ff" : "#0284c7",
      });
    } catch {
      // Ignore
    }
  }, [theme]);

  // 3. Smooth Fullscreen / Height Expansion (Never Disposes Chart)
  useEffect(() => {
    if (isDisposedRef.current || !chartRef.current || !containerRef.current) return;
    const targetHeight = isFullscreen ? window.innerHeight - 160 : height;

    const timer = setTimeout(() => {
      if (!isDisposedRef.current && chartRef.current && containerRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: targetHeight,
        });
        chartRef.current.timeScale().fitContent();
      }
    }, 50);

    return () => clearTimeout(timer);
  }, [isFullscreen, height]);

  // 4. Dynamic Visibility Toggles
  useEffect(() => {
    if (!isDisposedRef.current) {
      candleSeriesRef.current?.applyOptions({ visible: chartType === "candles" });
      areaSeriesRef.current?.applyOptions({ visible: chartType === "area" });
    }
  }, [chartType]);

  useEffect(() => {
    if (!isDisposedRef.current) volumeSeriesRef.current?.applyOptions({ visible: showVolume });
  }, [showVolume]);

  useEffect(() => {
    if (!isDisposedRef.current) avwapSeriesRef.current?.applyOptions({ visible: showAvwap });
  }, [showAvwap]);

  useEffect(() => {
    if (!isDisposedRef.current) ema20SeriesRef.current?.applyOptions({ visible: showEma20 });
  }, [showEma20]);

  useEffect(() => {
    if (!isDisposedRef.current) ema50SeriesRef.current?.applyOptions({ visible: showEma50 });
  }, [showEma50]);

  // 5. Guaranteed Real Candle Data Fetch (Always Runs on Mount & Symbol/Period Change)
  useEffect(() => {
    let active = true;
    setChartLoading(true);
    setChartError(null);

    fetch(`http://localhost:5000/api/chart_data?symbol=${encodeURIComponent(symbol)}&period=${period}`)
      .then((res) => res.json())
      .then((data: ChartPayload) => {
        if (!active) return;
        currentPayloadRef.current = data;
        applyPayloadToChart(data);
      })
      .catch(() => {
        if (!active) return;
        handleError(`Failed to connect to market data engine for "${symbol}".`);
      })
      .finally(() => {
        if (active) setChartLoading(false);
      });

    return () => {
      active = false;
    };
  }, [symbol, period, applyPayloadToChart]);

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (customInput.trim()) {
      setSymbol(sanitize(customInput));
      setShowSuggestions(false);
    }
  };

  const selectSuggestion = (sym: string) => {
    setSymbol(sym);
    setCustomInput("");
    setShowSuggestions(false);
  };

  const activeData = hoveredData || {
    time: "Latest Session",
    open: latestMetrics.open,
    high: latestMetrics.high,
    low: latestMetrics.low,
    close: latestMetrics.ltp,
    volume: latestMetrics.volume,
    avwap: undefined,
  };

  const isBullish = latestMetrics.change >= 0;

  return (
    <div
      className={isFullscreen ? "" : "glass-panel"}
      style={{
        width: "100%",
        display: "flex",
        flexDirection: "column",
        overflow: "visible",
        position: isFullscreen ? "fixed" : "relative",
        top: isFullscreen ? 0 : "auto",
        left: isFullscreen ? 0 : "auto",
        right: isFullscreen ? 0 : "auto",
        bottom: isFullscreen ? 0 : "auto",
        zIndex: isFullscreen ? 9999 : 1,
        background: isFullscreen ? "var(--bg-darkest)" : "var(--bg-card)",
        padding: isFullscreen ? "20px" : "24px 28px",
        borderRadius: isFullscreen ? 0 : "var(--radius-lg)",
        boxShadow: isFullscreen ? "none" : "var(--card-shadow)",
        transition: "background 0.2s ease",
      }}
    >
      {/* 1. Terminal Header & Live Pricing HUD */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
          marginBottom: "16px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <span style={{ fontSize: "18px", fontWeight: 800, letterSpacing: "-0.01em" }}>{title}</span>
            <span
              className={`badge ${chartError ? "badge-bearish" : "badge-cyan"} font-mono`}
              style={{ fontSize: "13px", padding: "3px 10px" }}
            >
              {symbol}
            </span>
            {latestMetrics.ltp > 0 && (
              <span className="font-mono" style={{ fontSize: "15px", fontWeight: 700 }}>
                ₹{latestMetrics.ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                <span
                  style={{
                    color: isBullish ? "var(--emerald)" : "var(--crimson)",
                    marginLeft: "8px",
                    fontSize: "13px",
                  }}
                >
                  {isBullish ? "+" : ""}
                  {latestMetrics.change.toFixed(2)} ({isBullish ? "+" : ""}
                  {latestMetrics.pct.toFixed(2)}%)
                </span>
              </span>
            )}
            {!chartError && (
              <span className="badge badge-bullish" style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
                <IconActivity size={12} color="var(--emerald)" />
                <span>AUTHENTIC TICKS</span>
              </span>
            )}
            {chartError && (
              <span className="badge badge-bearish" style={{ fontSize: "11px" }}>
                INVALID TICKER
              </span>
            )}
          </div>
          <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
            {subtitle}
          </div>
        </div>

        {showControls && (
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            {/* Period Switcher */}
            <div
              style={{
                display: "inline-flex",
                background: "var(--bg-surface-elevated)",
                padding: "3px",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle)",
              }}
            >
              {[
                { label: "1M", val: "1mo" },
                { label: "3M", val: "3mo" },
                { label: "6M", val: "6mo" },
                { label: "1Y", val: "1y" },
              ].map((p) => (
                <button
                  key={p.val}
                  onClick={() => setPeriod(p.val)}
                  style={{
                    background: period === p.val ? "var(--cyan)" : "transparent",
                    color: period === p.val ? "#05070b" : "var(--text-secondary)",
                    border: "none",
                    padding: "4px 10px",
                    borderRadius: "6px",
                    fontSize: "11px",
                    fontWeight: 700,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {/* Chart Type Toggle */}
            <div
              style={{
                display: "inline-flex",
                background: "var(--bg-surface-elevated)",
                padding: "3px",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <button
                onClick={() => setChartType("candles")}
                style={{
                  background: chartType === "candles" ? "var(--border-glass)" : "transparent",
                  color: chartType === "candles" ? "var(--text-primary)" : "var(--text-muted)",
                  border: "none",
                  padding: "4px 10px",
                  borderRadius: "6px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Candles
              </button>
              <button
                onClick={() => setChartType("area")}
                style={{
                  background: chartType === "area" ? "var(--border-glass)" : "transparent",
                  color: chartType === "area" ? "var(--text-primary)" : "var(--text-muted)",
                  border: "none",
                  padding: "4px 10px",
                  borderRadius: "6px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Area
              </button>
            </div>

            {/* Open in TradingView External Web Link */}
            <a
              href={`https://www.tradingview.com/chart/?symbol=NSE:${symbol}`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-glass"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "5px",
                padding: "5px 10px",
                borderRadius: "8px",
                fontSize: "11px",
                textDecoration: "none",
              }}
              title="Open full chart on TradingView"
            >
              <span>TradingView Web</span>
              <IconExternalLink size={12} />
            </a>

            {/* Fullscreen Expansion Toggle (Smooth Resize, Zero Disposed Error) */}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="btn-glass"
              style={{ padding: "6px 10px", borderRadius: "8px", cursor: "pointer" }}
              title={isFullscreen ? "Exit Fullscreen" : "Fullscreen Chart"}
            >
              {isFullscreen ? <IconMinimize size={14} /> : <IconMaximize size={14} />}
            </button>
          </div>
        )}
      </div>

      {/* 2. Interactive OHLCV Heads-Up Display (HUD) */}
      {!chartError && (
        <div
          className="font-mono"
          style={{
            display: "flex",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "14px",
            background: "var(--bg-surface-elevated)",
            padding: "8px 14px",
            borderRadius: "8px",
            marginBottom: "14px",
            border: "1px solid var(--border-subtle)",
            fontSize: "11px",
            color: "var(--text-secondary)",
          }}
        >
          <span style={{ color: "var(--text-muted)", fontWeight: 600 }}>
            {hoveredData ? `Bar: ${hoveredData.time}` : `Latest Session`}
          </span>
          <span>
            O: <strong style={{ color: "var(--text-primary)" }}>₹{activeData.open.toFixed(2)}</strong>
          </span>
          <span>
            H: <strong style={{ color: "var(--emerald)" }}>₹{activeData.high.toFixed(2)}</strong>
          </span>
          <span>
            L: <strong style={{ color: "var(--crimson)" }}>₹{activeData.low.toFixed(2)}</strong>
          </span>
          <span>
            C: <strong style={{ color: "var(--cyan)" }}>₹{activeData.close.toFixed(2)}</strong>
          </span>
          {activeData.volume !== undefined && activeData.volume > 0 && (
            <span>
              Vol: <strong style={{ color: "var(--text-primary)" }}>{(activeData.volume / 1000).toFixed(1)}k</strong>
            </span>
          )}
          {showAvwap && activeData.avwap !== undefined && (
            <span>
              AVWAP: <strong style={{ color: "var(--cyan)" }}>₹{activeData.avwap.toFixed(2)}</strong>
            </span>
          )}
        </div>
      )}

      {/* 3. Quick Symbol Switcher & Autocomplete Search Bar */}
      {showQuickSwitcher && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "12px",
            marginBottom: "14px",
            paddingBottom: "12px",
            borderBottom: "1px solid var(--border-subtle)",
            position: "relative",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
            <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>Tickers:</span>
            {POPULAR_TICKERS.map((t) => {
              const isSelected = symbol === t.sym && !chartError;
              return (
                <button
                  key={t.sym}
                  onClick={() => {
                    setSymbol(t.sym);
                    setCustomInput("");
                    setShowSuggestions(false);
                  }}
                  className={`btn ${isSelected ? "btn-cyan" : "btn-glass"}`}
                  style={{
                    padding: "4px 9px",
                    fontSize: "11px",
                    fontFamily: "'JetBrains Mono', monospace",
                    borderRadius: "6px",
                  }}
                >
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* Autocomplete Search Form with Dropdown */}
          <div ref={searchContainerRef} style={{ position: "relative" }}>
            <form onSubmit={handleCustomSubmit} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <input
                type="text"
                placeholder="Search NSE Ticker (e.g. TATA)"
                value={customInput}
                onChange={(e) => {
                  setCustomInput(e.target.value.toUpperCase());
                  setShowSuggestions(true);
                }}
                onFocus={() => setShowSuggestions(true)}
                className="quant-input font-mono"
                style={{ width: "220px", padding: "6px 12px", fontSize: "11px" }}
              />
              <button type="submit" className="btn btn-glass" style={{ padding: "6px 12px", fontSize: "11px" }}>
                <IconSearch size={12} />
                <span>Load</span>
              </button>
            </form>

            {/* Suggestions Dropdown */}
            {showSuggestions && customInput.trim().length > 0 && (
              <div
                style={{
                  position: "absolute",
                  top: "100%",
                  left: 0,
                  right: 0,
                  marginTop: "4px",
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-medium)",
                  borderRadius: "8px",
                  boxShadow: "0 12px 28px rgba(0, 0, 0, 0.4)",
                  zIndex: 50,
                  maxHeight: "220px",
                  overflowY: "auto",
                }}
              >
                {suggestions.length > 0 ? (
                  suggestions.map((s) => (
                    <div
                      key={s}
                      onClick={() => selectSuggestion(s)}
                      style={{
                        padding: "8px 12px",
                        fontSize: "12px",
                        fontFamily: "'JetBrains Mono', monospace",
                        color: "var(--text-primary)",
                        cursor: "pointer",
                        borderBottom: "1px solid var(--border-subtle)",
                        transition: "background 0.15s ease",
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--border-glass)")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <span style={{ fontWeight: 700, color: "var(--cyan)" }}>{s}</span>
                      <span style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "8px" }}>NSE</span>
                    </div>
                  ))
                ) : (
                  <div style={{ padding: "12px", fontSize: "11px", color: "var(--crimson)", textAlign: "center" }}>
                    No matching NSE/BSE symbols found
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 4. Canvas Chart Viewport & Error State */}
      <div
        style={{
          width: "100%",
          height: isFullscreen ? "calc(100vh - 200px)" : `${height}px`,
          position: "relative",
          borderRadius: "8px",
          overflow: "hidden",
          border: "1px solid var(--border-subtle)",
          background: theme === "dark" ? "#090d16" : "#ffffff",
        }}
      >
        {chartLoading && (
          <div
            style={{
              position: "absolute",
              top: "14px",
              right: "14px",
              zIndex: 10,
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: "var(--bg-surface-glass)",
              padding: "4px 10px",
              borderRadius: "20px",
              fontSize: "11px",
              color: "var(--cyan)",
            }}
          >
            <span className="loader" style={{ width: "10px", height: "10px" }} />
            <span>Fetching Authentic Candles...</span>
          </div>
        )}

        {/* Error / Invalid Symbol Empty State */}
        {chartError && (
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              zIndex: 20,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              background: theme === "dark" ? "rgba(9, 13, 22, 0.95)" : "rgba(255, 255, 255, 0.95)",
              padding: "32px",
              textAlign: "center",
            }}
          >
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "50%",
                background: "rgba(255, 51, 102, 0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: "16px",
                border: "1px solid rgba(255, 51, 102, 0.3)",
              }}
            >
              <IconSearch size={22} color="var(--crimson)" />
            </div>

            <span className="badge badge-bearish" style={{ marginBottom: "10px", fontSize: "11px" }}>
              TICKER NOT FOUND
            </span>

            <h3 style={{ fontSize: "18px", fontWeight: 800, margin: "0 0 8px 0", letterSpacing: "-0.01em" }}>
              No Market Data for "{symbol}"
            </h3>

            <p style={{ maxWidth: "460px", fontSize: "13px", color: "var(--text-secondary)", margin: "0 0 20px 0" }}>
              The symbol entered does not match any actively traded security on the National Stock Exchange (NSE) or Bombay Stock Exchange (BSE).
            </p>

            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", justifyContent: "center" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Try a valid ticker:</span>
              {["NIFTY", "TCS", "INFY", "RELIANCE", "TATASTEEL"].map((sym) => (
                <button
                  key={sym}
                  onClick={() => selectSuggestion(sym)}
                  className="btn btn-glass font-mono"
                  style={{ padding: "4px 10px", fontSize: "11px", borderRadius: "6px" }}
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={containerRef} style={{ width: "100%", height: "100%", position: "relative" }} />
      </div>

      {/* 5. Indicators Pill Toggles & Legend Bar */}
      {!chartError && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "12px",
            marginTop: "12px",
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          {/* Toggleable Pills */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
            <button
              onClick={() => setShowAvwap(!showAvwap)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                background: showAvwap ? "rgba(0, 240, 255, 0.12)" : "var(--bg-surface-elevated)",
                color: showAvwap ? "var(--cyan)" : "var(--text-muted)",
                border: `1px solid ${showAvwap ? "var(--cyan)" : "var(--border-subtle)"}`,
                padding: "3px 8px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: "var(--cyan)" }} />
              <span>Anchored VWAP</span>
            </button>

            <button
              onClick={() => setShowEma20(!showEma20)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                background: showEma20 ? "rgba(192, 132, 252, 0.12)" : "var(--bg-surface-elevated)",
                color: showEma20 ? "var(--purple)" : "var(--text-muted)",
                border: `1px solid ${showEma20 ? "var(--purple)" : "var(--border-subtle)"}`,
                padding: "3px 8px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: "var(--purple)" }} />
              <span>20 EMA</span>
            </button>

            <button
              onClick={() => setShowEma50(!showEma50)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                background: showEma50 ? "rgba(245, 158, 11, 0.12)" : "var(--bg-surface-elevated)",
                color: showEma50 ? "var(--amber)" : "var(--text-muted)",
                border: `1px solid ${showEma50 ? "var(--amber)" : "var(--border-subtle)"}`,
                padding: "3px 8px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: "var(--amber)" }} />
              <span>50 EMA</span>
            </button>

            <button
              onClick={() => setShowVolume(!showVolume)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                background: showVolume ? "rgba(0, 255, 136, 0.12)" : "var(--bg-surface-elevated)",
                color: showVolume ? "var(--emerald)" : "var(--text-muted)",
                border: `1px solid ${showVolume ? "var(--emerald)" : "var(--border-subtle)"}`,
                padding: "3px 8px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: "var(--emerald)" }} />
              <span>Volume Bars</span>
            </button>
          </div>

          <div className="font-mono" style={{ fontSize: "10px" }}>
            Engine: TradingView Lightweight Charts (Verified Authentic) • IST Timezone
          </div>
        </div>
      )}
    </div>
  );
}
