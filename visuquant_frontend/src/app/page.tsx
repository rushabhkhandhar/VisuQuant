"use client";

import { useState } from "react";

export default function Home() {
  const [date, setDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState("");

  const runScreener = async () => {
    setLoading(true);
    setError("");
    setResults(null);
    
    try {
      const payload = date ? { date, top_n: 5 } : { top_n: 5 };
      const res = await fetch("http://localhost:8000/api/screener", {
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
        <div className="flex gap-4">
          <input 
            type="date" 
            className="input-glass"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            placeholder="YYYY-MM-DD (Leave blank for today)"
          />
          <button 
            className="btn-primary" 
            onClick={runScreener}
            disabled={loading}
          >
            {loading ? <span className="loader"></span> : '▶'} {loading ? 'Running Screen...' : 'Run Screener'}
          </button>
        </div>
        {error && <p className="text-danger mt-4">{error}</p>}
      </div>

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
                  <th>Trend Status</th>
                </tr>
              </thead>
              <tbody>
                {results.candidates.map((c: any, idx: number) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{c.symbol}</td>
                    <td className="text-cyan">{c.score !== undefined ? c.score.toFixed(1) : '-'}</td>
                    <td>{c.trigger_type}</td>
                    <td className="text-success">{c.metrics?.trend_up_days} Days UP</td>
                  </tr>
                ))}
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
