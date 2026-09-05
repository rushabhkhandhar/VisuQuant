"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  IconActivity,
  IconRefresh,
  IconSearch,
  IconChevronRight,
  IconZap,
  IconBarChart,
  IconLayers,
} from "./Icons";

interface StockRecord {
  symbol: string;
  name: string;
  open: number;
  high: number;
  low: number;
  close: number;
  change: number;
  volume: number;
  market_cap: number;
  sector: string;
}

interface SectorSummary {
  sector: string;
  avg_change: number;
  count: number;
  advances: number;
  declines: number;
  total_volume: number;
  total_market_cap: number;
  stocks: StockRecord[];
}

interface MarketOverviewData {
  status: string;
  timestamp: string;
  total_stocks: number;
  summary: {
    advances: number;
    declines: number;
    unchanged: number;
    advance_decline_ratio: number;
    top_sector: string;
    top_sector_change: number;
    bottom_sector: string;
    bottom_sector_change: number;
  };
  movers: {
    gainers: StockRecord[];
    losers: StockRecord[];
    most_active: StockRecord[];
  };
  sectors: SectorSummary[];
}

interface MarketHeatmapProps {
  onAnalyzeTicker: (symbol: string) => void;
}

export default function MarketHeatmap({ onAnalyzeTicker }: MarketHeatmapProps) {
  const [data, setData] = useState<MarketOverviewData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<"heatmap" | "movers">("heatmap");
  const [universeFilter, setUniverseFilter] = useState<"50" | "100" | "500">("100");
  const [selectedSector, setSelectedSector] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const [hoveredStock, setHoveredStock] = useState<StockRecord | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const containerRef = useRef<HTMLDivElement>(null);

  const fetchOverview = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const url = `http://localhost:5000/api/market_overview${isManual ? "?refresh=true" : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (json.status === "success") {
        setData(json);
        setError(null);
      } else {
        throw new Error(json.message || "Failed to load market data");
      }
    } catch (err: any) {
      console.error("Market overview fetch error:", err);
      setError("Unable to sync live market overview.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchOverview();
    const interval = setInterval(() => {
      fetchOverview();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Precise institutional color mapping
  const getTileStyle = (change: number) => {
    if (change >= 3.0) {
      return {
        bg: "rgba(0, 230, 118, 0.45)",
        border: "rgba(0, 230, 118, 0.8)",
        text: "#ffffff",
        changeColor: "#b9f6ca",
      };
    }
    if (change >= 1.5) {
      return {
        bg: "rgba(0, 200, 83, 0.32)",
        border: "rgba(0, 230, 118, 0.55)",
        text: "#ffffff",
        changeColor: "#a7f3d0",
      };
    }
    if (change > 0.0) {
      return {
        bg: "rgba(16, 185, 129, 0.22)",
        border: "rgba(16, 185, 129, 0.45)",
        text: "#ffffff",
        changeColor: "#6ee7b7",
      };
    }
    if (change === 0.0) {
      return {
        bg: "rgba(255, 255, 255, 0.05)",
        border: "rgba(255, 255, 255, 0.12)",
        text: "var(--text-muted)",
        changeColor: "var(--text-muted)",
      };
    }
    if (change > -1.5) {
      return {
        bg: "rgba(239, 68, 68, 0.22)",
        border: "rgba(239, 68, 68, 0.45)",
        text: "#ffffff",
        changeColor: "#fca5a5",
      };
    }
    if (change > -3.0) {
      return {
        bg: "rgba(220, 38, 38, 0.32)",
        border: "rgba(255, 68, 68, 0.55)",
        text: "#ffffff",
        changeColor: "#fecaca",
      };
    }
    return {
      bg: "rgba(220, 38, 38, 0.45)",
      border: "rgba(255, 68, 68, 0.8)",
      text: "#ffffff",
      changeColor: "#fee2e2",
    };
  };

  const formatVolume = (vol: number) => {
    if (vol >= 10000000) return `${(vol / 10000000).toFixed(2)} Cr`;
    if (vol >= 100000) return `${(vol / 100000).toFixed(1)} L`;
    if (vol >= 1000) return `${(vol / 1000).toFixed(1)} K`;
    return `${vol}`;
  };

  const formatMarketCap = (mcap: number) => {
    if (mcap >= 1000000000000) return `₹${(mcap / 1000000000000).toFixed(2)}T`;
    if (mcap >= 10000000) return `₹${(mcap / 10000000).toFixed(0)} Cr`;
    return `₹${mcap.toLocaleString()}`;
  };

  // Filter and limit stocks according to universe and search
  const processedSectors = useMemo(() => {
    if (!data?.sectors) return [];
    const maxStocks = universeFilter === "50" ? 50 : universeFilter === "100" ? 100 : 500;

    // Get top N overall stocks by market cap for 50/100 filter
    const allSorted = data.sectors
      .flatMap((s) => s.stocks)
      .sort((a, b) => b.market_cap - a.market_cap);
    const allowedSymbols = new Set(allSorted.slice(0, maxStocks).map((s) => s.symbol));

    let list = data.sectors.map((sec) => {
      let secStocks = sec.stocks.filter((st) => allowedSymbols.has(st.symbol));

      if (searchQuery.trim()) {
        const q = searchQuery.trim().toUpperCase();
        secStocks = secStocks.filter(
          (st) => st.symbol.includes(q) || st.name.toUpperCase().includes(q)
        );
      }

      return {
        ...sec,
        stocks: secStocks,
      };
    });

    if (selectedSector !== "ALL") {
      list = list.filter((s) => s.sector === selectedSector);
    } else {
      list = list.filter((s) => s.stocks.length > 0);
    }

    // Sort sectors by count or absolute performance for clean layout
    return list.sort((a, b) => b.stocks.length - a.stocks.length);
  }, [data, universeFilter, selectedSector, searchQuery]);

  const allSectorNames = useMemo(() => {
    if (!data?.sectors) return [];
    return data.sectors.map((s) => s.sector);
  }, [data]);

  return (
    <div
      ref={containerRef}
      className="glass-panel"
      style={{
        width: "100%",
        display: "flex",
        flexDirection: "column",
        border: "1px solid var(--border-subtle)",
        borderRadius: "12px",
        overflow: "hidden",
        boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
        background: "rgba(10, 14, 26, 0.78)",
      }}
    >
      {/* Top Compact Controls Bar */}
      <div
        style={{
          padding: "8px 14px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border-subtle)",
          background: "rgba(255, 255, 255, 0.02)",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        {/* Left: Title & Status */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div
            style={{
              width: "22px",
              height: "22px",
              borderRadius: "6px",
              background: "rgba(0, 229, 255, 0.12)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <IconActivity size={13} color="var(--cyan)" />
          </div>
          <span style={{ fontSize: "13px", fontWeight: 800, letterSpacing: "-0.01em" }}>
            Sector Heatmap
          </span>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "3px",
              background: "rgba(0, 255, 136, 0.1)",
              border: "1px solid rgba(0, 255, 136, 0.3)",
              borderRadius: "10px",
              padding: "1px 6px",
              fontSize: "9.5px",
              fontWeight: 700,
              color: "var(--emerald)",
            }}
          >
            <span
              style={{
                width: "4px",
                height: "4px",
                borderRadius: "50%",
                background: "var(--emerald)",
                boxShadow: "0 0 5px var(--emerald)",
              }}
            />
            <span>LIVE</span>
          </span>

          {/* Mini Breadth Summary */}
          {data?.summary && (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                background: "rgba(0,0,0,0.35)",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: "6px",
                padding: "2px 7px",
                fontSize: "10px",
                marginLeft: "4px",
              }}
            >
              <span style={{ color: "var(--emerald)", fontWeight: 700 }}>
                ▲ {data.summary.advances}
              </span>
              <span style={{ color: "var(--text-muted)" }}>/</span>
              <span style={{ color: "var(--crimson)", fontWeight: 700 }}>
                ▼ {data.summary.declines}
              </span>
            </div>
          )}
        </div>

        {/* Center: Heatmap / Movers Mode Switch */}
        <div
          style={{
            display: "flex",
            gap: "2px",
            background: "rgba(0,0,0,0.35)",
            padding: "2px",
            borderRadius: "6px",
            border: "1px solid rgba(255,255,255,0.05)",
          }}
        >
          <button
            onClick={() => setActiveTab("heatmap")}
            style={{
              padding: "3px 8px",
              fontSize: "10.5px",
              fontWeight: 600,
              borderRadius: "4px",
              border: "none",
              cursor: "pointer",
              background: activeTab === "heatmap" ? "var(--cyan)" : "transparent",
              color: activeTab === "heatmap" ? "#000" : "var(--text-secondary)",
              transition: "all 0.15s ease",
            }}
          >
            Heatmap
          </button>
          <button
            onClick={() => setActiveTab("movers")}
            style={{
              padding: "3px 8px",
              fontSize: "10.5px",
              fontWeight: 600,
              borderRadius: "4px",
              border: "none",
              cursor: "pointer",
              background: activeTab === "movers" ? "var(--cyan)" : "transparent",
              color: activeTab === "movers" ? "#000" : "var(--text-secondary)",
              transition: "all 0.15s ease",
            }}
          >
            Top Movers
          </button>
        </div>

        {/* Right: Universe Selector, Sector Dropdown & Search */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
          {/* Universe buttons */}
          <div
            style={{
              display: "flex",
              gap: "2px",
              background: "rgba(255,255,255,0.04)",
              borderRadius: "5px",
              padding: "2px",
            }}
          >
            <button
              onClick={() => setUniverseFilter("50")}
              title="Top 50 NIFTY Stocks (Fit without scroll)"
              style={{
                padding: "2px 6px",
                fontSize: "9.5px",
                fontWeight: 700,
                borderRadius: "3px",
                border: "none",
                cursor: "pointer",
                background: universeFilter === "50" ? "rgba(0, 229, 255, 0.25)" : "transparent",
                color: universeFilter === "50" ? "var(--cyan)" : "var(--text-muted)",
              }}
            >
              NIFTY 50
            </button>
            <button
              onClick={() => setUniverseFilter("100")}
              title="Top 100 Market Cap Leaders"
              style={{
                padding: "2px 6px",
                fontSize: "9.5px",
                fontWeight: 700,
                borderRadius: "3px",
                border: "none",
                cursor: "pointer",
                background: universeFilter === "100" ? "rgba(0, 229, 255, 0.25)" : "transparent",
                color: universeFilter === "100" ? "var(--cyan)" : "var(--text-muted)",
              }}
            >
              NIFTY 100
            </button>
            <button
              onClick={() => setUniverseFilter("500")}
              title="Full NIFTY 500 Universe"
              style={{
                padding: "2px 6px",
                fontSize: "9.5px",
                fontWeight: 700,
                borderRadius: "3px",
                border: "none",
                cursor: "pointer",
                background: universeFilter === "500" ? "rgba(0, 229, 255, 0.25)" : "transparent",
                color: universeFilter === "500" ? "var(--cyan)" : "var(--text-muted)",
              }}
            >
              NIFTY 500
            </button>
          </div>

          {/* Sector filter */}
          <select
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            style={{
              background: "rgba(255, 255, 255, 0.05)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "5px",
              color: "var(--text-primary)",
              padding: "3px 6px",
              fontSize: "10px",
              outline: "none",
              cursor: "pointer",
            }}
          >
            <option value="ALL">All Sectors</option>
            {data?.summary?.top_sector && (
              <option value={data.summary.top_sector}>
                🚀 Best: {data.summary.top_sector} ({data.summary.top_sector_change > 0 ? "+" : ""}{data.summary.top_sector_change}%)
              </option>
            )}
            {data?.summary?.bottom_sector && (
              <option value={data.summary.bottom_sector}>
                🔻 Worst: {data.summary.bottom_sector} ({data.summary.bottom_sector_change}%)
              </option>
            )}
            <option disabled>──────────</option>
            {allSectorNames.map((sec) => (
              <option key={sec} value={sec}>
                {sec}
              </option>
            ))}
          </select>

          {/* Search box */}
          <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
            <IconSearch size={11} style={{ position: "absolute", left: "6px", color: "var(--text-muted)" }} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search ticker..."
              style={{
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "5px",
                color: "var(--text-primary)",
                padding: "3px 6px 3px 20px",
                fontSize: "10px",
                width: "84px",
                outline: "none",
              }}
            />
          </div>

          {/* Refresh button */}
          <button
            onClick={() => fetchOverview(true)}
            disabled={refreshing}
            style={{
              background: "rgba(255,255,255,0.05)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "5px",
              color: "var(--text-secondary)",
              padding: "3px 6px",
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
            }}
            title="Refresh Quotes"
          >
            <IconRefresh size={11} className={refreshing ? "spin-animation" : ""} />
          </button>
        </div>
      </div>

      {/* Sector Quick Leader & Laggard Action Strip */}
      {data?.summary && (
        <div
          style={{
            padding: "5px 14px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
            background: "rgba(0, 0, 0, 0.25)",
            fontSize: "10.5px",
            flexWrap: "wrap",
            gap: "8px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
            <span
              style={{
                fontSize: "9.5px",
                color: "var(--text-muted)",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              Sector Extremes:
            </span>

            {/* Option 1: Most Upward Moving Sector */}
            {data.summary.top_sector && (
              <button
                onClick={() => {
                  setActiveTab("heatmap");
                  setSelectedSector((prev) =>
                    prev === data.summary.top_sector ? "ALL" : data.summary.top_sector
                  );
                }}
                title={`Filter to Most Upward Moving Sector: ${data.summary.top_sector}`}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  background:
                    selectedSector === data.summary.top_sector
                      ? "rgba(0, 230, 118, 0.28)"
                      : "rgba(0, 230, 118, 0.08)",
                  border: `1px solid ${
                    selectedSector === data.summary.top_sector
                      ? "var(--emerald)"
                      : "rgba(0, 230, 118, 0.35)"
                  }`,
                  borderRadius: "5px",
                  padding: "2px 8px",
                  fontSize: "10px",
                  fontWeight: 700,
                  color: "var(--emerald)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  boxShadow:
                    selectedSector === data.summary.top_sector
                      ? "0 0 10px rgba(0, 230, 118, 0.3)"
                      : "none",
                }}
              >
                <span>🚀 Top Leader:</span>
                <span style={{ fontWeight: 800 }}>
                  {data.summary.top_sector} ({data.summary.top_sector_change > 0 ? "+" : ""}
                  {data.summary.top_sector_change}%)
                </span>
                {selectedSector === data.summary.top_sector && (
                  <span style={{ fontSize: "9px", opacity: 0.85, marginLeft: "2px" }}>✕</span>
                )}
              </button>
            )}

            {/* Option 2: Worst Performing Sector */}
            {data.summary.bottom_sector && (
              <button
                onClick={() => {
                  setActiveTab("heatmap");
                  setSelectedSector((prev) =>
                    prev === data.summary.bottom_sector ? "ALL" : data.summary.bottom_sector
                  );
                }}
                title={`Filter to Worst Performing Sector: ${data.summary.bottom_sector}`}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  background:
                    selectedSector === data.summary.bottom_sector
                      ? "rgba(255, 61, 87, 0.28)"
                      : "rgba(255, 61, 87, 0.08)",
                  border: `1px solid ${
                    selectedSector === data.summary.bottom_sector
                      ? "var(--crimson)"
                      : "rgba(255, 61, 87, 0.35)"
                  }`,
                  borderRadius: "5px",
                  padding: "2px 8px",
                  fontSize: "10px",
                  fontWeight: 700,
                  color: "var(--crimson)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  boxShadow:
                    selectedSector === data.summary.bottom_sector
                      ? "0 0 10px rgba(255, 61, 87, 0.3)"
                      : "none",
                }}
              >
                <span>🔻 Worst Sector:</span>
                <span style={{ fontWeight: 800 }}>
                  {data.summary.bottom_sector} ({data.summary.bottom_sector_change}%)
                </span>
                {selectedSector === data.summary.bottom_sector && (
                  <span style={{ fontSize: "9px", opacity: 0.85, marginLeft: "2px" }}>✕</span>
                )}
              </button>
            )}
          </div>

          {/* Reset button when a specific sector is filtered */}
          {selectedSector !== "ALL" && (
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ color: "var(--text-muted)", fontSize: "10px" }}>
                Filtered: <strong style={{ color: "var(--cyan)" }}>{selectedSector}</strong>
              </span>
              <button
                onClick={() => setSelectedSector("ALL")}
                style={{
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "4px",
                  color: "var(--text-secondary)",
                  padding: "2px 6px",
                  fontSize: "9.5px",
                  cursor: "pointer",
                }}
              >
                Show All Sectors
              </button>
            </div>
          )}
        </div>
      )}

      {/* Main Rectangular Viewport Box (Compact ~340px height so everything is easily compared altogether) */}
      <div
        style={{
          height: "340px",
          overflowY: "auto",
          padding: "8px",
          position: "relative",
          background: "rgba(0, 0, 0, 0.18)",
        }}
      >
        {loading && (
          <div
            style={{
              height: "100%",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
            }}
          >
            <div
              className="spin-animation"
              style={{
                width: "20px",
                height: "20px",
                borderRadius: "50%",
                border: "2px solid rgba(0, 229, 255, 0.2)",
                borderTopColor: "var(--cyan)",
              }}
            />
            <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
              Loading real-time sector matrix...
            </span>
          </div>
        )}

        {/* View 1: Compact Sector Heatmap Grid */}
        {!loading && activeTab === "heatmap" && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))",
              gap: "6px",
              alignItems: "start",
            }}
          >
            {processedSectors.map((sec) => {
              const secColor = sec.avg_change >= 0 ? "var(--emerald)" : "var(--crimson)";
              return (
                <div
                  key={sec.sector}
                  style={{
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid rgba(255, 255, 255, 0.06)",
                    borderRadius: "6px",
                    padding: "5px 6px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "4px",
                  }}
                >
                  {/* Sector Mini Header */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
                      paddingBottom: "3px",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 800,
                        color: "var(--text-primary)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        maxWidth: "125px",
                        letterSpacing: "-0.01em",
                      }}
                      title={sec.sector}
                    >
                      {sec.sector}
                    </span>
                    <span
                      style={{
                        fontSize: "9.5px",
                        fontWeight: 800,
                        color: secColor,
                      }}
                    >
                      {sec.avg_change > 0 ? "+" : ""}
                      {sec.avg_change}%
                    </span>
                  </div>

                  {/* Stock Micro-Tiles inside Sector */}
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "3px",
                    }}
                  >
                    {sec.stocks.map((st) => {
                      const tile = getTileStyle(st.change);
                      return (
                        <div
                          key={st.symbol}
                          onClick={() => onAnalyzeTicker(st.symbol)}
                          onMouseEnter={(e) => {
                            setHoveredStock(st);
                            const rect = e.currentTarget.getBoundingClientRect();
                            setTooltipPos({ x: rect.left + rect.width / 2, y: rect.top - 8 });
                          }}
                          onMouseLeave={() => setHoveredStock(null)}
                          style={{
                            background: tile.bg,
                            border: `1px solid ${tile.border}`,
                            borderRadius: "3px",
                            padding: "2px 4px",
                            height: "22px",
                            minWidth: "38px",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            cursor: "pointer",
                            transition: "all 0.1s ease",
                            userSelect: "none",
                            flexGrow: 1,
                          }}
                          onMouseOver={(e) => {
                            e.currentTarget.style.transform = "scale(1.15)";
                            e.currentTarget.style.boxShadow = "0 3px 10px rgba(0,0,0,0.6)";
                            e.currentTarget.style.zIndex = "10";
                          }}
                          onMouseOut={(e) => {
                            e.currentTarget.style.transform = "none";
                            e.currentTarget.style.boxShadow = "none";
                            e.currentTarget.style.zIndex = "1";
                          }}
                        >
                          <span
                            style={{
                              fontSize: "8.5px",
                              fontWeight: 800,
                              lineHeight: 1,
                              color: tile.text,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              letterSpacing: "-0.02em",
                            }}
                          >
                            {st.symbol}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* View 2: Compact Market Movers (3 side-by-side columns inside the box) */}
        {!loading && activeTab === "movers" && data?.movers && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "8px",
              height: "100%",
            }}
          >
            {/* Top Gainers */}
            <div
              style={{
                background: "rgba(0, 230, 118, 0.04)",
                border: "1px solid rgba(0, 230, 118, 0.2)",
                borderRadius: "6px",
                padding: "8px",
                display: "flex",
                flexDirection: "column",
                gap: "4px",
                overflowY: "auto",
              }}
            >
              <div style={{ fontSize: "11px", fontWeight: 800, color: "var(--emerald)", display: "flex", justifyContent: "space-between" }}>
                <span>▲ Top Gainers</span>
                <span style={{ fontSize: "9px", color: "var(--text-muted)" }}>NIFTY 500</span>
              </div>
              {data.movers.gainers.slice(0, 10).map((st) => (
                <div
                  key={st.symbol}
                  onClick={() => onAnalyzeTicker(st.symbol)}
                  onMouseEnter={(e) => {
                    setHoveredStock(st);
                    const rect = e.currentTarget.getBoundingClientRect();
                    setTooltipPos({ x: rect.left + rect.width / 2, y: rect.top - 8 });
                  }}
                  onMouseLeave={() => setHoveredStock(null)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "3px 6px",
                    borderRadius: "4px",
                    background: "rgba(0,0,0,0.25)",
                    cursor: "pointer",
                    fontSize: "10px",
                  }}
                  onMouseOver={(e) => (e.currentTarget.style.background = "rgba(0, 230, 118, 0.15)")}
                  onMouseOut={(e) => (e.currentTarget.style.background = "rgba(0,0,0,0.25)")}
                >
                  <span style={{ fontWeight: 700 }}>{st.symbol}</span>
                  <span style={{ color: "var(--emerald)", fontWeight: 800 }}>+{st.change}%</span>
                </div>
              ))}
            </div>

            {/* Top Losers */}
            <div
              style={{
                background: "rgba(255, 61, 87, 0.04)",
                border: "1px solid rgba(255, 61, 87, 0.2)",
                borderRadius: "6px",
                padding: "8px",
                display: "flex",
                flexDirection: "column",
                gap: "4px",
                overflowY: "auto",
              }}
            >
              <div style={{ fontSize: "11px", fontWeight: 800, color: "var(--crimson)", display: "flex", justifyContent: "space-between" }}>
                <span>▼ Top Losers</span>
                <span style={{ fontSize: "9px", color: "var(--text-muted)" }}>NIFTY 500</span>
              </div>
              {data.movers.losers.slice(0, 10).map((st) => (
                <div
                  key={st.symbol}
                  onClick={() => onAnalyzeTicker(st.symbol)}
                  onMouseEnter={(e) => {
                    setHoveredStock(st);
                    const rect = e.currentTarget.getBoundingClientRect();
                    setTooltipPos({ x: rect.left + rect.width / 2, y: rect.top - 8 });
                  }}
                  onMouseLeave={() => setHoveredStock(null)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "3px 6px",
                    borderRadius: "4px",
                    background: "rgba(0,0,0,0.25)",
                    cursor: "pointer",
                    fontSize: "10px",
                  }}
                  onMouseOver={(e) => (e.currentTarget.style.background = "rgba(255, 61, 87, 0.15)")}
                  onMouseOut={(e) => (e.currentTarget.style.background = "rgba(0,0,0,0.25)")}
                >
                  <span style={{ fontWeight: 700 }}>{st.symbol}</span>
                  <span style={{ color: "var(--crimson)", fontWeight: 800 }}>{st.change}%</span>
                </div>
              ))}
            </div>

            {/* Volume Leaders */}
            <div
              style={{
                background: "rgba(0, 229, 255, 0.04)",
                border: "1px solid rgba(0, 229, 255, 0.2)",
                borderRadius: "6px",
                padding: "8px",
                display: "flex",
                flexDirection: "column",
                gap: "4px",
                overflowY: "auto",
              }}
            >
              <div style={{ fontSize: "11px", fontWeight: 800, color: "var(--cyan)", display: "flex", justifyContent: "space-between" }}>
                <span>⚡ Volume Leaders</span>
                <span style={{ fontSize: "9px", color: "var(--text-muted)" }}>NIFTY 500</span>
              </div>
              {data.movers.most_active.slice(0, 10).map((st) => (
                <div
                  key={st.symbol}
                  onClick={() => onAnalyzeTicker(st.symbol)}
                  onMouseEnter={(e) => {
                    setHoveredStock(st);
                    const rect = e.currentTarget.getBoundingClientRect();
                    setTooltipPos({ x: rect.left + rect.width / 2, y: rect.top - 8 });
                  }}
                  onMouseLeave={() => setHoveredStock(null)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "3px 6px",
                    borderRadius: "4px",
                    background: "rgba(0,0,0,0.25)",
                    cursor: "pointer",
                    fontSize: "10px",
                  }}
                  onMouseOver={(e) => (e.currentTarget.style.background = "rgba(0, 229, 255, 0.15)")}
                  onMouseOut={(e) => (e.currentTarget.style.background = "rgba(0,0,0,0.25)")}
                >
                  <span style={{ fontWeight: 700 }}>{st.symbol}</span>
                  <span style={{ color: "var(--cyan)", fontWeight: 700 }}>{formatVolume(st.volume)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Bottom Mini Legend Bar */}
      <div
        style={{
          padding: "5px 14px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTop: "1px solid var(--border-subtle)",
          background: "rgba(255,255,255,0.015)",
          fontSize: "9.5px",
          color: "var(--text-muted)",
        }}
      >
        <span>Hover tile for instant metrics & price range • Click to analyze</span>

        {/* Color scale gradient */}
        <div style={{ display: "flex", alignItems: "center", gap: "3px" }}>
          <span>-3%</span>
          <span style={{ width: "10px", height: "6px", borderRadius: "2px", background: "rgba(220, 38, 38, 0.7)" }} />
          <span style={{ width: "10px", height: "6px", borderRadius: "2px", background: "rgba(239, 68, 68, 0.35)" }} />
          <span style={{ width: "10px", height: "6px", borderRadius: "2px", background: "rgba(255, 255, 255, 0.08)" }} />
          <span style={{ width: "10px", height: "6px", borderRadius: "2px", background: "rgba(16, 185, 129, 0.35)" }} />
          <span style={{ width: "10px", height: "6px", borderRadius: "2px", background: "rgba(0, 230, 118, 0.7)" }} />
          <span>+3%</span>
        </div>
      </div>

      {/* High-Contrast Floating Tooltip on Hover */}
      {hoveredStock && (
        <div
          style={{
            position: "fixed",
            left: `${Math.min(Math.max(tooltipPos.x, 110), window.innerWidth - 120)}px`,
            top: `${Math.max(tooltipPos.y, 80)}px`,
            transform: "translate(-50%, -100%)",
            background: "rgba(11, 15, 25, 0.97)",
            backdropFilter: "blur(14px)",
            border: "1px solid rgba(0, 229, 255, 0.4)",
            borderRadius: "8px",
            padding: "8px 12px",
            pointerEvents: "none",
            zIndex: 9999,
            boxShadow: "0 10px 30px rgba(0,0,0,0.75)",
            minWidth: "180px",
            display: "flex",
            flexDirection: "column",
            gap: "3px",
          }}
        >
          {/* Header: Symbol, % Change, Sector */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "12px", fontWeight: 800, color: "var(--cyan)" }}>
              {hoveredStock.symbol}
            </span>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 800,
                color: hoveredStock.change >= 0 ? "var(--emerald)" : "var(--crimson)",
              }}
            >
              {hoveredStock.change > 0 ? "+" : ""}
              {hoveredStock.change}%
            </span>
          </div>

          <div
            style={{
              fontSize: "9.5px",
              color: "var(--text-muted)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: "180px",
            }}
          >
            {hoveredStock.name} • {hoveredStock.sector}
          </div>

          <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", margin: "2px 0" }} />

          {/* Metric Grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "3px", fontSize: "9.5px" }}>
            <div>
              <span style={{ color: "var(--text-muted)" }}>Price: </span>
              <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>
                ₹{hoveredStock.close.toLocaleString()}
              </span>
            </div>
            <div>
              <span style={{ color: "var(--text-muted)" }}>Vol: </span>
              <span style={{ fontWeight: 600 }}>{formatVolume(hoveredStock.volume)}</span>
            </div>
            <div>
              <span style={{ color: "var(--text-muted)" }}>High: </span>
              <span style={{ fontWeight: 600 }}>₹{hoveredStock.high.toLocaleString()}</span>
            </div>
            <div>
              <span style={{ color: "var(--text-muted)" }}>Low: </span>
              <span style={{ fontWeight: 600 }}>₹{hoveredStock.low.toLocaleString()}</span>
            </div>
          </div>

          {/* Mini Range Indicator */}
          {hoveredStock.high > hoveredStock.low && (
            <div style={{ marginTop: "3px" }}>
              <div
                style={{
                  width: "100%",
                  height: "3px",
                  borderRadius: "2px",
                  background: "rgba(255,255,255,0.1)",
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    left: "0",
                    top: "0",
                    bottom: "0",
                    width: `${Math.min(
                      Math.max(
                        ((hoveredStock.close - hoveredStock.low) /
                          (hoveredStock.high - hoveredStock.low)) *
                          100,
                        2
                      ),
                      100
                    )}%`,
                    background: hoveredStock.change >= 0 ? "var(--emerald)" : "var(--crimson)",
                  }}
                />
              </div>
            </div>
          )}

          <div
            style={{
              fontSize: "8.5px",
              color: "var(--cyan)",
              textAlign: "center",
              marginTop: "3px",
              fontWeight: 600,
            }}
          >
            Click to launch Deep Ticker Analysis →
          </div>
        </div>
      )}
    </div>
  );
}
