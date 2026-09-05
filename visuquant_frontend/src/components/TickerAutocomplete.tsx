"use client";

import React, { useState, useEffect, useRef } from "react";

interface TickerAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
  onSelect?: (value: string) => void;
  placeholder?: string;
  className?: string;
  style?: React.CSSProperties;
  disabled?: boolean;
}

export default function TickerAutocomplete({
  value,
  onChange,
  onSelect,
  placeholder = "e.g. TCS",
  className = "quant-input font-mono",
  style,
  disabled = false,
}: TickerAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Debounced fetch for matching symbols
  useEffect(() => {
    if (!value || !value.trim()) {
      setSuggestions([]);
      return;
    }

    const timer = setTimeout(() => {
      fetch(`http://localhost:5000/api/search_symbols?q=${encodeURIComponent(value.trim())}`)
        .then((res) => res.json())
        .then((data) => {
          if (data && data.symbols) {
            setSuggestions(data.symbols);
          }
        })
        .catch(() => {
          setSuggestions([]);
        });
    }, 150);

    return () => clearTimeout(timer);
  }, [value]);

  const handleSelect = (sym: string) => {
    onChange(sym);
    if (onSelect) onSelect(sym);
    setIsOpen(false);
    setHighlightedIndex(-1);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || suggestions.length === 0) {
      if (e.key === "ArrowDown" && suggestions.length > 0) {
        setIsOpen(true);
        setHighlightedIndex(0);
        e.preventDefault();
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : suggestions.length - 1));
    } else if (e.key === "Enter") {
      if (highlightedIndex >= 0 && highlightedIndex < suggestions.length) {
        e.preventDefault();
        handleSelect(suggestions[highlightedIndex]);
      }
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  };

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
      <input
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value.toUpperCase());
          setIsOpen(true);
        }}
        onFocus={() => {
          if (value.trim().length > 0) {
            setIsOpen(true);
          }
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        className={className}
        style={{
          width: "100%",
          textTransform: "uppercase",
          fontWeight: 700,
          ...style,
        }}
        autoComplete="off"
        spellCheck="false"
      />

      {/* Floating Autocomplete Dropdown */}
      {isOpen && value.trim().length > 0 && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            marginTop: "6px",
            background: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-medium)",
            borderRadius: "8px",
            boxShadow: "0 12px 28px rgba(0, 0, 0, 0.4)",
            zIndex: 1000,
            maxHeight: "240px",
            overflowY: "auto",
          }}
        >
          {suggestions.length > 0 ? (
            suggestions.map((sym, idx) => {
              const isHighlighted = idx === highlightedIndex;
              return (
                <div
                  key={sym}
                  onMouseDown={(e) => {
                    e.preventDefault(); // Prevent blur before select
                    handleSelect(sym);
                  }}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                  style={{
                    padding: "9px 14px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    background: isHighlighted ? "var(--border-glass)" : "transparent",
                    cursor: "pointer",
                    borderBottom: "1px solid var(--border-subtle)",
                    transition: "background 0.12s ease",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontWeight: 700,
                      fontSize: "13px",
                      color: isHighlighted ? "var(--cyan)" : "var(--text-primary)",
                    }}
                  >
                    {sym}
                  </span>
                  <span
                    className="badge badge-cyan font-mono"
                    style={{ fontSize: "9px", padding: "2px 6px" }}
                  >
                    NSE
                  </span>
                </div>
              );
            })
          ) : (
            <div
              style={{
                padding: "12px 14px",
                fontSize: "12px",
                color: "var(--crimson)",
                textAlign: "center",
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              No matching NSE/BSE symbols
            </div>
          )}
        </div>
      )}
    </div>
  );
}
