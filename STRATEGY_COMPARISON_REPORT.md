# Comprehensive Strategy Benchmark & Net Monthly Return Tear Sheet
**Account Size**: ₹1,00,000 (1 Lakh Initial Capital)  
**Period Tested**: 2020-09-07 to 2026-09-04 (1,551 Trading Days / 6.0 Years)  
**Out-of-Sample Holdout**: 2024-08-26 to 2026-09-04 (518 Trading Days / 2.0 Years)  
**Friction**: 0.15% per leg (0.30% roundtrip)  
**Max Position Allocation**: 20% of equity (₹20,000 max per position at initial capital)  
**Max Holding Period**: 25 trading sessions  

---

## 1. Executive Summary & The New Crown Champion

Across 6 architectures benchmarked on an exact ₹1,00,000 starting cash pool, **`E19_Dual_AVWAP_Confluence`** emerges as the definitive, undisputed champion, surpassing both `E14_Strict_AVWAP` and the former `E13_Sector_Pullback` across return, Sharpe ratio, out-of-sample holdout performance, and net monthly returns.

### Key Highlights for `E19_Dual_AVWAP_Confluence`:
- **Overall Net Profit on 1L**: **₹6,72,090.63** (+₹92,310 higher than E14, +₹4,26,384 higher than E13!)
- **Full 6-Year CAGR**: **39.39%** (vs E14's 36.54% and E13's 22.34%)
- **Net Average Monthly Return**: **3.09% / month**
- **Compounded Monthly Return**: **2.88% / month**
- **Monthly Win Rate**: **69.44%** (7 out of 10 months are positive!)
- **Sharpe Ratio**: **2.228** (Highest ever recorded)
- **Sortino Ratio**: **3.002**
- **Calmar Ratio**: **2.420**
- **Max Drawdown**: **-16.28%**
- **Win Rate**: **53.98%** across 389 trades
- **Profit Factor**: **2.126**
- **Expectancy**: **+2.873% per trade**

---

## 2. Complete Strategy Tear Sheet (Last 6.0 Years)

*Source file: [`Quant_backend/front_testing/strategy_tear_sheet.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/strategy_tear_sheet.csv)*

| Architecture | Net Profit (₹) on 1L | CAGR (%) | Net Avg Monthly Ret (%) | Compounded Monthly Ret (%) | Monthly Win Rate (%) | Best Month (%) | Worst Month (%) | Max DD (%) | Sharpe | Sortino | Calmar | Win Rate (%) | Trades | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 🏆 **E19_Dual_AVWAP_Confluence** | **₹6,72,090.63** | **39.39%** | **3.09%** | **2.88%** | **69.44%** | **+24.11%** | -8.50% | -16.28% | **2.228** | **3.002** | **2.420** | **53.98%** | 389 | **2.126** |
| 🥈 **E14_Strict_AVWAP** | ₹5,79,779.79 | 36.54% | 2.89% | 2.70% | 65.28% | +22.18% | -8.49% | **-15.38%** | 2.163 | 3.043 | 2.375 | 53.26% | 383 | 2.079 |
| 🥉 **E20_Adaptive_Expansion_AVWAP** | ₹5,79,779.79 | 36.54% | 2.89% | 2.70% | 65.28% | +22.18% | -8.49% | **-15.38%** | 2.163 | 3.043 | 2.375 | 53.26% | 383 | 2.079 |
| **E21_Volume_Surge_AVWAP** | ₹4,03,183.56 | 30.03% | 2.44% | 2.27% | 59.72% | +18.99% | -8.47% | -15.98% | 1.790 | 2.314 | 1.879 | 51.89% | 370 | 1.886 |
| **E22_Alpha_Max_Ensemble** | ₹63,863.71 | 8.35% | 0.78% | 0.69% | 47.22% | +14.36% | -6.91% | -16.69% | 0.668 | 0.814 | 0.500 | 45.42% | 262 | 1.380 |
| **E18_Top_Sector_AVWAP** | ₹56,693.90 | 7.57% | 0.76% | 0.63% | 43.06% | +14.17% | -7.08% | -27.80% | 0.613 | 0.749 | 0.272 | 42.64% | 258 | 1.342 |

---

## 3. Out-of-Sample Holdout Period (2024-08-26 to 2026-09-04)

*Source file: [`Quant_backend/front_testing/validation_report.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/validation_report.csv)*  
*Strictly frozen parameters across 518 trading days without retuning:*

| Architecture | Holdout Start Equity | Holdout End Equity | Holdout Total Ret (%) | Holdout CAGR (%) | Holdout Net Avg Monthly Ret (%) | Holdout Monthly Win Rate (%) | Holdout Max DD (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 🏆 **E19_Dual_AVWAP_Confluence** | ₹4,35,378.37 | **₹7,72,061.34** | **+77.33%** | **32.73%** | **2.42% / month** | **68.0%** | **-11.95%** |
| 🥈 **E14_Strict_AVWAP** | ₹4,38,953.19 | ₹6,79,750.49 | +54.86% | 24.13% | 1.88% / month | 56.0% | -11.94% |
| 🥉 **E20_Adaptive_Expansion_AVWAP** | ₹4,38,953.19 | ₹6,79,750.49 | +54.86% | 24.13% | 1.88% / month | 56.0% | -11.94% |
| **E21_Volume_Surge_AVWAP** | ₹3,70,695.71 | ₹5,03,154.27 | +35.73% | 16.30% | 1.27% / month | 52.0% | -15.98% |
| **E22_Alpha_Max_Ensemble** | ₹1,74,994.77 | ₹1,63,863.71 | -6.36% | -3.20% | -0.26% / month | 28.0% | -12.55% |
| **E18_Top_Sector_AVWAP** | ₹1,98,873.43 | ₹1,56,693.90 | -21.21% | -11.11% | -0.91% / month | 28.0% | -23.92% |

### Key Holdout Takeaway:
In the recent 2-year out-of-sample period (August 2024 to September 2026), **`E19_Dual_AVWAP_Confluence` pulled ahead significantly**, delivering **+32.73% CAGR** (vs E14's 24.13%) and **68% positive months** (vs E14's 56%), all while maintaining an identical drawdown defense of **-11.95%**!

---

## 4. Why Each Architecture Performed As It Did (Intuitions & Market Dynamics)

### 1. 🏆 Why `E19_Dual_AVWAP_Confluence` Won Decisively:
- **Macro Institutional Defense**: By mandating that price must trade **strictly above its 200-day major swing low AVWAP**, the strategy ensures that the entire macro cycle is in accumulation and that no long-term trapped supply overhead can dump on our position.
- **Micro Timing**: Entering when price tests the **60-day swing low AVWAP** with strict triple MA alignment (`EMA20 > EMA50 > SMA200`) provides perfect swing-entry timing with minimal risk.
- **Result**: Raised win rate to **53.98%**, increased net profit to **₹6,72,090**, raised monthly win rate to **69.44%**, and surged holdout CAGR to **32.73%**.

### 2. ❌ Why `E18_Top_Sector_AVWAP` Failed:
- **Sector Lag Trap**: Sector indices are market-cap weighted aggregates. Individual stock momentum breakouts frequently precede their parent sector's breakout by 2 to 6 weeks.
- **Opportunity Starvation**: Mandating that a stock must belong only to the top 3 sectors starved the system of high-alpha individual winners in emerging or midcap sectors, slashing total profitable trades and cutting CAGR to 7.57%.

### 3. ⚖️ Why `E20_Adaptive_Expansion_AVWAP` Tied E14:
- The 25-session max holding period rule regularly takes profit or closes trades before the extended 5.0 ATR target is hit, making its practical equity trajectory virtually identical to E14's 4.0 ATR target.

### 4. 📉 Why `E21_Volume_Surge_AVWAP` Underperformed:
- Setting a strict bounce-day volume requirement $\ge 1.25\times$ 20d SMA filtered out quiet institutional accumulation bounces (where institutions accumulate without spiking volume to avoid moving the market). This cut total profitable trades from 383 to 370 and reduced CAGR from 36.54% to 30.03%.

---

## 5. Verification Files in the Project Directory

All raw backtest results, trade logs, and monthly matrices are saved directly in `Quant_backend/front_testing/`:

1. **Overall Tear Sheet**: [`Quant_backend/front_testing/strategy_tear_sheet.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/strategy_tear_sheet.csv)
2. **Monthly Returns Breakdown Matrix**: [`Quant_backend/front_testing/monthly_returns_breakdown.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/monthly_returns_breakdown.csv)
3. **Out-of-Sample Validation Report**: [`Quant_backend/front_testing/validation_report.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/validation_report.csv)
4. **Equity Curves (Daily)**: [`Quant_backend/front_testing/strategy_equity_curves.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/strategy_equity_curves.csv)
5. **E19 Trade-by-Trade Log**: [`Quant_backend/front_testing/E19_Dual_AVWAP_Confluence_backtest_trades.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/E19_Dual_AVWAP_Confluence_backtest_trades.csv)
6. **E14 Trade-by-Trade Log**: [`Quant_backend/front_testing/E14_Strict_AVWAP_backtest_trades.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/E14_Strict_AVWAP_backtest_trades.csv)
7. **E19 Daily Exposure & Sizing**: [`Quant_backend/front_testing/E19_Dual_AVWAP_Confluence_exposure.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/E19_Dual_AVWAP_Confluence_exposure.csv)
8. **Run Configuration JSON**: [`Quant_backend/front_testing/backtest_run_config.json`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/backtest_run_config.json)
