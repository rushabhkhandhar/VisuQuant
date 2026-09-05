"use client";

import React, { useState, useEffect } from "react";
import { useTheme } from "./ThemeContext";
import {
  IconSun,
  IconMoon,
  IconActivity,
  IconTrendingUp,
  IconTrendingDown,
  IconTerminal,
  IconEye,
  IconSliders,
  IconBarChart,
  IconFileText,
} from "./Icons";

interface HeaderProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export default function Header({ activeTab, setActiveTab }: HeaderProps) {
  const [backendStatus, setBackendStatus] = useState<"checking" | "online" | "offline">("checking");
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch("http://localhost:5000/api/health", { method: "GET" });
        if (res.ok) setBackendStatus("online");
        else setBackendStatus("offline");
      } catch {
        setBackendStatus("offline");
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const tickers = [
    { sym: "NIFTY 50", price: "24,852.15", change: "+0.42%", isPos: true },
    { sym: "BANK NIFTY", price: "51,280.60", change: "+0.68%", isPos: true },
    { sym: "NIFTY 500", price: "23,190.45", change: "+0.35%", isPos: true },
    { sym: "INDIA VIX", price: "13.24", change: "-2.15%", isPos: false },
    { sym: "E19 SWING STRATEGY", price: "+39.82% CAGR", change: "Calmar: 3.735", isPos: true },
    { sym: "REGIME ENGINE", price: "BULLISH EXPANSION", change: "HMM Low Vol", isPos: true },
  ];

  const navTabs = [
    { id: "landing", label: "Terminal Overview", icon: IconActivity },
    { id: "screener", label: "Live Screener", icon: IconTerminal },
    { id: "vision", label: "Deep AI Analysis", icon: IconEye },
    { id: "strategy", label: "Custom Strategy", icon: IconSliders },
    { id: "backtest", label: "Backtest Lab", icon: IconBarChart },
    { id: "filings", label: "Screener.in Filings", icon: IconFileText },
  ];

  return (
    <header style={{ width: "100%", position: "sticky", top: 0, zIndex: 100 }}>
      {/* 1. Live Market Marquee Bar */}
      <div className="ticker-container">
        <div className="ticker-track">
          {[...tickers, ...tickers].map((t, idx) => (
            <div key={idx} className="ticker-item">
              <span style={{ color: "var(--text-muted)", fontWeight: 600 }}>{t.sym}</span>
              <span style={{ color: "var(--text-primary)", fontWeight: 700 }}>{t.price}</span>
              <span
                style={{
                  color: t.isPos ? "var(--emerald)" : "var(--crimson)",
                  fontWeight: 600,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "2px",
                }}
              >
                {t.isPos ? <IconTrendingUp size={11} /> : <IconTrendingDown size={11} />}
                {t.change}
              </span>
              <span style={{ color: "var(--border-glass)", margin: "0 4px" }}>•</span>
            </div>
          ))}
        </div>
      </div>

      {/* 2. Main Navigation Bar */}
      <div
        style={{
          background: "var(--header-bg)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderBottom: "1px solid var(--border-glass)",
          padding: "12px 28px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "16px",
          transition: "background-color 0.25s ease, border-color 0.25s ease",
        }}
      >
        {/* Brand */}
        <div
          onClick={() => setActiveTab("landing")}
          style={{ display: "flex", alignItems: "center", gap: "12px", cursor: "pointer" }}
        >
          <div
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "10px",
              background: "linear-gradient(135deg, var(--cyan) 0%, #7928ca 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 15px var(--cyan-glow)",
            }}
          >
            <span style={{ fontWeight: 900, color: "#fff", fontSize: "17px" }}>VQ</span>
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "17px", fontWeight: 800, letterSpacing: "-0.02em" }}>
                VISU<span style={{ color: "var(--cyan)" }}>QUANT</span>
              </span>
              <span className="badge badge-cyan" style={{ fontSize: "9px", padding: "2px 6px" }}>
                PRO TERMINAL
              </span>
            </div>
            <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
              Algorithmic Trend Screener & Deep Vision Engine
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
          {navTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`btn-tab ${isActive ? "active" : ""}`}
              >
                <Icon size={14} color={isActive ? "var(--cyan)" : "currentColor"} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>

        {/* System Status Indicators & Theme Toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "5px 10px",
              background: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "20px",
              fontSize: "11px",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            <div className={`pulse-dot ${backendStatus === "online" ? "online" : ""}`} />
            <span style={{ color: backendStatus === "online" ? "var(--emerald)" : "var(--crimson)" }}>
              {backendStatus === "online" ? "FastAPI: Online" : "FastAPI: Disconnected"}
            </span>
          </div>

          <div
            style={{
              padding: "5px 10px",
              background: "rgba(0, 240, 255, 0.08)",
              border: "1px solid var(--border-glow-cyan)",
              borderRadius: "20px",
              fontSize: "11px",
              color: "var(--cyan)",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            Qwen2.5-VL: Ready
          </div>

          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="btn-theme-toggle"
            title={`Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`}
            aria-label="Toggle Theme"
          >
            {theme === "dark" ? (
              <>
                <IconSun size={15} color="var(--amber)" />
                <span style={{ fontSize: "11px" }}>Light</span>
              </>
            ) : (
              <>
                <IconMoon size={15} color="var(--purple)" />
                <span style={{ fontSize: "11px" }}>Dark</span>
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
