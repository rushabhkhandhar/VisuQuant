"use client";

import React, { useState } from "react";

export default function Home() {
  const [date, setDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState("");
  const [streamLogs, setStreamLogs] = useState<string[]>([]);
  const [expandedPeerRow, setExpandedPeerRow] = useState<number | null>(null);
  
  // Custom Screener State
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [selectedFilters, setSelectedFilters] = useState<string[]>([]);
  const [customLoading, setCustomLoading] = useState(false);
  const [customError, setCustomError] = useState("");
  const [riskOption, setRiskOption] = useState("ATR 1.5");
  const [customRisk, setCustomRisk] = useState("");
  const [aiLogicPrompt, setAiLogicPrompt] = useState("");
  const [aiFilterPrompt, setAiFilterPrompt] = useState("");
  const [geminiApiKey, setGeminiApiKey] = useState("");
  
  const AVAILABLE_TOOLS = [
    "Trendline", "S&R", "Market Structure", "Chart Patterns", 
    "Candle stick patterns", "VWAP", "Moving Avg", "RSI", "MACD"
  ];
  const AVAILABLE_FILTERS = [
    "Require RR >= 1:2", "Exclude Flat VWAP", 
    "Require High Liquidity (>100k Vol)", "Exclude High Volatility (ATR > 5%)"
  ];
  // Direct Analysis State
  const [directTicker, setDirectTicker] = useState("");
  const [directLoading, setDirectLoading] = useState(false);
  const [directError, setDirectError] = useState("");
  const [directPdfUrl, setDirectPdfUrl] = useState("");
  
  // Backtest State
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestResults, setBacktestResults] = useState<any>(null);
  const [backtestError, setBacktestError] = useState("");
  
  // Table Analysis State
  const [analysisStatus, setAnalysisStatus] = useState<Record<string, {loading: boolean, url?: string, error?: string}>>({});

  const toggleTool = (tool: string) => {
    if (selectedTools.includes(tool)) {
      setSelectedTools(selectedTools.filter(t => t !== tool));
    } else {
      setSelectedTools([...selectedTools, tool]);
    }
  };

  const toggleFilter = (filter: string) => {
    if (selectedFilters.includes(filter)) {
      setSelectedFilters(selectedFilters.filter(f => f !== filter));
    } else {
      setSelectedFilters([...selectedFilters, filter]);
    }
  };

  const runCustomScreener = async () => {
    if (selectedTools.length === 0 && !aiLogicPrompt) {
      setCustomError("Please select at least one trading tool or provide an AI Custom Logic prompt.");
      return;
    }
    let finalRisk = riskOption;
    if (riskOption === "Custom") {
      const riskRegex = /^(ATR|PCT)\s+\d+(\.\d+)?$/;
      if (!riskRegex.test(customRisk)) {
        setCustomError("Invalid custom risk format. Must be 'ATR X' or 'PCT Y' (e.g., 'ATR 1.5' or 'PCT 5.0').");
        return;
      }
      finalRisk = customRisk;
    }

    setCustomLoading(true);
    setCustomError("");
    setResults(null);
    setStreamLogs([]);
    
    try {
      const payload: any = { top_n: 20, trading_tools: selectedTools, trading_filters: selectedFilters, risk_management: finalRisk };
      if (date) payload.date = date;
      if (aiLogicPrompt) {
        payload.ai_logic_prompt = aiLogicPrompt;
        payload.gemini_api_key = geminiApiKey || null;
      }
      if (aiFilterPrompt) {
        payload.ai_filter_prompt = aiFilterPrompt;
        payload.gemini_api_key = geminiApiKey || null;
      }
      
      const res = await fetch("http://localhost:5000/api/custom_screener_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        throw new Error("Failed to fetch data from custom engine");
      }
      
      if (!res.body) throw new Error("ReadableStream not supported in this browser.");
      
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      
      let done = false;
      let buffer = "";
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";
          
          for (const part of parts) {
            const dataPrefix = "data: ";
            if (part.startsWith(dataPrefix)) {
              try {
                const dataStr = part.substring(dataPrefix.length).trim();
                if (!dataStr) continue;
                const data = JSON.parse(dataStr);
                if (data.type === 'log') {
                  setStreamLogs(prev => [...prev, data.message]);
                } else if (data.type === 'result') {
                  setResults(data.data);
                } else if (data.type === 'error') {
                  setCustomError(data.message);
                }
              } catch (e) {
                console.error("Error parsing SSE JSON:", e, part);
              }
            }
          }
        }
      }
    } catch (err: any) {
      setCustomError(err.message || "An error occurred");
    } finally {
      setCustomLoading(false);
    }
  };

  const runScreener = async () => {
    setLoading(true);
    setError("");
    setResults(null);
    setStreamLogs([]);
    
    try {
      const payload = date ? { date, top_n: 5 } : { top_n: 5 };
      const res = await fetch("http://localhost:5000/api/screener_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        throw new Error("Failed to fetch data from engine");
      }
      
      if (!res.body) throw new Error("ReadableStream not supported in this browser.");
      
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      
      let done = false;
      let buffer = "";
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() || ""; // keep the last incomplete chunk in the buffer
          
          for (const part of parts) {
            const dataPrefix = "data: ";
            if (part.startsWith(dataPrefix)) {
              try {
                const dataStr = part.substring(dataPrefix.length).trim();
                if (!dataStr) continue;
                const data = JSON.parse(dataStr);
                if (data.type === 'log') {
                  setStreamLogs(prev => [...prev, data.message]);
                } else if (data.type === 'result') {
                  setResults(data.data);
                } else if (data.type === 'error') {
                  setError(data.message);
                }
              } catch (e) {
                console.error("Error parsing SSE JSON:", e, part);
              }
            }
          }
        }
      }
      
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const generateReport = async (symbol: string, isDirect: boolean = false) => {
    if (isDirect) {
      setDirectLoading(true);
      setDirectError("");
      setDirectPdfUrl("");
    } else {
      setAnalysisStatus(prev => ({...prev, [symbol]: { loading: true }}));
    }
    
    try {
      const res = await fetch("http://localhost:5000/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, date: isDirect ? null : (date || null) })
      });
      
      const data = await res.json();
      if (!res.ok || data.status === "error") {
        throw new Error(data.message || "Failed to generate report");
      }
      
      if (isDirect) {
        setDirectPdfUrl(data.pdf_url);
      } else {
        setAnalysisStatus(prev => ({...prev, [symbol]: { loading: false, url: data.pdf_url }}));
      }
    } catch (err: any) {
      if (isDirect) {
        setDirectError(err.message || "An error occurred");
      } else {
        setAnalysisStatus(prev => ({...prev, [symbol]: { loading: false, error: err.message || "Error" }}));
      }
    } finally {
      if (isDirect) {
        setDirectLoading(false);
      }
    }
  };

  const runBacktest = async (symbol: string) => {
    setBacktestLoading(true);
    setBacktestError("");
    setBacktestResults(null);
    
    try {
      const res = await fetch("http://localhost:5000/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, months: 60 })
      });
      
      const data = await res.json();
      if (!res.ok || data.status === "error") {
        throw new Error(data.message || "Failed to run backtest");
      }
      
      setBacktestResults(data.data);
    } catch (err: any) {
      setBacktestError(err.message || "An error occurred during backtesting");
    } finally {
      setBacktestLoading(false);
    }
  };

  return (
    <div className="page-container">
      <div className="flex-between mb-4">
        <div>
          <h1 className="gradient-text" style={{ fontSize: '32px', margin: '0 0 8px 0' }}>VisuQuant Engine</h1>
          <p className="text-secondary" style={{ margin: 0 }}>Algorithmic Trend Screener & Regime Analysis</p>
        </div>
        
        {results?.regime && (
          <div className={`badge ${results.regime.includes('UP') ? 'badge-bullish' : results.regime.includes('DOWN') ? 'badge-bearish' : ''}`}>
            REGIME: {results.regime}
          </div>
        )}
      </div>

      <div className="glass-panel mb-4">
        <h2 style={{ margin: '0 0 16px 0', fontSize: '20px' }}>Control Panel</h2>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
          {/* Screener Section */}
          <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '16px', color: 'var(--accent-cyan)' }}>1. Quantitative Screener</h3>
            <div className="flex gap-4">
              <input 
                type="date" 
                className="input-glass"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                placeholder="YYYY-MM-DD"
                style={{ flex: 1 }}
              />
              <button 
                className="btn-primary" 
                onClick={runScreener}
                disabled={loading}
              >
                {loading ? <span className="loader"></span> : '▶'} {loading ? 'Scanning...' : 'Run Screener'}
              </button>
            </div>
            {error && <p className="text-danger mt-4" style={{ fontSize: '14px' }}>{error}</p>}
          </div>

          {/* Direct Analysis Section */}
          <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '16px', color: 'var(--success)' }}>2. Direct Ticker Analysis</h3>
            <div className="flex gap-4">
              <input 
                type="text" 
                className="input-glass"
                value={directTicker}
                onChange={(e) => {
                  setDirectTicker(e.target.value.toUpperCase());
                  setDirectPdfUrl("");
                  setBacktestResults(null);
                }}
                placeholder="e.g. RELIANCE"
                style={{ flex: 1 }}
              />
              
              {directPdfUrl ? (
                <a 
                  href={directPdfUrl} 
                  download 
                  target="_blank" 
                  rel="noreferrer" 
                  className="btn-primary flex-center"
                  style={{ borderColor: 'var(--success)', color: 'var(--success)', boxShadow: '0 0 10px rgba(0, 255, 136, 0.4)', background: 'rgba(0, 255, 136, 0.1)', textDecoration: 'none' }}
                >
                  ⬇️ Download PDF
                </a>
              ) : (
                <button 
                  className="btn-primary" 
                  onClick={() => generateReport(directTicker, true)}
                  disabled={directLoading || !directTicker}
                  style={{ borderColor: 'var(--success)', color: 'var(--success)', boxShadow: '0 0 10px rgba(0, 255, 136, 0.2)' }}
                >
                  {directLoading ? <span className="loader" style={{ borderTopColor: 'var(--success)' }}></span> : '⚡'} {directLoading ? 'Analyzing...' : 'Generate PDF'}
                </button>
              )}
              
              <button 
                className="btn-primary" 
                onClick={() => runBacktest(directTicker)}
                disabled={backtestLoading || !directTicker}
                style={{ borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)', boxShadow: '0 0 10px rgba(0, 238, 255, 0.2)' }}
              >
                {backtestLoading ? <span className="loader" style={{ borderTopColor: 'var(--accent-cyan)' }}></span> : '📊'} {backtestLoading ? 'Running...' : 'Run Backtest (5y)'}
              </button>
            </div>
            {directError && <p className="text-danger mt-4" style={{ fontSize: '14px' }}>{directError}</p>}
            {backtestError && <p className="text-danger mt-4" style={{ fontSize: '14px' }}>{backtestError}</p>}
          </div>
        </div>

        {/* Custom Strategy Builder Section */}
        <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '16px', color: '#c084fc' }}>3. Custom Strategy Builder</h3>
          <p className="text-secondary" style={{ fontSize: '14px', marginBottom: '16px' }}>Select multiple trading tools to construct a custom scan (stocks must pass all selected tools).</p>
          
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '16px' }}>
            {AVAILABLE_TOOLS.map(tool => (
              <button
                key={tool}
                onClick={() => toggleTool(tool)}
                style={{
                  padding: '8px 16px',
                  borderRadius: '20px',
                  border: `1px solid ${selectedTools.includes(tool) ? '#c084fc' : 'rgba(255,255,255,0.1)'}`,
                  background: selectedTools.includes(tool) ? 'rgba(192,132,252,0.15)' : 'transparent',
                  color: selectedTools.includes(tool) ? '#c084fc' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  fontSize: '13px',
                  fontWeight: selectedTools.includes(tool) ? 600 : 400,
                }}
              >
                {tool}
              </button>
            ))}
          </div>

          <h3 style={{ fontSize: '14px', margin: '0 0 12px 0', color: '#60a5fa' }}>🛡️ Trading Filters</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '24px' }}>
            {AVAILABLE_FILTERS.map((filter) => (
              <button 
                key={filter}
                onClick={() => toggleFilter(filter)}
                style={{
                  padding: '8px 16px',
                  borderRadius: '20px',
                  border: `1px solid ${selectedFilters.includes(filter) ? '#60a5fa' : 'rgba(255,255,255,0.1)'}`,
                  background: selectedFilters.includes(filter) ? 'rgba(96,165,250,0.15)' : 'transparent',
                  color: selectedFilters.includes(filter) ? '#60a5fa' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  fontSize: '13px',
                  fontWeight: selectedFilters.includes(filter) ? 600 : 400,
                }}
              >
                {filter}
              </button>
            ))}
          </div>
          
          <div style={{ marginBottom: '16px', padding: '16px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px dashed rgba(255,255,255,0.1)' }}>
            <h4 style={{ fontSize: '13px', margin: '0 0 8px 0', color: '#c084fc' }}>🤖 AI Custom Filter</h4>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
              Want to filter by custom risk parameters? (e.g. <i>"Exclude stocks where Risk {">"} 10% of Entry Price"</i>).
            </p>
            <textarea 
              className="input-glass"
              placeholder="Enter natural language filter rules..."
              value={aiFilterPrompt}
              onChange={(e) => setAiFilterPrompt(e.target.value)}
              style={{ width: '100%', minHeight: '60px', padding: '10px', fontSize: '12px' }}
            />
          </div>

          <div style={{ marginBottom: '16px', display: 'flex', gap: '16px', alignItems: 'center' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Risk Management (Stop Loss)</label>
              <select 
                className="input-glass" 
                value={riskOption} 
                onChange={(e) => setRiskOption(e.target.value)}
                style={{ width: '200px', padding: '8px' }}
              >
                <option value="ATR 1.5">1.5x ATR</option>
                <option value="ATR 2.0">2.0x ATR</option>
                <option value="ATR 3.0">3.0x ATR</option>
                <option value="PCT 5.0">5% Fixed SL</option>
                <option value="PCT 10.0">10% Fixed SL</option>
                <option value="Custom">Custom</option>
              </select>
            </div>
            
            {riskOption === "Custom" && (
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Custom SL Format</label>
                <input 
                  type="text" 
                  className="input-glass"
                  value={customRisk}
                  onChange={(e) => setCustomRisk(e.target.value)}
                  placeholder="e.g., ATR 1.5 or PCT 5.0"
                  style={{ width: '200px', padding: '8px' }}
                />
              </div>
            )}
          </div>
          
          {/* AI Custom Logic Section */}
          <div style={{ marginBottom: '24px', padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <h3 style={{ fontSize: '14px', margin: '0 0 12px 0', color: '#c084fc' }}>✨ AI Custom Logic</h3>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                Select a predefined strategy or describe your own in plain English. Our AI agent will write and execute the Pandas logic on the fly!
            </p>
            
            <select 
                className="input-glass"
                style={{ width: '100%', padding: '8px', marginBottom: '12px', fontSize: '13px' }}
                onChange={(e) => {
                    if (e.target.value !== "custom") {
                        setAiLogicPrompt(e.target.value);
                    }
                }}
            >
                <option value="custom">-- Select a Predefined Strategy (Optional) --</option>
                <option value="Find stocks where the 50-day SMA just crossed above the 200-day SMA (Golden Cross).">Golden Cross (50 SMA crosses above 200 SMA)</option>
                <option value="Find stocks where the RSI is below 30 (Oversold), but the closing price is still strictly above the 200-day SMA.">Oversold Pullback (RSI {"<"} 30, Price {">"} 200 SMA)</option>
                <option value="Find stocks where the MACD histogram has just crossed above 0, indicating bullish momentum shift.">MACD Bullish Reversal</option>
                <option value="Find stocks where the current closing price is within 2% of the 52-week high, and today's volume is at least 150% of the 20-day average volume.">High Volume Breakout (Near 52W High)</option>
            </select>
            
            <textarea 
              className="input-glass"
              placeholder="Enter natural language strategy..."
              value={aiLogicPrompt}
              onChange={(e) => setAiLogicPrompt(e.target.value)}
              style={{ width: '100%', minHeight: '80px', padding: '12px', marginBottom: '12px', fontSize: '13px' }}
            />
            <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <input 
                    type="password"
                    className="input-glass"
                    placeholder="Enter Gemini API Key..."
                    value={geminiApiKey}
                    onChange={(e) => setGeminiApiKey(e.target.value)}
                    style={{ width: '300px', padding: '8px', fontSize: '13px' }}
                />
                <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>*Leave blank to fallback to your local Ollama (Qwen) model for free execution.</span>
            </div>
          </div>

          <div className="flex gap-4">
            <button 
              className="btn-primary" 
              onClick={runCustomScreener}
              disabled={customLoading}
              style={{ borderColor: '#c084fc', color: '#c084fc', boxShadow: '0 0 10px rgba(192, 132, 252, 0.2)' }}
            >
              {customLoading ? <span className="loader" style={{ borderTopColor: '#c084fc' }}></span> : '🛠️'} {customLoading ? 'Scanning...' : 'Run Custom Strategy'}
            </button>
          </div>
          {customError && <p className="text-danger mt-4" style={{ fontSize: '14px' }}>{customError}</p>}
        </div>
      </div>

      {backtestResults && (
        <div className="glass-panel mb-4" style={{ borderTop: '4px solid var(--accent-cyan)' }}>
          <div className="flex-between mb-4">
            <h2 style={{ margin: 0, fontSize: '20px' }}>
              Historical Performance <span style={{ color: 'var(--text-secondary)' }}>({backtestResults.symbol} | {backtestResults.period})</span>
            </h2>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '24px' }}>
            <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
              <p style={{ margin: '0 0 8px 0', fontSize: '12px', color: 'var(--text-secondary)' }}>WIN RATE</p>
              <h3 style={{ margin: 0, fontSize: '24px', color: backtestResults.metrics['Win Rate (%)'] > 50 ? 'var(--success)' : 'var(--text-primary)' }}>{backtestResults.metrics['Win Rate (%)']}%</h3>
            </div>
            <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
              <p style={{ margin: '0 0 8px 0', fontSize: '12px', color: 'var(--text-secondary)' }}>CAGR</p>
              <h3 style={{ margin: 0, fontSize: '24px', color: backtestResults.metrics['CAGR (%)'] > 0 ? 'var(--success)' : 'var(--danger)' }}>{backtestResults.metrics['CAGR (%)']}%</h3>
            </div>
            <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
              <p style={{ margin: '0 0 8px 0', fontSize: '12px', color: 'var(--text-secondary)' }}>SHARPE RATIO</p>
              <h3 style={{ margin: 0, fontSize: '24px', color: backtestResults.metrics['Sharpe Ratio'] > 1 ? 'var(--accent-cyan)' : 'var(--text-primary)' }}>{backtestResults.metrics['Sharpe Ratio']}</h3>
            </div>
            <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
              <p style={{ margin: '0 0 8px 0', fontSize: '12px', color: 'var(--text-secondary)' }}>MAX DRAWDOWN</p>
              <h3 style={{ margin: 0, fontSize: '24px', color: 'var(--danger)' }}>{backtestResults.metrics['Max Drawdown (%)']}%</h3>
            </div>
            <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
              <p style={{ margin: '0 0 8px 0', fontSize: '12px', color: 'var(--text-secondary)' }}>TOTAL TRADES</p>
              <h3 style={{ margin: 0, fontSize: '24px', color: 'var(--text-primary)' }}>{backtestResults.metrics['Total Trades']}</h3>
            </div>
            <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
              <p style={{ margin: '0 0 8px 0', fontSize: '12px', color: 'var(--text-secondary)' }}>AVG WIN / LOSS</p>
              <h3 style={{ margin: 0, fontSize: '24px', color: 'var(--text-primary)' }}><span style={{ color: 'var(--success)' }}>+{backtestResults.metrics['Average Win (%)']}%</span> <span style={{ fontSize: '16px', opacity: 0.5 }}>/</span> <span style={{ color: 'var(--danger)' }}>{backtestResults.metrics['Average Loss (%)']}%</span></h3>
            </div>
          </div>
          
          <h3 style={{ margin: '0 0 16px 0', fontSize: '16px' }}>Simulated Trade History (Dynamic 20 SMA Exit)</h3>
          {backtestResults.trades && backtestResults.trades.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Entry Date</th>
                    <th>Exit Date</th>
                    <th>Entry Price</th>
                    <th>Exit Price</th>
                    <th style={{ textAlign: 'right' }}>Net Return</th>
                  </tr>
                </thead>
                <tbody>
                  {backtestResults.trades.map((t: any, idx: number) => (
                    <tr key={idx}>
                      <td className="text-secondary">{t.entry_date}</td>
                      <td className="text-secondary">{t.exit_date}</td>
                      <td>₹{t.entry_price.toFixed(2)}</td>
                      <td>₹{t.exit_price.toFixed(2)}</td>
                      <td style={{ textAlign: 'right', fontWeight: 600, color: t.return > 0 ? 'var(--success)' : 'var(--danger)' }}>
                        {t.return > 0 ? '+' : ''}{t.return.toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-secondary">No trades generated for this strategy during the 5-year period.</p>
          )}
        </div>
      )}

      {streamLogs.length > 0 && !results && (
        <div className="glass-panel mb-4" style={{ backgroundColor: '#0f172a', border: '1px solid #334155' }}>
          <h2 style={{ margin: '0 0 12px 0', fontSize: '16px', color: '#38bdf8' }}>Live Engine Progress</h2>
          <div style={{ 
            maxHeight: '300px', 
            overflowY: 'auto', 
            fontFamily: 'monospace', 
            fontSize: '13px', 
            color: '#94a3b8',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px'
          }}>
            {streamLogs.map((log, i) => (
              <div key={i}>
                 <span style={{color: '#64748b'}}>[{new Date().toLocaleTimeString()}]</span> {log}
              </div>
            ))}
          </div>
        </div>
      )}

      {results && (
        <div className="glass-panel">
          <h2 style={{ margin: '0 0 16px 0', fontSize: '20px' }}>Candidates ({(results.candidates || []).length})</h2>
          
          {results.candidates && results.candidates.length > 0 ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Composite Score</th>
                  <th>Trigger</th>
                  <th>Entry</th>
                  <th>Target</th>
                  <th>Stop Loss</th>
                  <th>Trend Status</th>
                  <th>5Y Win Rate</th>
                  <th>5Y CAGR</th>
                  <th style={{ textAlign: 'center' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {results.candidates.map((c: any, idx: number) => {
                  const status = analysisStatus[c.symbol];
                  
                  return (
                    <React.Fragment key={idx}>
                      <tr>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{c.symbol}</td>
                      <td className="text-cyan">{c.score !== undefined ? c.score.toFixed(1) : '-'}</td>
                      <td>{c.trigger_type}</td>
                      <td>₹{c.entry_price || '-'}</td>
                      <td className="text-cyan">₹{c.target || '-'}</td>
                      <td className="text-danger">₹{c.stop_loss || '-'}</td>
                      <td className="text-success">{c.trend_status || (c.metrics?.trend_up_days ? `${c.metrics.trend_up_days} Days UP` : '-')}</td>
                      <td style={{ color: c.metrics?.backtest?.['Win Rate (%)'] >= 50 ? 'var(--success)' : 'var(--text-secondary)' }}>
                        {c.metrics?.backtest?.['Win Rate (%)'] !== undefined ? `${c.metrics.backtest['Win Rate (%)']}%` : '-'}
                      </td>
                      <td style={{ color: c.metrics?.backtest?.['CAGR (%)'] > 0 ? 'var(--success)' : 'var(--danger)' }}>
                        {c.metrics?.backtest?.['CAGR (%)'] !== undefined ? `${c.metrics.backtest['CAGR (%)']}%` : '-'}
                      </td>
                      <td style={{ textAlign: 'center', display: 'flex', gap: '8px', justifyContent: 'center' }}>
                        {status?.url ? (
                          <a href={status.url} download target="_blank" rel="noreferrer" style={{ color: 'var(--success)', textDecoration: 'none', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                            ⬇️ Download PDF
                          </a>
                        ) : status?.error ? (
                          <span className="text-danger" style={{ fontSize: '14px' }}>{status.error}</span>
                        ) : (
                          <button 
                            className="btn-primary" 
                            style={{ padding: '6px 12px', fontSize: '13px', margin: '0 auto' }}
                            onClick={() => generateReport(c.symbol)}
                            disabled={status?.loading}
                          >
                            {status?.loading ? <span className="loader" style={{ width: '14px', height: '14px', borderWidth: '2px' }}></span> : '⚡ Deep Dive'}
                          </button>
                        )}
                        {c.peers && c.peers.length > 0 && (
                          <button 
                            className="btn-secondary" 
                            style={{ padding: '6px 12px', fontSize: '13px', backgroundColor: '#334155', border: 'none', color: '#fff' }}
                            onClick={() => setExpandedPeerRow(expandedPeerRow === idx ? null : idx)}
                          >
                            {expandedPeerRow === idx ? "Hide Peers" : `Peers (${c.peers.length})`}
                          </button>
                        )}
                      </td>
                    </tr>
                    {expandedPeerRow === idx && c.peers && c.peers.length > 0 && (
                      <tr key={`peers-${idx}`} style={{ backgroundColor: '#0f172a' }}>
                        <td colSpan={10} style={{ padding: '20px' }}>
                          <h4 style={{ margin: '0 0 12px 0', color: '#38bdf8', fontSize: '14px' }}>Peer Candidates (Comparative Analysis)</h4>
                          <table className="data-table" style={{ backgroundColor: '#1e293b' }}>
                            <thead>
                              <tr>
                                <th>Peer Symbol</th>
                                <th>Score</th>
                                <th>Trigger</th>
                                <th>Entry</th>
                                <th>Target</th>
                                <th>Stop Loss</th>
                              </tr>
                            </thead>
                            <tbody>
                              {c.peers.map((peer: any, pIdx: number) => (
                                <tr key={`peer-${pIdx}`}>
                                  <td style={{ fontWeight: 600 }}>{peer.symbol}</td>
                                  <td className="text-cyan">{peer.score !== undefined ? peer.score.toFixed(1) : '-'}</td>
                                  <td>{peer.trigger_type}</td>
                                  <td>₹{peer.entry_price || '-'}</td>
                                  <td className="text-cyan">₹{peer.target || '-'}</td>
                                  <td className="text-danger">₹{peer.stop_loss || '-'}</td>
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
          ) : (
            <div className="flex-center" style={{ padding: '40px 0' }}>
              <p className="text-secondary">No perfect setups found for this date. (Extremely Strict Filtering)</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
