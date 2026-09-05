"use client";

import React, { useState, useEffect } from "react";
import Header from "@/components/Header";
import HeroLanding from "@/components/HeroLanding";
import ScreenerView from "@/components/ScreenerView";
import VisionAnalysisView from "@/components/VisionAnalysisView";
import CustomStrategyView from "@/components/CustomStrategyView";
import BacktestView from "@/components/BacktestView";
import FilingsExplorerView from "@/components/FilingsExplorerView";

const VALID_TABS = ["landing", "screener", "vision", "strategy", "backtest", "filings"];

export default function Home() {
  const [activeTab, setActiveTab] = useState<string>("landing");
  const [targetTicker, setTargetTicker] = useState<string>("TCS");

  // 1. Initialize active tab & target ticker from URL Hash, Query Param, or LocalStorage on mount
  useEffect(() => {
    let initialTab = "landing";

    // Priority 1: URL Hash (#screener, #strategy, #backtest, etc.)
    const hash = window.location.hash.replace("#", "").toLowerCase().trim();
    if (VALID_TABS.includes(hash)) {
      initialTab = hash;
    } else {
      // Priority 2: Query param (?tab=screener)
      const params = new URLSearchParams(window.location.search);
      const qTab = params.get("tab")?.toLowerCase().trim();
      if (qTab && VALID_TABS.includes(qTab)) {
        initialTab = qTab;
      } else {
        // Priority 3: LocalStorage persistence
        try {
          const storedTab = localStorage.getItem("visuquant_active_tab")?.toLowerCase().trim();
          if (storedTab && VALID_TABS.includes(storedTab)) {
            initialTab = storedTab;
          }
        } catch {
          // Ignore storage restrictions
        }
      }
    }

    setActiveTab(initialTab);
    if (initialTab !== "landing" && !window.location.hash) {
      window.history.replaceState(null, "", `#${initialTab}`);
    }

    // Restore target ticker if saved
    try {
      const storedTicker = localStorage.getItem("visuquant_target_ticker");
      if (storedTicker && storedTicker.trim()) {
        setTargetTicker(storedTicker.trim().toUpperCase());
      }
    } catch {
      // Ignore
    }
  }, []);

  // 2. Listen to Browser Back / Forward Button Navigation
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace("#", "").toLowerCase().trim();
      if (VALID_TABS.includes(hash)) {
        setActiveTab(hash);
        try {
          localStorage.setItem("visuquant_active_tab", hash);
        } catch {}
      } else if (!hash) {
        setActiveTab("landing");
        try {
          localStorage.setItem("visuquant_active_tab", "landing");
        } catch {}
      }
    };

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  // 3. Tab Switch Handler with History & LocalStorage Sync
  const handleTabChange = (tab: string) => {
    if (!VALID_TABS.includes(tab)) return;
    setActiveTab(tab);
    try {
      localStorage.setItem("visuquant_active_tab", tab);
      if (tab === "landing") {
        window.history.pushState(null, "", window.location.pathname + window.location.search);
      } else {
        window.history.pushState(null, "", `#${tab}`);
      }
    } catch {}
  };

  const handleDeepAnalyze = (sym: string) => {
    const cleanSym = sym.trim().toUpperCase();
    setTargetTicker(cleanSym);
    try {
      localStorage.setItem("visuquant_target_ticker", cleanSym);
    } catch {}
    handleTabChange("vision");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--bg-darkest)", transition: "background-color 0.25s ease" }}>
      {/* 1. Global Header with Live Marquee */}
      <Header activeTab={activeTab} setActiveTab={handleTabChange} />

      {/* 2. Main Body Container */}
      <main style={{ maxWidth: "1280px", margin: "0 auto", padding: "24px 20px", width: "100%", flex: 1 }}>
        {activeTab === "landing" && (
          <HeroLanding onNavigate={(tab) => {
            handleTabChange(tab);
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
