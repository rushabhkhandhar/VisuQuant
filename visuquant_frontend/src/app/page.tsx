"use client";

import { useState } from "react";

export default function Home() {
  const [date, setDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState("");
  
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

  const runScreener = async () => {
    setLoading(true);
    setError("");
    setResults(null);
    
    try {
      const payload = date ? { date, top_n: 5 } : { top_n: 5 };
      const res = await fetch("http://localhost:5000/api/screener", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        throw new Error("Failed to fetch data from engine");
      }
      
      const data = await res.json();
      setResults(data);
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
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
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

      {results && (
        <div className="glass-panel">
          <h2 style={{ margin: '0 0 16px 0', fontSize: '20px' }}>Candidates ({results.candidates.length})</h2>
          
          {results.candidates.length > 0 ? (
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
                    <tr key={idx}>
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
                      <td style={{ textAlign: 'center' }}>
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
                      </td>
                    </tr>
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
