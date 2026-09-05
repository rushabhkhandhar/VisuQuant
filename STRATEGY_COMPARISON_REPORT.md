# Comprehensive Strategy Benchmark: The 4-Year Modern Market Regime
**Account Size**: ₹1,00,000 (1 Lakh Initial Capital)  
**Primary Horizon Tested**: 2022-09-06 to 2026-09-04 (1,032 Trading Days / 4.0 Years)  
**Recent 2-Year Holdout**: 2024-08-26 to 2026-09-04 (518 Trading Days / 2.0 Years)  
**Friction**: 0.15% per leg (0.30% roundtrip)  
**Max Position Allocation**: 20% of equity (₹20,000 max per position at initial capital)  
**Max Holding Period**: 25 trading sessions  

---

## 1. Executive Summary: Why We Focus on the Last 4 Years (2022–2026)

The 2020–2021 period was an artificial, post-COVID global zero-interest-rate environment where liquidity rocketed virtually all breakouts into parabolic runners. Evaluating algorithms over 6 years distorts real-world expectancy by over-weighting a market regime that will never repeat.

In contrast, the **last 4 years (September 2022 to September 2026)** represent the **modern post-rate-hike reality**:
- Highly rotational sector leadership.
- Extended periods of broad market consolidation (NIFTY was **-2.00%** over the last 2 years).
- Frequent sharp pullbacks and false breakouts.

Across this modern 4-year horizon, our benchmark evaluated whether regime-sensitive profit mechanisms and capital velocity rules could solve trade decay in flat markets.

### The Breakthrough: `E19_Dead_Money_Cut`
By introducing a **15-Session Dead-Money Exit** in sideways chop ($\text{BCR} \le 0.52$), where positions that have made $\le 0\%$ after 3 weeks are cut early while profitable runners are permitted to hold the full 25 sessions:
- **Max Drawdown plummeted from -16.78% to -10.66%** (and **-9.90%** in the 2-year holdout).
- **Calmar Ratio surged from 2.442 to 3.735**.
- **Monthly Win Rate jumped from 62.50% to 70.83%** (more than 7 out of 10 months are positive).
- **Recent 2-Year Return (2024–2026) increased from +47.85% to +62.05%** (outperforming the original Champion by +14.2% while reducing drawdowns by 41%).

---

## 2. Official 4-Year Strategy Tear Sheet (2022–2026)

*Source file: [`Quant_backend/front_testing/strategy_tear_sheet.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/strategy_tear_sheet.csv)*

| Architecture | Net Profit (₹) on 1L | CAGR (%) | Net Avg Monthly Ret (%) | Compounded Monthly Ret (%) | Monthly Win Rate (%) | Worst Month (%) | Max DD (%) | Sharpe | Sortino | Calmar | Win Rate (%) | Trades | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 🛡️ **E19_Dead_Money_Cut (Optimal Velocity)** | **₹2,94,613.11** | **39.82%** | **3.06%** | **2.90%** | **70.83%** | **-4.93%** | **-10.66%** | **2.373** | **3.334** | **3.735** | 50.92% | 273 | **2.237** |
| 🚀 **E19_Dual_AVWAP_Confluence (Original Champion)** | **₹3,08,092.38** | **40.97%** | **3.14%** | **2.97%** | 62.50% | -5.74% | -16.78% | **2.458** | **3.468** | 2.442 | **54.79%** | 261 | 2.236 |
| 🎯 **E19_Adaptive_Target_3ATR** | ₹2,63,270.98 | 37.03% | 2.86% | 2.72% | 66.67% | -4.74% | -13.91% | 2.274 | 3.272 | 2.661 | 55.51% | 263 | 2.151 |
| 🔒 **E19_Adaptive_Regime_Lock (Defensive Shield)** | ₹2,20,470.46 | 32.89% | 2.61% | 2.46% | 64.58% | -5.34% | -12.73% | 2.101 | 2.909 | 2.585 | 51.80% | 278 | 2.071 |
| 🥈 **E19_Baseline_Unfiltered** | ₹2,08,467.06 | 31.66% | 2.56% | 2.37% | 64.58% | -5.83% | -13.89% | 1.920 | 2.550 | 2.279 | 51.67% | 269 | 1.925 |

---

## 3. The 2-Year Trend Shift Autopsy & Holdout Validation (2024–2026)

*Source file: [`Quant_backend/front_testing/validation_report.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/validation_report.csv)*

| Architecture | Period | NIFTY Ret | Total Ret (%) | CAGR (%) | Net Avg Monthly Ret (%) | Monthly Win Rate (%) | Max Drawdown (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **E19_Dead_Money_Cut** | **In-Sample (2022–2024)** | +44.20% | **+140.69%** | 56.43% | 4.12% | **73.91%** | **-10.66%** |
| **E19_Dead_Money_Cut** | **Holdout (2024–2026)** | **-2.00%** | **+62.05%** | **26.95%** | **2.03%** | **68.00%** | **-9.90%** |
| E19_Dual_AVWAP_Confluence | In-Sample (2022–2024) | +44.20% | +174.62% | 67.30% | 4.70% | 69.57% | -10.98% |
| E19_Dual_AVWAP_Confluence | Holdout (2024–2026) | -2.00% | +47.85% | 21.32% | 1.63% | 56.00% | -16.78% |
| E19_Baseline_Unfiltered | In-Sample (2022–2024) | +44.20% | +92.80% | 39.71% | 3.17% | 65.22% | -9.44% |
| E19_Baseline_Unfiltered | Holdout (2024–2026) | -2.00% | +59.79% | 26.07% | 1.97% | 64.00% | -13.89% |

### Why `Dead Money Cut` Outperforms:
1. **Prevents Capital Asphyxiation**: In the flat 2024–2026 market, 22 trades were identified as dead money and exited after 15 sessions with an average loss of only **-1.82%** (instead of holding another 10 sessions and decaying into -5.5% full stop-losses).
2. **Frees Slots for Winners**: Because dead trades were liquidated at session 15, the portfolio had cash available to enter high-conviction breakout setups. Winning trades in holdout increased from 34 to **39 Wins**.
3. **Does Not Choke Right Tail**: Unlike rigid profit locks that capped targets at $3.0\times$ ATR or locked breakeven prematurely, `Dead Money Cut` preserves the full $4.0\times$ ATR target for any trade showing positive momentum.

---

## 4. Verification Files in the Project Directory

All raw 4-year backtest results, trade logs, and monthly matrices are saved directly in `Quant_backend/front_testing/`:

1. **Overall Tear Sheet**: [`Quant_backend/front_testing/strategy_tear_sheet.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/strategy_tear_sheet.csv)
2. **Monthly Returns Matrix**: [`Quant_backend/front_testing/monthly_returns_breakdown.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/monthly_returns_breakdown.csv)
3. **Validation Report**: [`Quant_backend/front_testing/validation_report.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/validation_report.csv)
4. **Equity Curves (Daily 4-Year)**: [`Quant_backend/front_testing/strategy_equity_curves.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/strategy_equity_curves.csv)
5. **E19 Dead Money Cut Trade Log**: [`Quant_backend/front_testing/E19_Dead_Money_Cut_backtest_trades.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/E19_Dead_Money_Cut_backtest_trades.csv)
6. **E19 Dual AVWAP Trade Log**: [`Quant_backend/front_testing/E19_Dual_AVWAP_Confluence_backtest_trades.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/E19_Dual_AVWAP_Confluence_backtest_trades.csv)
7. **Run Configuration JSON**: [`Quant_backend/front_testing/backtest_run_config.json`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/backtest_run_config.json)
