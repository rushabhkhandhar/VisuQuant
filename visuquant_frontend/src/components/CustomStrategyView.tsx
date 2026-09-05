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
  IconKey,
  IconDownload,
  IconChevronRight,
} from "./Icons";

interface CustomStrategyViewProps {
  onAnalyzeTicker: (symbol: string) => void;
}

export default function CustomStrategyView({ onAnalyzeTicker }: CustomStrategyViewProps) {
  // 1. Tool & Filter Selections
  const [selectedTools, setSelectedTools] = useState<string[]>([
    "Trendline", "S&R", "Market Structure", "VWAP"
  ]);
  const [selectedFilters, setSelectedFilters] = useState<string[]>([
    "Require RR >= 1:2", "Require High Liquidity (>100k Vol)"
  ]);

  // 2. Risk Management
  const [riskOption, setRiskOption] = useState<string>("ATR 1.5");
  const [customRisk, setCustomRisk] = useState<string>("");

  // 3. AI Prompts & Keys
  const [aiLogicPrompt, setAiLogicPrompt] = useState<string>("");
  const [aiFilterPrompt, setAiFilterPrompt] = useState<string>("");
  const [geminiApiKey, setGeminiApiKey] = useState<string>("");
  const [showKey, setShowKey] = useState<boolean>(false);

  // 4. Execution Config
  const [date, setDate] = useState<string>("");
  const [topN, setTopN] = useState<number>(15);

  // 5. Execution State
  const [loading, setLoading] = useState<boolean>(false);
  const [backtestLoading, setBacktestLoading] = useState<boolean>(false);
  const [results, setResults] = useState<any>(null);
  const [backtestResults, setBacktestResults] = useState<any>(null);
  const [error, setError] = useState<string>("");
  const [streamLogs, setStreamLogs] = useState<{ msg: string; level: string; time: string }[]>([]);
  const [expandedPeerRow, setExpandedPeerRow] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<Record<string, { loading: boolean; url?: string; error?: string }>>({});

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
      id: "golden_cross",
      title: "Golden Cross (50 SMA crosses above 200 SMA)",
      prompt: "Find stocks where the 50-day SMA just crossed above the 200-day SMA (Golden Cross) with 1.5x volume surge.",
    },
    {
      id: "oversold_pullback",
      title: "Oversold Pullback (RSI < 30, Price > 200 SMA)",
      prompt: "Find stocks where the RSI is below 30 (Oversold), but the closing price is still strictly above the 200-day SMA.",
    },
    {
      id: "macd_reversal",
      title: "MACD Bullish Reversal",
      prompt: "Find stocks where the MACD histogram has just crossed above 0, indicating bullish momentum shift.",
    },
    {
      id: "breakout_52w",
      title: "High Volume Breakout (Near 52W High)",
      prompt: "Find stocks where current closing price is within 2% of the 52-week high, and today's volume is at least 150% of the 20-day average volume.",
    },
    {
      id: "dual_avwap",
      title: "Dual AVWAP Momentum Breakout",
      prompt: "Filter stocks trading above both Earnings-Anchored VWAP and Swing High AVWAP with RSI between 55 and 70.",
    },
    {
      id: "vcp",
      title: "Volatility Contraction Pattern (VCP)",
      prompt: "Find stocks with daily ATR decreasing over the last 10 days, breaking out above 20 EMA with 2x volume surge.",
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
    if (selectedTools.length === 0 && !aiLogicPrompt && !aiFilterPrompt) {
      setError("Please select at least one trading tool or provide an AI Custom Logic / Filter prompt.");
      return;
    }

    let finalRisk = riskOption;
    if (riskOption === "Custom") {
      const riskRegex = /^(ATR|PCT)\s+\d+(\.\d+)?$/;
      if (!riskRegex.test(customRisk.trim())) {
        setError("Invalid custom risk format. Must be 'ATR X' or 'PCT Y' (e.g., 'ATR 1.5' or 'PCT 5.0').");
        return;
      }
      finalRisk = customRisk.trim();
    }

    setLoading(true);
    setBacktestLoading(true);
    setError("");
    setResults(null);
    setBacktestResults(null);
    setStreamLogs([]);

    const payload: any = {
      top_n: topN,
      trading_tools: selectedTools,
      trading_filters: selectedFilters,
      risk_management: finalRisk,
    };
    if (date) payload.date = date;
    if (aiLogicPrompt.trim()) {
      payload.ai_logic_prompt = aiLogicPrompt.trim();
      payload.gemini_api_key = geminiApiKey.trim() || null;
    }
    if (aiFilterPrompt.trim()) {
      payload.ai_filter_prompt = aiFilterPrompt.trim();
      payload.gemini_api_key = geminiApiKey.trim() || null;
    }

    // 1. Concurrent Backtest Execution
    fetch("http://localhost:5000/api/backtest_custom_strategy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "success") {
          setBacktestResults(data.data);
        } else {
          console.warn("Custom backtest message:", data.message);
        }
      })
      .catch((err) => {
        console.error("Backtest error:", err);
      })
      .finally(() => {
        setBacktestLoading(false);
      });

    // 2. Screener Streaming Execution
    try {
      const res = await fetch("http://localhost:5000/api/custom_screener_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.body) throw new Error("No response stream received from backend engine.");

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
              console.error("Error parsing stream payload:", err);
            }
          }
        }
      }

      if (buffer.startsWith("data: ")) {
        try {
          const item = JSON.parse(buffer.substring(6));
          if (item.type === "result") setResults(item.data);
        } catch {
          // buffer parse fallback
        }
      }
    } catch (err: any) {
      setError(err.message || "Failed to execute custom strategy screener.");
    } finally {
      setLoading(false);
    }
  };

  const generateReport = async (sym: string) => {
    setAnalysisStatus((prev) => ({ ...prev, [sym]: { loading: true } }));
    try {
      const res = await fetch("http://localhost:5000/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: sym, date: date || undefined }),
      });
      const data = await res.json();
      if (data.status === "success" && data.pdf_url) {
        setAnalysisStatus((prev) => ({ ...prev, [sym]: { loading: false, url: data.pdf_url } }));
      } else {
        setAnalysisStatus((prev) => ({ ...prev, [sym]: { loading: false, error: data.message || "Failed" } }));
      }
    } catch (e: any) {
      setAnalysisStatus((prev) => ({ ...prev, [sym]: { loading: false, error: e.message } }));
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* 1. Builder Workspace */}
      <div className="glass-panel" style={{ padding: "28px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px", marginBottom: "24px" }}>
          <div>
            <h2 style={{ fontSize: "20px", fontWeight: 800, margin: 0 }}>
              Custom Quantitative Strategy Builder
            </h2>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
              Compose proprietary trading rules by combining visual indicators, quantitative filters, and natural language AI logic.
            </div>
          </div>
          <span className="badge badge-purple" style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
            <IconCpu size={13} />
            <span>AI Code Agent Active</span>
          </span>
        </div>

        {/* Section 1: Core Analysis Tools */}
        <div style={{ marginBottom: "22px" }}>
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

        {/* Section 2: Quantitative Filters */}
        <div style={{ marginBottom: "22px" }}>
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

        {/* Section 3: AI Natural Language Filter */}
        <div
          style={{
            marginBottom: "22px",
            padding: "16px 20px",
            background: "var(--bg-surface-elevated)",
            borderRadius: "10px",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
            <IconShield size={14} color="var(--cyan)" />
            <h4 style={{ fontSize: "13px", fontWeight: 700, margin: 0, color: "var(--cyan)" }}>
              3. AI Natural Language Filter (Optional)
            </h4>
          </div>
          <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "10px", lineHeight: 1.4 }}>
            Filter by custom risk parameters in natural language (e.g. <em>&quot;Exclude stocks where Risk &gt; 10% of Entry Price&quot;</em> or <em>&quot;Require Debt to Equity &lt; 0.5&quot;</em>).
          </p>
          <textarea
            className="quant-input font-mono"
            placeholder="Enter natural language filter rules (e.g., 'Only select stocks with ROCE > 20% and ATR < 4%')..."
            value={aiFilterPrompt}
            onChange={(e) => setAiFilterPrompt(e.target.value)}
            rows={2}
            style={{ width: "100%", fontSize: "12px", resize: "vertical" }}
          />
        </div>

        {/* Section 4: Risk Management & Stop-Loss */}
        <div style={{ marginBottom: "22px", display: "flex", gap: "16px", alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>
              Risk Management (Stop Loss Model)
            </label>
            <select
              className="quant-input"
              value={riskOption}
              onChange={(e) => setRiskOption(e.target.value)}
              style={{ width: "210px" }}
            >
              <option value="ATR 1.5">1.5x ATR (Standard)</option>
              <option value="ATR 2.0">2.0x ATR (Wide Swing)</option>
              <option value="ATR 3.0">3.0x ATR (Trend Following)</option>
              <option value="PCT 5.0">5% Fixed Stop Loss</option>
              <option value="PCT 10.0">10% Fixed Stop Loss</option>
              <option value="Custom">Custom SL Format</option>
            </select>
          </div>

          {riskOption === "Custom" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>
                Custom SL Rule (&apos;ATR X&apos; or &apos;PCT Y&apos;)
              </label>
              <input
                type="text"
                className="quant-input font-mono"
                value={customRisk}
                onChange={(e) => setCustomRisk(e.target.value)}
                placeholder="e.g. ATR 1.8 or PCT 6.5"
                style={{ width: "200px" }}
              />
            </div>
          )}
        </div>

        {/* Section 5: AI Custom Strategy Logic */}
        <div
          style={{
            marginBottom: "24px",
            padding: "20px",
            background: "var(--bg-surface-elevated)",
            borderRadius: "10px",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", flexWrap: "wrap", gap: "10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <IconCpu size={16} color="var(--purple)" />
              <h3 style={{ fontSize: "14px", fontWeight: 700, margin: 0, color: "var(--purple)" }}>
                4. AI Custom Strategy Logic
              </h3>
            </div>
            <span className="badge badge-purple">Autonomous Pandas Code Generation</span>
          </div>

          <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "12px" }}>
            Select a predefined quantitative setup or describe your proprietary alpha in plain English. The AI agent generates and executes vector math on the fly.
          </p>

          <div style={{ marginBottom: "12px" }}>
            <select
              className="quant-input"
              style={{ width: "100%", fontSize: "13px" }}
              onChange={(e) => {
                if (e.target.value !== "custom") {
                  setAiLogicPrompt(e.target.value);
                } else {
                  setAiLogicPrompt("");
                }
              }}
            >
              <option value="custom">-- Select a Predefined Strategy (Optional) or Type Below --</option>
              {PREDEFINED_STRATEGIES.map((s) => (
                <option key={s.id} value={s.prompt}>
                  {s.title}
                </option>
              ))}
            </select>
          </div>

          <textarea
            className="quant-input font-mono"
            placeholder="Describe your natural language trading strategy (e.g., 'Select stocks where 20 EMA is above 50 EMA, RSI is crossing above 50, and 5-day delivery volume is 200% above monthly average')..."
            value={aiLogicPrompt}
            onChange={(e) => setAiLogicPrompt(e.target.value)}
            rows={3}
            style={{ width: "100%", fontSize: "13px", resize: "vertical", marginBottom: "16px" }}
          />

          {/* Gemini API Key Section */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "8px",
              paddingTop: "14px",
              borderTop: "1px solid var(--border-subtle)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <IconKey size={14} color={geminiApiKey ? "var(--emerald)" : "var(--text-muted)"} />
                <label style={{ fontSize: "12px", fontWeight: 700, color: "var(--text-primary)" }}>
                  Gemini API Key (Optional Override)
                </label>
              </div>
              <span className={`badge ${geminiApiKey ? "badge-bullish" : "badge-cyan"}`} style={{ fontSize: "10px" }}>
                {geminiApiKey ? "Using Gemini Cloud API" : "Default: Local Ollama (qwen2.5vl:7b)"}
              </span>
            </div>

            <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
              <div style={{ position: "relative", flex: 1, minWidth: "260px" }}>
                <input
                  type={showKey ? "text" : "password"}
                  className="quant-input font-mono"
                  placeholder="Paste your Gemini API Key (e.g. AIzaSy...)"
                  value={geminiApiKey}
                  onChange={(e) => setGeminiApiKey(e.target.value)}
                  style={{ paddingRight: "70px", fontSize: "12px" }}
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  style={{
                    position: "absolute",
                    right: "10px",
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    color: "var(--text-muted)",
                    fontSize: "11px",
                    cursor: "pointer",
                    fontWeight: 600,
                  }}
                >
                  {showKey ? "HIDE" : "SHOW"}
                </button>
              </div>
              <span style={{ fontSize: "11px", color: "var(--text-secondary)", flex: 2, minWidth: "240px", lineHeight: 1.4 }}>
                *Leave blank to fallback to your local Ollama (<code>qwen2.5vl:7b</code>) model for 100% free and offline execution.
              </span>
            </div>
          </div>
        </div>

        {/* Section 6: Execution Controls Bar */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "16px",
            paddingTop: "16px",
            borderTop: "1px solid var(--border-subtle)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>As-Of Date:</label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="quant-input font-mono"
                style={{ width: "150px", padding: "6px 10px", fontSize: "12px" }}
              />
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>Top Setups:</label>
              <select
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value))}
                className="quant-input"
                style={{ width: "100px", padding: "6px 10px", fontSize: "12px" }}
              >
                <option value={5}>Top 5</option>
                <option value={10}>Top 10</option>
                <option value={15}>Top 15</option>
                <option value={20}>Top 20</option>
              </select>
            </div>
          </div>

          <button
            onClick={runCustomScreen}
            disabled={loading || backtestLoading}
            className="btn btn-purple"
            style={{ padding: "12px 30px", fontSize: "14px" }}
          >
            {loading || backtestLoading ? (
              <>
                <span className="loader" style={{ width: "14px", height: "14px" }} />
                <span>Scanning &amp; Backtesting...</span>
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

      {/* 4. Concurrent Backtest Forensics Card */}
      {backtestResults && backtestResults.metrics && (
        <div className="glass-panel" style={{ padding: "24px 28px", borderTop: "4px solid var(--purple)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "18px", flexWrap: "wrap", gap: "12px" }}>
            <div>
              <h3 style={{ fontSize: "18px", fontWeight: 800, margin: 0 }}>
                Historical Backtest Performance (Custom Strategy Ruleset)
              </h3>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
                Simulated trade metrics over historical regime data with dynamic stop-loss.
              </div>
            </div>
            <span className="badge badge-purple">Walk-Forward Simulation</span>
          </div>

          <div className="grid-cols-4" style={{ gap: "12px", marginBottom: "20px" }}>
            <div className="stat-card" style={{ padding: "14px 18px" }}>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>WIN RATE</div>
              <div
                className="font-mono"
                style={{
                  fontSize: "22px",
                  fontWeight: 800,
                  color: Number(backtestResults.metrics["Win Rate (%)"]) >= 50 ? "var(--emerald)" : "var(--crimson)",
                  marginTop: "4px",
                }}
              >
                {backtestResults.metrics["Win Rate (%)"]}%
              </div>
            </div>

            <div className="stat-card" style={{ padding: "14px 18px" }}>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>TOTAL TRADES</div>
              <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--cyan)", marginTop: "4px" }}>
                {backtestResults.metrics["Total Trades"]}
              </div>
            </div>

            <div className="stat-card" style={{ padding: "14px 18px" }}>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>AVG WIN / LOSS</div>
              <div className="font-mono" style={{ fontSize: "18px", fontWeight: 800, marginTop: "6px" }}>
                <span style={{ color: "var(--emerald)" }}>+{backtestResults.metrics["Average Win (%)"]}%</span>
                <span style={{ color: "var(--text-dim)", margin: "0 4px" }}>/</span>
                <span style={{ color: "var(--crimson)" }}>{backtestResults.metrics["Average Loss (%)"]}%</span>
              </div>
            </div>

            <div className="stat-card" style={{ padding: "14px 18px" }}>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>MAX DRAWDOWN</div>
              <div className="font-mono" style={{ fontSize: "22px", fontWeight: 800, color: "var(--crimson)", marginTop: "4px" }}>
                {backtestResults.metrics["Max Drawdown (%)"]}%
              </div>
            </div>
          </div>

          {/* Trade History Table */}
          {backtestResults.trades && backtestResults.trades.length > 0 && (
            <div>
              <h4 style={{ fontSize: "13px", fontWeight: 700, marginBottom: "10px", color: "var(--text-primary)" }}>
                Simulated Trade Ledger ({backtestResults.trades.length} Closed Trades)
              </h4>
              <div style={{ maxHeight: "240px", overflowY: "auto", border: "1px solid var(--border-subtle)", borderRadius: "8px" }}>
                <table className="terminal-table" style={{ fontSize: "12px" }}>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Entry Date</th>
                      <th>Exit Date</th>
                      <th>Entry Price</th>
                      <th>Exit Price</th>
                      <th style={{ textAlign: "right" }}>Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtestResults.trades.map((t: any, idx: number) => {
                      const ret = Number(t.return || 0);
                      const isPos = ret > 0;
                      return (
                        <tr key={idx}>
                          <td style={{ fontWeight: 800, color: "var(--cyan)", fontFamily: "'JetBrains Mono', monospace" }}>
                            {t.symbol}
                          </td>
                          <td className="font-mono" style={{ color: "var(--text-secondary)" }}>{t.entry_date}</td>
                          <td className="font-mono" style={{ color: "var(--text-secondary)" }}>{t.exit_date}</td>
                          <td className="font-mono">₹{Number(t.entry_price || 0).toFixed(2)}</td>
                          <td className="font-mono">₹{Number(t.exit_price || 0).toFixed(2)}</td>
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
          )}
        </div>
      )}

      {/* 5. Screened Candidates Results Table */}
      {results && results.candidates && results.candidates.length > 0 && (
        <div className="glass-panel" style={{ padding: "20px 24px", overflowX: "auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <h3 style={{ fontSize: "18px", fontWeight: 800, margin: 0 }}>
                Custom Screen Qualified Candidates ({results.candidates.length} Stocks Identified)
              </h3>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "3px" }}>
                Ranked by institutional composite score and user-defined tool/filter clearance.
              </div>
            </div>
          </div>

          <table className="terminal-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Score</th>
                <th>Trigger</th>
                <th>Entry</th>
                <th>Target</th>
                <th>Stop Loss</th>
                <th>Trend Status</th>
                <th>5Y Win Rate</th>
                <th>5Y CAGR</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {results.candidates.map((c: any, idx: number) => {
                const sym = c.symbol || c.ticker;
                const status = analysisStatus[sym];
                const isPeersOpen = expandedPeerRow === sym;
                const winRate = c.metrics?.backtest?.["Win Rate (%)"];
                const cagr = c.metrics?.backtest?.["CAGR (%)"];

                return (
                  <React.Fragment key={idx}>
                    <tr>
                      <td style={{ fontWeight: 800, color: "var(--cyan)", fontFamily: "'JetBrains Mono', monospace" }}>
                        {sym}
                      </td>
                      <td className="font-mono" style={{ color: "var(--purple)", fontWeight: 700 }}>
                        {c.score !== undefined ? Number(c.score).toFixed(1) : "-"}
                      </td>
                      <td style={{ fontSize: "12px" }}>{c.trigger_type || "Custom Setup"}</td>
                      <td className="font-mono">₹{Number(c.entry_price || c.close || 0).toFixed(2)}</td>
                      <td className="font-mono" style={{ color: "var(--emerald)", fontWeight: 700 }}>
                        ₹{Number(c.target || 0).toFixed(2)}
                      </td>
                      <td className="font-mono" style={{ color: "var(--crimson)", fontWeight: 700 }}>
                        ₹{Number(c.stop_loss || 0).toFixed(2)}
                      </td>
                      <td>
                        <span className="badge badge-bullish" style={{ fontSize: "10px" }}>
                          {c.trend_status || (c.metrics?.trend_up_days ? `${c.metrics.trend_up_days}D UP` : "BULLISH")}
                        </span>
                      </td>
                      <td
                        className="font-mono"
                        style={{
                          color: winRate && winRate >= 50 ? "var(--emerald)" : "var(--text-secondary)",
                          fontWeight: 600,
                        }}
                      >
                        {winRate !== undefined ? `${winRate}%` : "-"}
                      </td>
                      <td
                        className="font-mono"
                        style={{
                          color: cagr && cagr > 0 ? "var(--emerald)" : "var(--crimson)",
                          fontWeight: 600,
                        }}
                      >
                        {cagr !== undefined ? `${cagr}%` : "-"}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: "6px" }}>
                          {status?.url ? (
                            <a
                              href={status.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn btn-cyan"
                              style={{ padding: "5px 10px", fontSize: "11px" }}
                            >
                              <IconDownload size={12} />
                              <span>PDF Report</span>
                            </a>
                          ) : (
                            <button
                              onClick={() => generateReport(sym)}
                              disabled={status?.loading}
                              className="btn btn-purple"
                              style={{ padding: "5px 10px", fontSize: "11px" }}
                            >
                              {status?.loading ? (
                                <span className="loader" style={{ width: "12px", height: "12px" }} />
                              ) : (
                                <>
                                  <IconSearch size={12} />
                                  <span>Deep Dive</span>
                                </>
                              )}
                            </button>
                          )}

                          {c.peers && c.peers.length > 0 && (
                            <button
                              onClick={() => setExpandedPeerRow(isPeersOpen ? null : sym)}
                              className="btn btn-glass"
                              style={{ padding: "5px 10px", fontSize: "11px" }}
                            >
                              <span>{isPeersOpen ? "Hide" : `Peers (${c.peers.length})`}</span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>

                    {/* Peer Comparative Row */}
                    {isPeersOpen && c.peers && c.peers.length > 0 && (
                      <tr>
                        <td colSpan={10} style={{ background: "var(--bg-surface-elevated)", padding: "16px 20px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                            <span style={{ fontWeight: 700, color: "var(--cyan)", fontSize: "13px" }}>
                              Peer Candidates for {sym} (Comparative Relative Strength)
                            </span>
                            <span className="badge badge-cyan">Sector Benchmarked</span>
                          </div>
                          <table className="terminal-table" style={{ fontSize: "12px" }}>
                            <thead>
                              <tr>
                                <th>Peer Symbol</th>
                                <th>Score</th>
                                <th>Trigger</th>
                                <th>Entry</th>
                                <th>Target</th>
                                <th>Stop Loss</th>
                                <th style={{ textAlign: "right" }}>Analyze</th>
                              </tr>
                            </thead>
                            <tbody>
                              {c.peers.map((peer: any, pIdx: number) => (
                                <tr key={pIdx}>
                                  <td style={{ fontWeight: 700, color: "var(--text-primary)" }}>{peer.symbol}</td>
                                  <td className="font-mono" style={{ color: "var(--purple)" }}>
                                    {peer.score !== undefined ? Number(peer.score).toFixed(1) : "-"}
                                  </td>
                                  <td>{peer.trigger_type || "Peer Setup"}</td>
                                  <td className="font-mono">₹{Number(peer.entry_price || 0).toFixed(2)}</td>
                                  <td className="font-mono" style={{ color: "var(--emerald)" }}>
                                    ₹{Number(peer.target || 0).toFixed(2)}
                                  </td>
                                  <td className="font-mono" style={{ color: "var(--crimson)" }}>
                                    ₹{Number(peer.stop_loss || 0).toFixed(2)}
                                  </td>
                                  <td style={{ textAlign: "right" }}>
                                    <button
                                      onClick={() => onAnalyzeTicker(peer.symbol)}
                                      className="btn btn-glass"
                                      style={{ padding: "4px 8px", fontSize: "10px" }}
                                    >
                                      Vision Scan
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
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
