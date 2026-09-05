"use client";

import React, { useState } from "react";
import Header from "@/components/Header";
import HeroLanding from "@/components/HeroLanding";
import ScreenerView from "@/components/ScreenerView";
import VisionAnalysisView from "@/components/VisionAnalysisView";
import CustomStrategyView from "@/components/CustomStrategyView";
import BacktestView from "@/components/BacktestView";
import FilingsExplorerView from "@/components/FilingsExplorerView";

export default function Home() {
  const [activeTab, setActiveTab] = useState<string>("landing");
  const [targetTicker, setTargetTicker] = useState<string>("TCS");

  const handleDeepAnalyze = (sym: string) => {
    setTargetTicker(sym);
    setActiveTab("vision");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--bg-darkest)", transition: "background-color 0.25s ease" }}>
      {/* 1. Global Header with Live Marquee */}
      <Header activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* 2. Main Body Container */}
      <main style={{ maxWidth: "1280px", margin: "0 auto", padding: "24px 20px", width: "100%", flex: 1 }}>
        {activeTab === "landing" && (
          <HeroLanding onNavigate={(tab) => {
            setActiveTab(tab);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }} />
        )}

        {activeTab === "screener" && (
          <ScreenerView onAnalyzeTicker={handleDeepAnalyze} />
        )}

        {activeTab === "vision" && (
          <VisionAnalysisView initialSymbol={targetTicker} />
        )}

        {activeTab === "strategy" && (
          <CustomStrategyView onAnalyzeTicker={handleDeepAnalyze} />
        )}

        {activeTab === "backtest" && (
          <BacktestView />
        )}

        {activeTab === "filings" && (
          <FilingsExplorerView />
        )}
      </main>

      {/* 3. Institutional Footer */}
      <footer
        style={{
          borderTop: "1px solid var(--border-subtle)",
          background: "var(--footer-bg)",
          padding: "32px 24px",
          marginTop: "60px",
          transition: "background-color 0.25s ease, border-color 0.25s ease",
        }}
      >
        <div
          style={{
            maxWidth: "1280px",
            margin: "0 auto",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "20px",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "16px", fontWeight: 800 }}>VISU<span style={{ color: "var(--cyan)" }}>QUANT</span> TERMINAL</span>
              <span className="badge badge-cyan" style={{ fontSize: "9px" }}>v2.4 INSTITUTIONAL</span>
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
              Algorithmic Trend Screener & Deep Vision Confluence Engine • Dual Anchored VWAP Alpha
            </div>
          </div>

          <div style={{ display: "flex", gap: "24px", fontSize: "12px", color: "var(--text-secondary)", flexWrap: "wrap" }}>
            <span>FastAPI Server: :5000</span>
            <span>Ollama Vision: :11434</span>
            <span>Screener.in Scraper: Playwright</span>
          </div>
        </div>

        <div style={{ maxWidth: "1280px", margin: "20px auto 0", fontSize: "11px", color: "var(--text-dim)", lineHeight: 1.5 }}>
          Disclaimer: VisuQuant is an algorithmic and quantitative research workbench. Market data, visual detections,
          and AI trade parameters are for informational, backtesting, and automated risk management purposes only. Past
          performance does not guarantee future results.
        </div>
      </footer>
    </div>
  );
}
