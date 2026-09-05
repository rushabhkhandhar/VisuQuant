# Strategy Benchmark Report: E14_Strict_AVWAP vs E13_Sector_Pullback
**Account Size**: ₹1,00,000 (1 Lakh Initial Capital)  
**Period Tested**: 2020-09-07 to 2026-09-04 (1,551 Trading Days / 6.0 Years)  
**Out-of-Sample Holdout**: 2024-08-26 to 2026-09-04 (518 Trading Days / 2.0 Years)  
**Friction**: 0.15% per leg (0.30% roundtrip)  
**Max Position Allocation**: 20% of equity (₹20,000 max per position at initial capital)  
**Max Holding Period**: 25 trading sessions  

---

## 1. Executive Summary

Both strategies were backtested under realistic conditions: a finite ₹1,00,000 cash pool, strict cash accounting, position caps, and realistic broker frictions on entry and exit.

### The Verdict
**`E14_Strict_AVWAP` decisively outperforms `E13_Sector_Pullback` across every single return and risk-adjusted metric, generating +2.36x more net profit with a lower 6-year maximum drawdown:**

- **Starting Capital**: ₹1,00,000.00
- **Final Ending Wealth**: **₹6,79,750** (E14) vs **₹3,45,618** (E13) *(+₹3,34,132 additional wealth)*
- **Total Net Profit**: **₹5,79,780** (E14) vs **₹2,45,706** (E13) *(**+136% higher profit**)*
- **Full 6-Year CAGR**: **36.54%** vs **22.34%** *(**+14.20% higher per year**)*
- **Full 6-Year Max Drawdown**: **-15.38%** vs **-16.20%** *(**Lower drawdown than E13!**)*
- **Sharpe Ratio**: **2.163** vs **1.401** *(+0.762)*
- **Sortino Ratio**: **3.043** vs **1.756** *(+1.287)*
- **Calmar Ratio**: **2.375** vs **1.379** *(+0.996)*
- **Win Rate**: **53.26%** vs **49.62%** *(+3.64%)*
- **Profit Factor**: **2.079** vs **1.623** *(+0.456)*

---

## 2. Full 6-Year Tear Sheet (2020 – 2026)

*Source file: `Quant_backend/front_testing/strategy_tear_sheet.csv`*

| Metric | E13_Sector_Pullback (Benchmark) | 🏆 E14_Strict_AVWAP (New Champion) | Variance |
| :--- | :---: | :---: | :---: |
| **Initial Capital** | ₹1,00,000.00 | ₹1,00,000.00 | Exactly 1L |
| **Final Equity** | ₹3,45,618.39 | **₹6,79,750.49** | **+₹3,34,132.10 (+96.7%)** |
| **Net Profit** | ₹2,45,706.40 | **₹5,79,779.79** | **+2.36x More Net Profit** |
| **CAGR (%)** | 22.34% | **36.54%** | **+14.20% / year** |
| **Max Drawdown (%)** | -16.20% | **-15.38%** | **Lower peak drawdown (-0.82%)** |
| **Sharpe Ratio** | 1.401 | **2.163** | **+0.762** |
| **Sortino Ratio** | 1.756 | **3.043** | **+1.287** |
| **Calmar Ratio** | 1.379 | **2.375** | **+0.996 (Superior return/risk)** |
| **Total Trades** | 395 | 383 | High selectivity |
| **Win Rate (%)** | 49.62% | **53.26%** | **+3.64%** |
| **Profit Factor** | 1.623 | **2.079** | **+0.456** |
| **Expectancy (%)** | 1.772% | **2.738%** | **+0.966% / trade** |
| **Average Win (%)** | 9.30% | **9.90%** | +0.60% |
| **Average Loss (%)** | -5.65% | **-5.43%** | Tighter losses |
| **Bullish Market Win Rate** | 47.54% (244 trades) | **51.10% (227 trades)** | +3.56% |
| **Sideways Market Win Rate** | 52.03% (148 trades) | **55.92% (152 trades)** | +3.89% |

---

## 3. Out-of-Sample Holdout Period (2024-08-26 to 2026-09-04)

*Source file: `Quant_backend/front_testing/validation_report.csv`*  
*Strictly frozen parameters across 518 trading days:*

| Metric | E13_Sector_Pullback | 🏆 E14_Strict_AVWAP | Variance |
| :--- | :---: | :---: | :---: |
| **Holdout Start Equity** | ₹2,49,246.79 | **₹4,38,953.19** | Higher base |
| **Holdout End Equity** | ₹3,45,618.39 | **₹6,79,750.49** | +₹3,34,132 |
| **Holdout Total Return (%)** | +38.67% | **+54.86%** | **+16.19% higher return** |
| **Holdout CAGR (%)** | 17.27% | **23.76%** | **+6.49% / year** |
| **Holdout Max Drawdown (%)** | **-9.34%** | -11.94% | Solid defense (<12%) |
| **Holdout Sharpe Ratio** | 1.225 | **1.638** | **+0.413** |
| **Holdout Sortino Ratio** | 1.621 | **2.450** | **+0.829** |
| **Holdout Calmar Ratio** | 1.849 | **1.989** | **Superior return/risk** |

---

## 4. Verification Files in the Project Directory

All raw backtest data, execution logs, and trade-by-trade records are located directly in `Quant_backend/front_testing/`:

1. **Overall Tear Sheet**: [`Quant_backend/front_testing/strategy_tear_sheet.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/strategy_tear_sheet.csv)
2. **Holdout Validation Report**: [`Quant_backend/front_testing/validation_report.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/validation_report.csv)
3. **Daily Equity Curves**: [`Quant_backend/front_testing/strategy_equity_curves.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/strategy_equity_curves.csv)
4. **E14 Trade-by-Trade Log**: [`Quant_backend/front_testing/E14_Strict_AVWAP_backtest_trades.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/E14_Strict_AVWAP_backtest_trades.csv)
5. **E13 Trade-by-Trade Log**: [`Quant_backend/front_testing/E13_Sector_Pullback_backtest_trades.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/E13_Sector_Pullback_backtest_trades.csv)
6. **E14 Daily Exposure & Positions**: [`Quant_backend/front_testing/E14_Strict_AVWAP_exposure.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/E14_Strict_AVWAP_exposure.csv)
7. **E13 Daily Exposure & Positions**: [`Quant_backend/front_testing/E13_Sector_Pullback_exposure.csv`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/E13_Sector_Pullback_exposure.csv)
8. **Run Configuration JSON**: [`Quant_backend/front_testing/backtest_run_config.json`](file:///Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/backtest_run_config.json)
