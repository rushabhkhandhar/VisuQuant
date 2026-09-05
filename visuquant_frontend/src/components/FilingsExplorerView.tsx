"use client";

import React, { useState, useEffect } from "react";
import {
  IconSearch,
  IconFileText,
  IconMegaphone,
  IconMic,
  IconDownload,
  IconBuilding,
} from "./Icons";
import TickerAutocomplete from "./TickerAutocomplete";

export default function FilingsExplorerView() {
  const [symbol, setSymbol] = useState("TCS");
  const [activeTab, setActiveTab] = useState<"annual_reports" | "announcements" | "concalls">("annual_reports");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");

  const quickSymbols = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "DIXON", "MTARTECH"];

  const fetchFilings = async (sym: string) => {
    if (!sym.trim()) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`http://localhost:5000/api/company_filings?symbol=${sym.trim().toUpperCase()}`);
      const json = await res.json();
      if (json.status === "success" && json.data) {
        setData(json.data);
      } else {
        setError(json.message || "No filing data found.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to connect to Screener.in filing pipeline.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFilings(symbol);
  }, []);

  const docs = data?.documents || {};
  const annualReports = docs.annual_reports || [];
  const announcements = docs.announcements || [];
  const concalls = docs.concalls || [];
  const ratios = data?.ratios || {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* 1. Direct Search Header */}
      <div className="glass-panel" style={{ padding: "28px", overflow: "visible" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h2 style={{ fontSize: "20px", fontWeight: 800, margin: 0 }}>
              Screener.in Corporate Intelligence Explorer
            </h2>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
              Automated scraping pipeline extracting corporate filings, AGM transcripts, and exchange announcements.
            </div>
          </div>
          <div className="badge badge-cyan" style={{ padding: "6px 12px" }}>
            Playwright Pipeline Live
          </div>
        </div>

        <div style={{ display: "flex", gap: "16px", alignItems: "flex-end", flexWrap: "wrap", overflow: "visible" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px", flex: 1, minWidth: "200px", position: "relative" }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>
              Search Any NSE / BSE Symbol
            </label>
            <TickerAutocomplete
              value={symbol}
              onChange={setSymbol}
              placeholder="e.g. TCS"
            />
          </div>

          <button
            onClick={() => fetchFilings(symbol)}
            disabled={loading}
            className="btn btn-cyan"
            style={{ padding: "12px 28px", fontSize: "14px" }}
          >
            {loading ? (
              <>
                <span className="loader" style={{ width: "14px", height: "14px" }} />
                <span>Querying Screener.in...</span>
              </>
            ) : (
              <>
                <IconSearch size={14} />
                <span>Fetch Official Filings</span>
              </>
            )}
          </button>
        </div>

        {/* Quick Tickers */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "16px", flexWrap: "wrap" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>Quick Lookup:</span>
          {quickSymbols.map((sym) => (
            <button
              key={sym}
              onClick={() => {
                setSymbol(sym);
                fetchFilings(sym);
              }}
              className="btn btn-glass"
              style={{ padding: "4px 10px", fontSize: "11px", fontFamily: "'JetBrains Mono', monospace" }}
            >
              {sym}
            </button>
          ))}
        </div>
      </div>

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
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* 2. Company Fundamentals Snapshot */}
      {data && (
        <div className="glass-panel" style={{ padding: "24px 28px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px", marginBottom: "16px" }}>
            <div>
              <h3 style={{ fontSize: "20px", fontWeight: 800, margin: 0 }}>
                {data.company_name || symbol}
              </h3>
              {data.about && (
                <p style={{ color: "var(--text-secondary)", fontSize: "13px", maxWidth: "800px", marginTop: "6px", lineHeight: 1.5 }}>
                  {data.about}
                </p>
              )}
            </div>
            <span className="badge badge-bullish">BSE / NSE Verified</span>
          </div>

          {/* Ratios Grid */}
          <div className="grid-cols-4" style={{ gap: "10px", marginTop: "16px" }}>
            {Object.entries(ratios).slice(0, 8).map(([k, v]: [string, any], idx) => (
              <div key={idx} className="stat-card" style={{ padding: "12px 16px" }}>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>{k}</div>
                <div className="font-mono" style={{ fontSize: "17px", fontWeight: 800, color: "var(--cyan)", marginTop: "4px" }}>
                  {v}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. Document Repository Tabs */}
      {data && (
        <div className="glass-panel" style={{ padding: "24px 28px" }}>
          <div style={{ display: "flex", gap: "10px", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "14px", marginBottom: "20px", flexWrap: "wrap" }}>
            <button
              onClick={() => setActiveTab("annual_reports")}
              className={`btn ${activeTab === "annual_reports" ? "btn-cyan" : "btn-glass"}`}
              style={{ fontSize: "13px", padding: "8px 16px" }}
            >
              <IconFileText size={14} />
              <span>Annual Reports ({annualReports.length})</span>
            </button>
            <button
              onClick={() => setActiveTab("announcements")}
              className={`btn ${activeTab === "announcements" ? "btn-cyan" : "btn-glass"}`}
              style={{ fontSize: "13px", padding: "8px 16px" }}
            >
              <IconMegaphone size={14} />
              <span>Corporate Filings ({announcements.length})</span>
            </button>
            <button
              onClick={() => setActiveTab("concalls")}
              className={`btn ${activeTab === "concalls" ? "btn-cyan" : "btn-glass"}`}
              style={{ fontSize: "13px", padding: "8px 16px" }}
            >
              <IconMic size={14} />
              <span>Concall Transcripts ({concalls.length})</span>
            </button>
          </div>

          {/* A. Annual Reports Tab */}
          {activeTab === "annual_reports" && (
            <div>
              {annualReports.length === 0 ? (
                <p style={{ color: "var(--text-muted)" }}>No annual reports found.</p>
              ) : (
                <table className="terminal-table">
                  <thead>
                    <tr>
                      <th style={{ width: "15%" }}>Financial Year</th>
                      <th style={{ width: "50%" }}>Document Title</th>
                      <th style={{ width: "20%" }}>Filing Source</th>
                      <th style={{ width: "15%", textAlign: "right" }}>Download</th>
                    </tr>
                  </thead>
                  <tbody>
                    {annualReports.map((ar: any, idx: number) => (
                      <tr key={idx}>
                        <td style={{ fontWeight: 800, color: "var(--emerald)", fontFamily: "'JetBrains Mono', monospace" }}>
                          FY {ar.year || "Report"}
                        </td>
                        <td style={{ fontWeight: 600 }}>{ar.title}</td>
                        <td style={{ color: "var(--text-secondary)", fontSize: "12px" }}>BSE India Exchange</td>
                        <td style={{ textAlign: "right" }}>
                          {ar.url ? (
                            <a
                              href={ar.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn btn-glass"
                              style={{ padding: "6px 14px", fontSize: "12px", color: "var(--cyan)", borderColor: "var(--border-glow-cyan)" }}
                            >
                              <IconDownload size={13} />
                              <span>View PDF</span>
                            </a>
                          ) : (
                            <span style={{ color: "var(--text-muted)", fontSize: "12px" }}>Unavailable</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* B. Announcements Tab */}
          {activeTab === "announcements" && (
            <div>
              {announcements.length === 0 ? (
                <p style={{ color: "var(--text-muted)" }}>No recent corporate announcements found.</p>
              ) : (
                <table className="terminal-table">
                  <thead>
                    <tr>
                      <th style={{ width: "15%" }}>Date</th>
                      <th style={{ width: "35%" }}>Title</th>
                      <th style={{ width: "35%" }}>Description / Catalyst</th>
                      <th style={{ width: "15%", textAlign: "right" }}>Document</th>
                    </tr>
                  </thead>
                  <tbody>
                    {announcements.map((ann: any, idx: number) => (
                      <tr key={idx}>
                        <td className="font-mono" style={{ color: "var(--amber)", fontSize: "12px" }}>
                          {ann.date || "Recent"}
                        </td>
                        <td style={{ fontWeight: 700 }}>{ann.title}</td>
                        <td style={{ color: "var(--text-secondary)", fontSize: "12px", lineHeight: 1.4 }}>
                          {ann.description}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          {ann.attachment ? (
                            <a
                              href={ann.attachment}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn btn-glass"
                              style={{ padding: "6px 12px", fontSize: "11px", color: "var(--cyan)" }}
                            >
                              <IconDownload size={13} />
                              <span>PDF Filing</span>
                            </a>
                          ) : (
                            <span style={{ color: "var(--text-dim)", fontSize: "11px" }}>No PDF</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* C. Concalls Tab */}
          {activeTab === "concalls" && (
            <div>
              {concalls.length === 0 ? (
                <p style={{ color: "var(--text-muted)" }}>No concall transcripts found.</p>
              ) : (
                <table className="terminal-table">
                  <thead>
                    <tr>
                      <th style={{ width: "20%" }}>Quarter / Period</th>
                      <th style={{ width: "50%" }}>Available Documents</th>
                      <th style={{ width: "30%", textAlign: "right" }}>Quick Links</th>
                    </tr>
                  </thead>
                  <tbody>
                    {concalls.map((cc: any, idx: number) => (
                      <tr key={idx}>
                        <td style={{ fontWeight: 800, color: "var(--purple)", fontFamily: "'JetBrains Mono', monospace" }}>
                          {cc.period}
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                            {cc.transcript_url && <span className="badge badge-cyan">Transcript</span>}
                            {cc.ppt_url && <span className="badge badge-purple">Investor PPT</span>}
                            {cc.rec_url && <span className="badge badge-amber">Audio / Webcast</span>}
                          </div>
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <div style={{ display: "inline-flex", gap: "8px" }}>
                            {cc.transcript_url && (
                              <a
                                href={cc.transcript_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn btn-glass"
                                style={{ padding: "5px 10px", fontSize: "11px" }}
                              >
                                Transcript PDF
                              </a>
                            )}
                            {cc.ppt_url && (
                              <a
                                href={cc.ppt_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn btn-glass"
                                style={{ padding: "5px 10px", fontSize: "11px" }}
                              >
                                PPT
                              </a>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
