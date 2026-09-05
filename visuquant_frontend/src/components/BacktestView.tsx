"use client";

import React, { useState, useEffect } from "react";
import { IconPlay, IconBarChart, IconShield } from "./Icons";
import TickerAutocomplete from "./TickerAutocomplete";

export default function BacktestView() {
  const [symbol, setSymbol] = useState("TCS");
  const [months, setMonths] = useState(60);
  const [loading, setLoading] = useState(false);
  const [backtestData, setBacktestData] = useState<any>(null);
  const [error, setError] = useState("");

  const strategies = [
    {
      name: "E19 Dead Money Cut",
      badge: "CHAMPION LIVE",
      badgeClass: "badge-cyan",
      cagr: "+39.82%",
      mdd: "-10.66%",
      calmar: "3.735",
      holdout: "+62.05%",
      status: "Active on GitHub Actions & Telegram",
      highlight: true,
    },
    {
      name: "E19 Baseline (Dual AVWAP)",
      badge: "BASELINE",
      badgeClass: "badge-purple",
      cagr: "+32.40%",
      mdd: "-14.20%",
      calmar: "2.281",
      holdout: "+44.10%",
      status: "Prior Benchmark",
      highlight: false,
    },
    {
      name: "NIFTY 500 TRI",
      badge: "INDEX BENCHMARK",
      badgeClass: "badge-amber",
      cagr: "+15.20%",
      mdd: "-18.40%",
      calmar: "0.826",
      holdout: "+28.50%",
      status: "Passive Index",
      highlight: false,
    },
  ];

  // Restore cached backtest results on reload
  useEffect(() => {
    try {
      const cached = sessionStorage.getItem("visuquant_backtest_cache");
      if (cached) {
        const parsed = JSON.parse(cached);
        // Clear obsolete dummy BASKET cache
        if (parsed.backtestData && parsed.backtestData.symbol === "BASKET") {
          sessionStorage.removeItem("visuquant_backtest_cache");
          return;
        }
        if (parsed.backtestData) setBacktestData(parsed.backtestData);
        if (parsed.symbol) setSymbol(parsed.symbol);
        if (parsed.months) setMonths(parsed.months);
      }
    } catch {}
  }, []);


  const runBacktest = async () => {
    if (!symbol.trim()) return;
    setLoading(true);
    setError("");
    setBacktestData(null);

    try {
      const res = await fetch("http://localhost:5000/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: symbol.trim().toUpperCase(), months }),
      });
      const data = await res.json();
      if (data.status === "success" && data.data) {
        setBacktestData(data.data);
        try {
          sessionStorage.setItem(
            "visuquant_backtest_cache",
            JSON.stringify({ backtestData: data.data, symbol: symbol.trim().toUpperCase(), months })
          );
        } catch {}
      } else {
        setError(data.message || "Backtest execution returned no data.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to reach backtest engine.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* 1. Header Intro */}
      <div className="glass-panel" style={{ padding: "28px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <h2 style={{ fontSize: "20px", fontWeight: 800, margin: 0 }}>
              Quantitative Strategy Forensics & Backtest Lab
            </h2>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
              Comprehensive performance attribution across market regimes (2020 - 2026).
            </div>
          </div>
          <div className="badge badge-bullish" style={{ padding: "6px 12px", display: "inline-flex", alignItems: "center", gap: "5px" }}>
            <IconShield size={12} color="var(--emerald)" />
            <span>Walk-Forward Verified</span>
          </div>
        </div>
      </div>

      {/* 2. Strategy Performance Comparison Cards */}
      <div className="grid-cols-3">
        {strategies.map((strat, idx) => (
          <div
            key={idx}
            className={strat.highlight ? "glass-panel-glow" : "glass-panel"}
            style={{
              padding: "24px",
              display: "flex",
              flexDirection: "column",
              gap: "16px",
              position: "relative",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "16px", fontWeight: 800 }}>{strat.name}</span>
              <span className={`badge ${strat.badgeClass}`}>{strat.badge}</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", paddingTop: "8px" }}>
              <div>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>CAGR</div>
                <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--emerald)" }}>
                  {strat.cagr}
                </div>
              </div>
              <div>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>MAX DRAWDOWN</div>
                <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--crimson)" }}>
                  {strat.mdd}
                </div>
              </div>
              <div>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>CALMAR RATIO</div>
                <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--cyan)" }}>
                  {strat.calmar}
                </div>
              </div>
              <div>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>2024-26 HOLDOUT</div>
                <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--amber)" }}>
                  {strat.holdout}
                </div>
              </div>
            </div>

            <div style={{ fontSize: "12px", color: "var(--text-secondary)", borderTop: "1px solid var(--border-subtle)", paddingTop: "12px" }}>
              {strat.status}
            </div>
          </div>
        ))}
      </div>

      {/* 3. Single Stock Historical Backtest Runner */}
      <div className="glass-panel" style={{ padding: "28px", overflow: "visible" }}>
        <h3 style={{ fontSize: "17px", fontWeight: 800, marginBottom: "16px" }}>
          Single Ticker Historical Simulation (E19 Ruleset)
        </h3>

        <div style={{ display: "flex", gap: "16px", alignItems: "flex-end", flexWrap: "wrap", marginBottom: "20px", overflow: "visible" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px", flex: 1, minWidth: "200px", position: "relative" }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>Symbol</label>
            <TickerAutocomplete
              value={symbol}
              onChange={setSymbol}
              placeholder="e.g. TCS"
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>Simulation Horizon</label>
            <select
              value={months}
              onChange={(e) => setMonths(Number(e.target.value))}
              className="quant-input"
              style={{ width: "160px" }}
            >
              <option value={12}>12 Months (1 Year)</option>
              <option value={24}>24 Months (2 Years)</option>
              <option value={36}>36 Months (3 Years)</option>
              <option value={60}>60 Months (5 Years)</option>
            </select>
          </div>

          <button
            onClick={runBacktest}
            disabled={loading}
            className="btn btn-cyan"
            style={{ padding: "12px 24px", fontSize: "14px" }}
          >
            {loading ? (
              <>
                <span className="loader" style={{ width: "14px", height: "14px" }} />
                <span>Computing Simulation...</span>
              </>
            ) : (
              <>
                <IconPlay size={14} />
                <span>Run Single-Stock Backtest</span>
              </>
            )}
          </button>
        </div>

        {error && (
          <div
            className="glass-panel"
            style={{
              borderColor: "rgba(255, 51, 102, 0.4)",
              background: "rgba(255, 51, 102, 0.08)",
              padding: "16px 20px",
              color: "var(--crimson)",
              marginBottom: "20px",
            }}
          >
            {error}
          </div>
        )}

        {backtestData && (
          <div style={{ display: "flex", flexDirection: "column", gap: "20px", marginTop: "16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h4 style={{ fontSize: "16px", fontWeight: 800, margin: 0 }}>
                Historical Simulation Performance ({backtestData.symbol || symbol} • {backtestData.period || `${months}M`})
              </h4>
              <span className="badge badge-cyan">Dynamic 20 SMA Exit</span>
            </div>

            {/* Metrics Grid */}
            <div className="grid-cols-4" style={{ gap: "12px" }}>
              <div className="stat-card" style={{ padding: "14px 18px" }}>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>WIN RATE</div>
                <div
                  className="font-mono"
                  style={{
                    fontSize: "22px",
                    fontWeight: 800,
                    color: Number(backtestData.metrics?.["Win Rate (%)"] || 0) >= 50 ? "var(--emerald)" : "var(--crimson)",
                    marginTop: "4px",
                  }}
                >
                  {backtestData.metrics?.["Win Rate (%)"] !== undefined ? `${backtestData.metrics["Win Rate (%)"]}%` : "—"}
                </div>
              </div>

              <div className="stat-card" style={{ padding: "14px 18px" }}>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>CAGR</div>
                <div
                  className="font-mono"
                  style={{
                    fontSize: "22px",
                    fontWeight: 800,
                    color: Number(backtestData.metrics?.["CAGR (%)"] || 0) > 0 ? "var(--emerald)" : "var(--crimson)",
                    marginTop: "4px",
                  }}
                >
                  {backtestData.metrics?.["CAGR (%)"] !== undefined ? `${backtestData.metrics["CAGR (%)"] > 0 ? "+" : ""}${backtestData.metrics["CAGR (%)"]}%` : "—"}
                </div>
              </div>

              <div className="stat-card" style={{ padding: "14px 18px" }}>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>SHARPE RATIO</div>
                <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--cyan)", marginTop: "4px" }}>
                  {backtestData.metrics?.["Sharpe Ratio"] !== undefined ? Number(backtestData.metrics["Sharpe Ratio"]).toFixed(2) : "—"}
                </div>
              </div>

              <div className="stat-card" style={{ padding: "14px 18px" }}>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>MAX DRAWDOWN</div>
                <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--crimson)", marginTop: "4px" }}>
                  {backtestData.metrics?.["Max Drawdown (%)"] !== undefined ? `${backtestData.metrics["Max Drawdown (%)"]}%` : "—"}
                </div>
              </div>

              <div className="stat-card" style={{ padding: "14px 18px" }}>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>TOTAL TRADES</div>
                <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--amber)", marginTop: "4px" }}>
                  {backtestData.metrics?.["Total Trades"] !== undefined ? backtestData.metrics["Total Trades"] : (backtestData.trades?.length || 0)}
                </div>
              </div>

              <div className="stat-card" style={{ padding: "14px 18px" }}>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>AVG WIN / LOSS</div>
                <div className="font-mono" style={{ fontSize: "18px", fontWeight: 800, marginTop: "6px" }}>
                  <span style={{ color: "var(--emerald)" }}>+{backtestData.metrics?.["Average Win (%)"] || 0}%</span>
                  <span style={{ color: "var(--text-dim)", margin: "0 4px" }}>/</span>
                  <span style={{ color: "var(--crimson)" }}>{backtestData.metrics?.["Average Loss (%)"] || 0}%</span>
                </div>
              </div>

              <div className="stat-card" style={{ padding: "14px 18px" }}>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>CALMAR RATIO</div>
                <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--purple)", marginTop: "4px" }}>
                  {backtestData.metrics?.["Calmar Ratio"] !== undefined ? Number(backtestData.metrics["Calmar Ratio"]).toFixed(2) : "—"}
                </div>
              </div>

              <div className="stat-card" style={{ padding: "14px 18px" }}>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>PROFIT FACTOR</div>
                <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--cyan)", marginTop: "4px" }}>
                  {backtestData.metrics?.["Profit Factor"] !== undefined ? Number(backtestData.metrics["Profit Factor"]).toFixed(2) : (backtestData.metrics?.["Sortino Ratio"] !== undefined ? Number(backtestData.metrics["Sortino Ratio"]).toFixed(2) : "—")}
                </div>
              </div>
            </div>

            {/* Simulated Trade History Table */}
            {backtestData.trades && backtestData.trades.length > 0 ? (
              <div>
                <h4 style={{ fontSize: "14px", fontWeight: 700, marginBottom: "12px", color: "var(--text-primary)" }}>
                  Simulated Trade History ({backtestData.trades.length} Executed Trades for {backtestData.symbol || symbol})
                </h4>
                <div style={{ maxHeight: "360px", overflowY: "auto", border: "1px solid var(--border-subtle)", borderRadius: "8px" }}>
                  <table className="terminal-table" style={{ fontSize: "12px" }}>
                    <thead>
                      <tr>
                        <th>Entry Date</th>
                        <th>Exit Date</th>
                        <th>Holding</th>
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>Exit Catalyst</th>
                        <th style={{ textAlign: "right" }}>Net Return</th>
                      </tr>
                    </thead>
                    <tbody>
                      {backtestData.trades.map((t: any, idx: number) => {
                        const ret = Number(t.return || 0);
                        const isPos = ret > 0;
                        const reason = t.exit_reason || "Trailing SMA";
                        const reasonClass =
                          reason === "Target Hit"
                            ? "badge-bullish"
                            : reason === "Stop Loss"
                            ? "badge-bearish"
                            : reason === "Dead Money Cut"
                            ? "badge-amber"
                            : "badge-cyan";

                        return (
                          <tr key={idx}>
                            <td className="font-mono" style={{ color: "var(--text-secondary)" }}>{t.entry_date}</td>
                            <td className="font-mono" style={{ color: "var(--text-secondary)" }}>{t.exit_date}</td>
                            <td className="font-mono" style={{ color: "var(--text-muted)", fontSize: "11px" }}>
                              {t.holding_days ? `${t.holding_days} sessions` : "—"}
                            </td>
                            <td className="font-mono">₹{Number(t.entry_price || 0).toFixed(2)}</td>
                            <td className="font-mono">₹{Number(t.exit_price || 0).toFixed(2)}</td>
                            <td>
                              <span className={`badge ${reasonClass}`} style={{ fontSize: "10px", padding: "2px 8px" }}>
                                {reason}
                              </span>
                            </td>
                            <td
                              className="font-mono"
                              style={{
                                textAlign: "right",
                                fontWeight: 700,
                                color: isPos ? "var(--emerald)" : "var(--crimson)",
                              }}
                            >
                              {isPos ? "+" : ""}{(ret > 1 ? ret : ret * 100).toFixed(2)}%
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p style={{ color: "var(--text-secondary)", fontSize: "13px" }}>
                No trades generated for {backtestData.symbol || symbol} during the selected {months}-month horizon.
              </p>
            )}

          </div>
        )}
      </div>
    </div>
  );
}
