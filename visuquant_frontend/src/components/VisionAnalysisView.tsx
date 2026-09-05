"use client";

import React, { useState } from "react";
import {
  IconZap,
  IconActivity,
  IconCheck,
  IconDownload,
  IconFileText,
  IconShield,
} from "./Icons";

interface VisionAnalysisViewProps {
  initialSymbol?: string;
}

export default function VisionAnalysisView({ initialSymbol = "TCS" }: VisionAnalysisViewProps) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [date, setDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [currentStep, setCurrentStep] = useState(0);

  const steps = [
    { title: "Chart Capture", desc: "TradingView & Mplfinance dark candle generation" },
    { title: "Qwen2.5-VL Vision", desc: "Extracting visual trendlines, S&R zones, and patterns" },
    { title: "Quantitative Trend", desc: "Dual Anchored VWAPs, EMAs, and momentum math" },
    { title: "Screener.in Filings", desc: "Annual reports, quarterly concall transcripts & POVs" },
    { title: "Confluence Engine", desc: "Contradiction elimination & institutional synthesis" },
    { title: "Institutional Report", desc: "Compiled executive report with Chandelier ATR profile" },
  ];

  const runAnalysis = async () => {
    if (!symbol.trim()) {
      setError("Please specify a ticker symbol (e.g., TCS).");
      return;
    }
    setLoading(true);
    setError("");
    setPdfUrl(null);
    setCurrentStep(1);

    const stepInterval = setInterval(() => {
      setCurrentStep((prev) => (prev < 5 ? prev + 1 : prev));
    }, 4500);

    try {
      const payload: any = { symbol: symbol.trim().toUpperCase() };
      if (date) payload.date = date;

      const res = await fetch("http://localhost:5000/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      clearInterval(stepInterval);

      if (data.status === "success" && data.pdf_url) {
        setCurrentStep(6);
        setPdfUrl(data.pdf_url);
      } else {
        setError(data.message || "Failed to generate analysis report.");
      }
    } catch (err: any) {
      clearInterval(stepInterval);
      setError(err.message || "Network error while connecting to VisuQuant engine.");
    } finally {
      setLoading(false);
    }
  };

  const trendingSymbols = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "DIXON", "MTARTECH"];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* 1. Direct Analysis Form */}
      <div className="glass-panel" style={{ padding: "28px" }}>
        <div style={{ marginBottom: "20px" }}>
          <h2 style={{ fontSize: "20px", fontWeight: 800, margin: 0 }}>
            Deep Vision & Institutional Analysis Engine
          </h2>
          <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
            Executes the full LangGraph pipeline: Computer Vision on raw charts, Screener.in corporate filings, and generates an executive PDF dashboard.
          </div>
        </div>

        <div style={{ display: "flex", gap: "16px", alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px", flex: 1, minWidth: "220px" }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>
              NSE Ticker Symbol
            </label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="e.g. TCS"
              className="quant-input font-mono"
              style={{ textTransform: "uppercase", fontWeight: 700, fontSize: "15px" }}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>
              As-Of Date (Optional Historical)
            </label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="quant-input font-mono"
              style={{ width: "170px" }}
            />
          </div>

          <button
            onClick={runAnalysis}
            disabled={loading}
            className="btn btn-purple"
            style={{ padding: "12px 28px", fontSize: "14px" }}
          >
            {loading ? (
              <>
                <span className="loader" style={{ width: "14px", height: "14px" }} />
                <span>Synthesizing LangGraph...</span>
              </>
            ) : (
              <>
                <IconZap size={14} />
                <span>Run Deep Vision Scan</span>
              </>
            )}
          </button>
        </div>

        {/* Quick Ticker Chips */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "16px", flexWrap: "wrap" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>Quick Select:</span>
          {trendingSymbols.map((sym) => (
            <button
              key={sym}
              onClick={() => setSymbol(sym)}
              className="btn btn-glass"
              style={{ padding: "4px 10px", fontSize: "11px", fontFamily: "'JetBrains Mono', monospace" }}
            >
              {sym}
            </button>
          ))}
        </div>
      </div>

      {/* 2. Pipeline Progress Stepper */}
      {loading && (
        <div className="glass-panel" style={{ padding: "24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "16px" }}>
            <IconActivity size={16} color="var(--cyan)" />
            <h3 style={{ fontSize: "15px", fontWeight: 700, margin: 0, color: "var(--cyan)" }}>
              Autonomous Pipeline Execution
            </h3>
          </div>
          <div className="grid-cols-3" style={{ gap: "12px" }}>
            {steps.map((step, idx) => {
              const isPast = currentStep > idx;
              const isCurrent = currentStep === idx + 1;

              return (
                <div
                  key={idx}
                  style={{
                    background: isCurrent ? "rgba(0, 240, 255, 0.08)" : "var(--bg-surface-elevated)",
                    border: `1px solid ${isCurrent ? "var(--cyan)" : isPast ? "var(--emerald)" : "var(--border-subtle)"}`,
                    borderRadius: "10px",
                    padding: "14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "6px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 700 }}>
                      STEP 0{idx + 1}
                    </span>
                    {isPast && (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: "3px", color: "var(--emerald)", fontSize: "11px", fontWeight: 700 }}>
                        <IconCheck size={12} color="var(--emerald)" />
                        <span>DONE</span>
                      </span>
                    )}
                    {isCurrent && (
                      <span className="loader" style={{ width: "12px", height: "12px", borderTopColor: "var(--cyan)" }} />
                    )}
                  </div>
                  <div style={{ fontSize: "13px", fontWeight: 700, color: isCurrent ? "var(--cyan)" : "var(--text-primary)" }}>
                    {step.title}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                    {step.desc}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 3. Output / Success Banner */}
      {pdfUrl && (
        <div
          className="glass-panel-glow"
          style={{
            padding: "28px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "20px",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span className="badge badge-bullish" style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                <IconCheck size={11} color="var(--emerald)" />
                <span>SUCCESS</span>
              </span>
              <h3 style={{ fontSize: "18px", fontWeight: 800, margin: 0 }}>
                Institutional Analysis Report Ready for {symbol}
              </h3>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "13px", marginTop: "6px", maxWidth: "600px" }}>
              Full report generated with Qwen2.5-VL vision readings, Screener.in corporate filings & annual reports,
              and Chandelier ATR execution profile.
            </p>
          </div>

          <div style={{ display: "flex", gap: "12px" }}>
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-cyan"
              style={{ padding: "12px 24px", fontSize: "14px" }}
            >
              <IconDownload size={14} />
              <span>Download Institutional PDF</span>
            </a>
          </div>
        </div>
      )}

      {/* 4. Error Card */}
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
          <strong>Analysis failed:</strong> {error}
        </div>
      )}
    </div>
  );
}
