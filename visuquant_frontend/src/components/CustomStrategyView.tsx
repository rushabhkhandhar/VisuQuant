"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  IconPlay,
  IconTerminal,
  IconSearch,
  IconCheck,
  IconTrendingUp,
  IconLayers,
  IconShield,
  IconEye,
  IconBarChart,
  IconActivity,
  IconZap,
  IconCpu,
} from "./Icons";

interface CustomStrategyViewProps {
  onAnalyzeTicker: (symbol: string) => void;
}

export default function CustomStrategyView({ onAnalyzeTicker }: CustomStrategyViewProps) {
  const [selectedTools, setSelectedTools] = useState<string[]>([
    "Trendline", "S&R", "Market Structure", "VWAP"
  ]);
  const [selectedFilters, setSelectedFilters] = useState<string[]>([
    "Require RR >= 1:2", "Require High Liquidity (>100k Vol)"
  ]);
  const [riskOption, setRiskOption] = useState("1.5x ATR");
  const [aiLogicPrompt, setAiLogicPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState("");
  const [streamLogs, setStreamLogs] = useState<{ msg: string; level: string; time: string }[]>([]);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [streamLogs]);

  const AVAILABLE_TOOLS = [
    { name: "Trendline", icon: IconTrendingUp },
    { name: "S&R", icon: IconLayers },
    { name: "Market Structure", icon: IconShield },
    { name: "Chart Patterns", icon: IconEye },
    { name: "Candlestick Patterns", icon: IconBarChart },
    { name: "VWAP", icon: IconActivity },
    { name: "Moving Avg", icon: IconActivity },
    { name: "RSI", icon: IconZap },
    { name: "MACD", icon: IconBarChart },
  ];

  const AVAILABLE_FILTERS = [
    "Require RR >= 1:2",
    "Exclude Flat VWAP",
    "Require High Liquidity (>100k Vol)",
    "Exclude High Volatility (ATR > 5%)",
  ];

  const PREDEFINED_STRATEGIES = [
    {
      title: "Dual AVWAP Momentum Breakout",
      prompt: "Filter stocks trading above both Earnings-Anchored VWAP and Swing High AVWAP with RSI between 55 and 70.",
    },
    {
      title: "Volatility Contraction Pattern (VCP)",
      prompt: "Find stocks with daily ATR decreasing over the last 10 days, breaking out above 20 EMA with 2x volume surge.",
    },
    {
      title: "Institutional Pullback to 50 EMA",
      prompt: "Select stocks in long-term uptrend (Close > 200 EMA) touching 50 EMA with bullish hammer or engulfing pattern.",
    },
  ];

  const toggleTool = (tool: string) => {
    setSelectedTools((prev) =>
      prev.includes(tool) ? prev.filter((t) => t !== tool) : [...prev, tool]
    );
  };

  const toggleFilter = (filter: string) => {
    setSelectedFilters((prev) =>
      prev.includes(filter) ? prev.filter((f) => f !== filter) : [...prev, filter]
    );
  };

  const runCustomScreen = async () => {
    if (selectedTools.length === 0 && !aiLogicPrompt) {
      setError("Please select at least one trading tool or provide an AI strategy prompt.");
      return;
    }

    setLoading(true);
    setError("");
    setResults(null);
    setStreamLogs([]);

    try {
      const payload: any = {
        top_n: 15,
        trading_tools: selectedTools,
        trading_filters: selectedFilters,
        risk_management: riskOption,
      };
      if (aiLogicPrompt) payload.ai_logic_prompt = aiLogicPrompt;

      const res = await fetch("http://localhost:5000/api/custom_screener_stream", {
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
              } else if (item.type === "error") {
                setError(item.message);
              }
            } catch (err) {
              console.error("Error parsing custom stream SSE payload:", err);
            }
          }
        }
      }
    } catch (err: any) {
      setError(err.message || "Failed to execute custom strategy screener.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* 1. Builder Workspace */}
      <div className="glass-panel" style={{ padding: "28px" }}>
        <div style={{ marginBottom: "24px" }}>
          <h2 style={{ fontSize: "20px", fontWeight: 800, margin: 0 }}>
            Custom Quantitative Strategy Builder
          </h2>
          <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
            Compose proprietary trading rules by combining visual indicators, quantitative filters, and natural language AI logic.
          </div>
        </div>

        {/* Section A: Tool Pills */}
        <div style={{ marginBottom: "20px" }}>
          <label style={{ fontSize: "13px", fontWeight: 700, color: "var(--text-primary)", display: "block", marginBottom: "10px" }}>
            1. Core Analysis Tools (Stocks must pass all selected)
          </label>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {AVAILABLE_TOOLS.map((t) => {
              const IconComp = t.icon;
              const isSelected = selectedTools.includes(t.name);
              return (
                <button
                  key={t.name}
                  onClick={() => toggleTool(t.name)}
                  className={`btn ${isSelected ? "btn-cyan" : "btn-glass"}`}
                  style={{ padding: "8px 14px", fontSize: "12px", gap: "6px" }}
                >
                  <IconComp size={13} color="currentColor" />
                  <span>{t.name}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Section B: Filter Pills */}
        <div style={{ marginBottom: "20px" }}>
          <label style={{ fontSize: "13px", fontWeight: 700, color: "var(--text-primary)", display: "block", marginBottom: "10px" }}>
            2. Quantitative Risk & Liquidity Filters
          </label>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {AVAILABLE_FILTERS.map((f) => {
              const isSelected = selectedFilters.includes(f);
              return (
                <button
                  key={f}
                  onClick={() => toggleFilter(f)}
                  className={`btn ${isSelected ? "btn-emerald" : "btn-glass"}`}
                  style={{ padding: "8px 14px", fontSize: "12px", gap: "6px" }}
                >
                  {isSelected ? <IconCheck size={12} color="currentColor" /> : <span>+</span>}
                  <span>{f}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Section C: AI Strategy Logic */}
        <div style={{ marginBottom: "24px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <label style={{ fontSize: "13px", fontWeight: 700, color: "var(--text-primary)" }}>
              3. AI Natural Language Logic (Optional)
            </label>
            <span className="badge badge-purple" style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
              <IconCpu size={12} />
              <span>Qwen2.5-VL / Gemini Code Agent</span>
            </span>
          </div>

          <div style={{ display: "flex", gap: "10px", marginBottom: "10px", flexWrap: "wrap" }}>
            {PREDEFINED_STRATEGIES.map((preset, idx) => (
              <button
                key={idx}
                onClick={() => setAiLogicPrompt(preset.prompt)}
                className="btn btn-glass"
                style={{ fontSize: "11px", padding: "4px 10px" }}
              >
                Preset: {preset.title}
              </button>
            ))}
          </div>

          <textarea
            value={aiLogicPrompt}
            onChange={(e) => setAiLogicPrompt(e.target.value)}
            placeholder="Describe custom logic in plain English (e.g. 'Only select stocks breaking out above 52-week high with ROCE > 25% and Debt to Equity < 0.5')..."
            className="quant-input font-mono"
            rows={3}
            style={{ width: "100%", resize: "vertical" }}
          />
        </div>

        {/* Section D: Execution Bar */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px", paddingTop: "16px", borderTop: "1px solid var(--border-subtle)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>Risk Model:</span>
            <select
              value={riskOption}
              onChange={(e) => setRiskOption(e.target.value)}
              className="quant-input"
              style={{ width: "130px", padding: "6px 10px", fontSize: "12px" }}
            >
              <option value="1.5x ATR">1.5x ATR</option>
              <option value="2.0x ATR">2.0x ATR</option>
              <option value="2.5x ATR">2.5x ATR</option>
              <option value="5.0% Fixed">5.0% Fixed</option>
            </select>
          </div>

          <button
            onClick={runCustomScreen}
            disabled={loading}
            className="btn btn-purple"
            style={{ padding: "12px 28px", fontSize: "14px" }}
          >
            {loading ? (
              <>
                <span className="loader" style={{ width: "14px", height: "14px" }} />
                <span>Synthesizing Custom Logic...</span>
              </>
            ) : (
              <>
                <IconPlay size={14} />
                <span>Run Custom Strategy Scan</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 2. Streaming Logs Console */}
      {(loading || streamLogs.length > 0) && (
        <div className="terminal-window">
          <div className="terminal-header">
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <IconTerminal size={14} color="var(--purple)" />
              <span style={{ color: "var(--purple)", fontWeight: 700 }}>CUSTOM STRATEGY EXECUTION TERMINAL</span>
            </div>
            <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>{streamLogs.length} events</span>
          </div>
          <div className="terminal-body">
            {streamLogs.map((log, idx) => (
              <div key={idx} className="terminal-line" style={{ display: "flex", gap: "10px" }}>
                <span style={{ color: "var(--text-dim)", minWidth: "70px" }}>{log.time}</span>
                <span style={{ color: "var(--cyan)", fontWeight: 600, minWidth: "60px" }}>[{log.level}]</span>
                <span style={{ color: "var(--text-primary)" }}>{log.msg}</span>
              </div>
            ))}
            <div ref={terminalEndRef} />
          </div>
        </div>
      )}

      {/* 3. Error Banner */}
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
          <strong>Execution error:</strong> {error}
        </div>
      )}

      {/* 4. Results Table */}
      {results && results.candidates && results.candidates.length > 0 && (
        <div className="glass-panel" style={{ padding: "20px 24px", overflowX: "auto" }}>
          <h3 style={{ fontSize: "18px", fontWeight: 800, marginBottom: "16px" }}>
            Custom Screen Output ({results.candidates.length} Stocks Qualified)
          </h3>
          <table className="terminal-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>CMP (₹)</th>
                <th>Target</th>
                <th>Stop Loss</th>
                <th>Matched Rule Attributes</th>
                <th style={{ textAlign: "right" }}>Deep Vision</th>
              </tr>
            </thead>
            <tbody>
              {results.candidates.map((stock: any, idx: number) => {
                const sym = stock.symbol || stock.ticker;
                return (
                  <tr key={idx}>
                    <td style={{ fontWeight: 800, color: "var(--cyan)", fontFamily: "'JetBrains Mono', monospace" }}>
                      {sym}
                    </td>
                    <td className="font-mono">₹{Number(stock.close || stock.current_price || 0).toFixed(2)}</td>
                    <td className="font-mono" style={{ color: "var(--emerald)", fontWeight: 700 }}>
                      ₹{Number(stock.target || 0).toFixed(2)}
                    </td>
                    <td className="font-mono" style={{ color: "var(--crimson)", fontWeight: 700 }}>
                      ₹{Number(stock.stop_loss || 0).toFixed(2)}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                        <span className="badge badge-cyan">Custom Tool Match</span>
                        <span className="badge badge-bullish">Risk Controlled</span>
                      </div>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        onClick={() => onAnalyzeTicker(sym)}
                        className="btn btn-purple"
                        style={{ padding: "6px 12px", fontSize: "11px" }}
                      >
                        <IconSearch size={12} />
                        <span>AI Deep Scan</span>
                      </button>
                    </td>
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
