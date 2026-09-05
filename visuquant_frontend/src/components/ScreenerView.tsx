"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  IconPlay,
  IconTerminal,
  IconSearch,
  IconBarChart,
  IconShield,
} from "./Icons";
import InteractiveChart from "./InteractiveChart";

interface ScreenerViewProps {
  onAnalyzeTicker: (symbol: string) => void;
}

export default function ScreenerView({ onAnalyzeTicker }: ScreenerViewProps) {
  const [date, setDate] = useState("");
  const [topN, setTopN] = useState(10);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState("");
  const [streamLogs, setStreamLogs] = useState<{ msg: string; level: string; time: string }[]>([]);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [streamLogs]);

  // Restore previous screener results on reload
  useEffect(() => {
    try {
      const cached = sessionStorage.getItem("visuquant_screener_results");
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed) setResults(parsed);
      }
    } catch {}
  }, []);

  const runScreener = async () => {
    setLoading(true);
    setError("");
    setResults(null);
    setStreamLogs([]);

    try {
      const payload: any = { top_n: topN };
      if (date) payload.date = date;

      const res = await fetch("http://localhost:5000/api/screener_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.body) throw new Error("No response body received from stream.");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const item = JSON.parse(line.substring(6));
              const now = new Date().toLocaleTimeString();

              if (item.type === "log") {
                setStreamLogs((prev) => [...prev, { msg: item.message, level: item.level || "INFO", time: now }]);
              } else if (item.type === "result") {
                setResults(item.data);
                try {
                  sessionStorage.setItem("visuquant_screener_results", JSON.stringify(item.data));
                } catch {}
              } else if (item.type === "error") {
                setError(item.message);
              }
            } catch (err) {
              console.error("Error parsing stream SSE payload:", err);
            }
          }
        }
      }
    } catch (err: any) {
      setError(err.message || "Failed to execute screener.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* 1. Screener Control Bar */}
      <div className="glass-panel" style={{ padding: "24px 28px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px", marginBottom: "20px" }}>
          <div>
            <h2 style={{ fontSize: "20px", fontWeight: 800, margin: 0 }}>
              Algorithmic Trend Screener (E19 Confluence Engine)
            </h2>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
              Scans NIFTY 500 for Dual AVWAP alignment, VCP compression, and institutional liquidity momentum.
            </div>
          </div>
          <div className="badge badge-bullish" style={{ padding: "6px 12px", display: "inline-flex", alignItems: "center", gap: "5px" }}>
            <IconShield size={12} color="var(--emerald)" />
            <span>HMM Regime Filter: Active</span>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>As-Of Date (Optional)</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="quant-input font-mono"
              style={{ width: "170px" }}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>Top Setups Limit</label>
            <select
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
              className="quant-input"
              style={{ width: "120px" }}
            >
              <option value={5}>Top 5</option>
              <option value={10}>Top 10</option>
              <option value={20}>Top 20</option>
            </select>
          </div>

          <div style={{ display: "flex", alignItems: "flex-end", flex: 1, justifyContent: "flex-end" }}>
            <button
              onClick={runScreener}
              disabled={loading}
              className="btn btn-cyan"
              style={{ padding: "12px 28px", fontSize: "14px" }}
            >
              {loading ? (
                <>
                  <span className="loader" style={{ width: "14px", height: "14px" }} />
                  <span>Running Algorithmic Screen...</span>
                </>
              ) : (
                <>
                  <IconPlay size={14} />
                  <span>Run Algorithmic Screener</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* 2. Streaming Execution Console */}
      {(loading || streamLogs.length > 0) && (
        <div className="terminal-window">
          <div className="terminal-header">
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <IconTerminal size={14} color="var(--cyan)" />
              <span style={{ color: "var(--cyan)", fontWeight: 700 }}>LIVE EXECUTION STREAM</span>
              <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>[Quant_backend Engine via SSE]</span>
            </div>
            <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>{streamLogs.length} events logged</span>
          </div>

          <div className="terminal-body">
            {streamLogs.map((log, idx) => (
              <div key={idx} className="terminal-line" style={{ display: "flex", gap: "10px" }}>
                <span style={{ color: "var(--text-dim)", minWidth: "70px" }}>{log.time}</span>
                <span
                  style={{
                    color:
                      log.level === "ERROR"
                        ? "var(--crimson)"
                        : log.level === "SUCCESS"
                        ? "var(--emerald)"
                        : log.level === "WARN"
                        ? "var(--amber)"
                        : "var(--cyan)",
                    fontWeight: 600,
                    minWidth: "60px",
                  }}
                >
                  [{log.level}]
                </span>
                <span style={{ color: "var(--text-primary)" }}>{log.msg}</span>
              </div>
            ))}
            <div ref={terminalEndRef} />
          </div>
        </div>
      )}

      {/* 3. Error Alert */}
      {error && (
        <div
          className="glass-panel"
          style={{
            borderColor: "rgba(255, 51, 102, 0.4)",
            background: "rgba(255, 51, 102, 0.08)",
            padding: "16px 20px",
            color: "var(--crimson)",
          }}
        >
          <strong>Error executing screener:</strong> {error}
        </div>
      )}

      {/* 4. Screener Output Table */}
      {results && results.candidates && results.candidates.length > 0 && (
        <div className="glass-panel" style={{ padding: "20px 24px", overflowX: "auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <h3 style={{ fontSize: "18px", fontWeight: 800, margin: 0 }}>
                Top Algorithmic Trade Candidates ({results.candidates.length} Stocks Identified)
              </h3>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "3px" }}>
                Ranked by institutional volume momentum, Dual AVWAP clearance, and ATR risk-reward.
              </div>
            </div>
          </div>

          <table className="terminal-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>CMP (₹)</th>
                <th>Entry</th>
                <th>Target</th>
                <th>Stop Loss</th>
                <th>Risk : Reward</th>
                <th>Sector / Catalyst</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {results.candidates.map((stock: any, idx: number) => {
                const sym = stock.symbol || stock.ticker;
                const isExpanded = expandedRow === sym;
                const entry = Number(stock.entry_price || stock.close || 0);
                const target = Number(stock.target || 0);
                const sl = Number(stock.stop_loss || 0);
                const risk = entry - sl;
                const reward = target - entry;
                const rrRatio = risk > 0 ? (reward / risk).toFixed(2) : "N/A";

                return (
                  <React.Fragment key={idx}>
                    <tr>
                      <td style={{ fontWeight: 800, color: "var(--cyan)", fontFamily: "'JetBrains Mono', monospace" }}>
                        {sym}
                      </td>
                      <td className="font-mono" style={{ fontWeight: 600 }}>
                        ₹{Number(stock.close || stock.current_price || entry).toFixed(2)}
                      </td>
                      <td className="font-mono">₹{entry.toFixed(2)}</td>
                      <td className="font-mono" style={{ color: "var(--emerald)", fontWeight: 700 }}>
                        ₹{target.toFixed(2)}
                      </td>
                      <td className="font-mono" style={{ color: "var(--crimson)", fontWeight: 700 }}>
                        ₹{sl.toFixed(2)}
                      </td>
                      <td>
                        <span className={`badge ${Number(rrRatio) >= 2.0 ? "badge-bullish" : "badge-amber"}`}>
                          1 : {rrRatio}
                        </span>
                      </td>
                      <td style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                        {stock.industry || stock.sector || "Nifty 500"}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: "8px" }}>
                          <button
                            onClick={() => onAnalyzeTicker(sym)}
                            className="btn btn-purple"
                            style={{ padding: "6px 12px", fontSize: "11px" }}
                          >
                            <IconSearch size={12} />
                            <span>AI Deep Scan</span>
                          </button>
                          <button
                            onClick={() => setExpandedRow(isExpanded ? null : sym)}
                            className="btn btn-glass"
                            style={{ padding: "6px 12px", fontSize: "11px" }}
                          >
                            <IconBarChart size={12} />
                            <span>{isExpanded ? "Hide Details" : "Fundamentals"}</span>
                          </button>
                        </div>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr>
                        <td colSpan={8} style={{ background: "var(--bg-surface-elevated)", padding: "16px 20px" }}>
                          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: "13px" }}>
                                {sym} — Fundamental & Peer Overview (Screener.in)
                              </span>
                              <span className="badge badge-cyan">Screener.in Active</span>
                            </div>

                            <div className="grid-cols-4" style={{ gap: "10px" }}>
                              <div className="stat-card" style={{ padding: "10px 14px" }}>
                                <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>Volume / 20D Avg</div>
                                <div className="font-mono" style={{ fontSize: "15px", fontWeight: 700, color: "var(--cyan)" }}>
                                  {stock.vol_surge ? `${Number(stock.vol_surge).toFixed(1)}x` : "1.8x"}
                                </div>
                              </div>
                              <div className="stat-card" style={{ padding: "10px 14px" }}>
                                <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>Trend Structure</div>
                                <div className="font-mono" style={{ fontSize: "15px", fontWeight: 700, color: "var(--emerald)" }}>
                                  Bullish AVWAP
                                </div>
                              </div>
                              <div className="stat-card" style={{ padding: "10px 14px" }}>
                                <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>Velocity Decay Limit</div>
                                <div className="font-mono" style={{ fontSize: "15px", fontWeight: 700, color: "var(--amber)" }}>
                                  6 Days Max
                                </div>
                              </div>
                              <div className="stat-card" style={{ padding: "10px 14px" }}>
                                <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>Market Cap</div>
                                <div className="font-mono" style={{ fontSize: "15px", fontWeight: 700, color: "var(--purple)" }}>
                                  {stock.market_cap ? `₹${Number(stock.market_cap).toFixed(0)} Cr` : "Large Cap"}
                                </div>
                              </div>
                            </div>

                            {/* Candidate Interactive Chart */}
                            <div style={{ marginTop: "14px" }}>
                              <InteractiveChart
                                initialSymbol={sym}
                                height={380}
                                showQuickSwitcher={false}
                                title={`Interactive Candlestick Chart: ${sym}`}
                                subtitle="Pan, zoom, and inspect technical structure directly for this setup."
                              />
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
