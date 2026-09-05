"use client";

import React from "react";
import {
  IconEye,
  IconFileText,
  IconZap,
  IconCpu,
  IconPlay,
  IconSearch,
  IconBarChart,
  IconShield,
  IconChevronRight,
  IconTerminal,
} from "./Icons";
import InteractiveChart from "./InteractiveChart";

interface HeroLandingProps {
  onNavigate: (tab: string) => void;
}

export default function HeroLanding({ onNavigate }: HeroLandingProps) {
  const metrics = [
    {
      title: "Strategy CAGR",
      value: "39.82%",
      sub: "E19 Dead Money Cut Champion",
      color: "var(--cyan)",
      badge: "Institutional Alpha",
    },
    {
      title: "Calmar Ratio",
      value: "3.735",
      sub: "CAGR / Max Drawdown",
      color: "var(--emerald)",
      badge: "Risk Adjusted",
    },
    {
      title: "Max Drawdown",
      value: "-10.66%",
      sub: "Historical Peak-to-Trough",
      color: "var(--purple)",
      badge: "Capital Preservation",
    },
    {
      title: "Holdout 2024-2026",
      value: "+62.05%",
      sub: "Out-of-sample outperformance",
      color: "var(--amber)",
      badge: "Regime Resilient",
    },
  ];

  const features = [
    {
      icon: IconEye,
      iconColor: "var(--cyan)",
      title: "Qwen2.5-VL Chart Vision",
      desc: "Deep visual recognition on candlestick structure, detecting trendlines, chart patterns, and S&R zones directly from raw pixel charts.",
      tag: "Computer Vision",
    },
    {
      icon: IconFileText,
      iconColor: "var(--amber)",
      title: "Screener.in Filings & Annual Reports",
      desc: "Live Playwright extraction of official BSE Annual Reports, quarterly earnings concall transcripts, and disclosures with LLM Short/Long-Term POVs.",
      tag: "Exchange Intelligence",
    },
    {
      icon: IconZap,
      iconColor: "var(--emerald)",
      title: "Dual AVWAP & Dead Money Cut",
      desc: "Anchored VWAPs from key swing pivots combined with strict velocity decay timers to liquidate stagnant trades and recycle capital rapidly.",
      tag: "Quantitative Edge",
    },
    {
      icon: IconCpu,
      iconColor: "var(--purple)",
      title: "Institutional Confluence Engine",
      desc: "Synthesizes visual features, quantitative indicators, risk profiles, and fundamental metrics into a coherent institutional thesis and PDF dashboard.",
      tag: "Multi-Agent AI",
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "50px", padding: "40px 0" }}>
      {/* 1. Hero Headline & CTA */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          maxWidth: "860px",
          margin: "0 auto",
          gap: "20px",
        }}
      >
        <div className="badge badge-cyan" style={{ padding: "6px 14px", fontSize: "11px", display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <IconTerminal size={13} />
          <span>ADVANCED ALGORITHMIC TRADING TERMINAL</span>
        </div>

        <h1
          style={{
            fontSize: "46px",
            fontWeight: 800,
            lineHeight: 1.15,
            letterSpacing: "-0.03em",
          }}
        >
          Quantitative Alpha Engineered with{" "}
          <span className="text-gradient-cyan">Deep Vision AI</span> &{" "}
          <span className="text-gradient-purple">Exchange Filings</span>
        </h1>

        <p
          style={{
            fontSize: "17px",
            lineHeight: 1.6,
            color: "var(--text-secondary)",
            maxWidth: "720px",
          }}
        >
          VisuQuant combines state-of-the-art visual pattern extraction, Anchored VWAP momentum,
          live Screener.in corporate documents, and automated risk management into a unified trading
          station.
        </p>

        <div style={{ display: "flex", gap: "16px", marginTop: "12px", flexWrap: "wrap", justifyContent: "center" }}>
          <button onClick={() => onNavigate("screener")} className="btn btn-cyan" style={{ padding: "14px 28px", fontSize: "14px" }}>
            <IconPlay size={14} />
            <span>Launch Live Screener</span>
          </button>
          <button onClick={() => onNavigate("vision")} className="btn btn-purple" style={{ padding: "14px 28px", fontSize: "14px" }}>
            <IconSearch size={14} />
            <span>Deep Ticker Analysis</span>
          </button>
          <button onClick={() => onNavigate("backtest")} className="btn btn-glass" style={{ padding: "14px 24px", fontSize: "14px" }}>
            <IconBarChart size={14} />
            <span>View Strategy Forensics</span>
          </button>
        </div>
      </div>

      {/* 2. Key Performance Metric Grid */}
      <div className="grid-cols-4">
        {metrics.map((m, idx) => (
          <div key={idx} className="stat-card" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>{m.title}</span>
              <span className="badge" style={{ background: "rgba(255,255,255,0.06)", color: m.color, fontSize: "10px" }}>
                {m.badge}
              </span>
            </div>
            <div style={{ fontSize: "32px", fontWeight: 800, color: m.color, fontFamily: "'JetBrains Mono', monospace" }}>
              {m.value}
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>{m.sub}</div>
          </div>
        ))}
      </div>

      {/* 3. Market Regime & Engine Status Banner */}
      <div
        className="glass-panel"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "24px 32px",
          borderLeft: "4px solid var(--emerald)",
          flexWrap: "wrap",
          gap: "20px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "20px" }}>
          <div
            style={{
              width: "48px",
              height: "48px",
              borderRadius: "12px",
              background: "rgba(0, 255, 136, 0.12)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <IconShield size={24} color="var(--emerald)" />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <span style={{ fontSize: "18px", fontWeight: 700 }}>HMM Market Regime: Bullish Expansion</span>
              <span className="badge badge-bullish">Low Volatility Trend</span>
            </div>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
              NIFTY 500 trading above 50 & 200 EMA. Full capital allocation permitted (100% long exposure).
            </div>
          </div>
        </div>

        <button onClick={() => onNavigate("screener")} className="btn btn-emerald">
          <span>Run Regime-Filtered Screen</span>
          <IconChevronRight size={15} />
        </button>
      </div>

      {/* 4. Live Interactive Market Terminal & Candlestick Chart */}
      <InteractiveChart
        initialSymbol="NIFTY"
        height={540}
        title="Live Market Terminal & Candlestick Forensics"
        subtitle="Interactive candlestick engine featuring real-time OHLCV, Dual Anchored VWAP, and volume dynamics."
      />

      {/* 5. Core Features Showcase */}
      <div>

        <div style={{ marginBottom: "24px" }}>
          <h2 style={{ fontSize: "24px", fontWeight: 800, letterSpacing: "-0.02em" }}>
            The Institutional VisuQuant Architecture
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "14px", marginTop: "4px" }}>
            Four interconnected engines powering autonomous analysis, risk execution, and filings synthesis.
          </p>
        </div>

        <div className="grid-cols-2">
          {features.map((f, idx) => {
            const IconComp = f.icon;
            return (
              <div
                key={idx}
                className="glass-panel"
                style={{
                  padding: "24px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "14px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div
                    style={{
                      width: "40px",
                      height: "40px",
                      borderRadius: "10px",
                      background: "rgba(255,255,255,0.06)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <IconComp size={20} color={f.iconColor} />
                  </div>
                  <span className="badge badge-purple">{f.tag}</span>
                </div>
                <h3 style={{ fontSize: "18px", fontWeight: 700, margin: 0 }}>{f.title}</h3>
                <p style={{ fontSize: "13px", lineHeight: 1.6, color: "var(--text-secondary)", margin: 0 }}>
                  {f.desc}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
