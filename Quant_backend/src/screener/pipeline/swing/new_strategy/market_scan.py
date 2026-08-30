import os
import sys
import pandas as pd
import numpy as np
import logging

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))))

from src.data.nse_fetcher import fetch_bulk_history, load_nifty500_symbols, load_nifty500_industry_mapping

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT_DIR, exist_ok=True)

def calculate_max_drawdown(series):
    roll_max = series.cummax()
    drawdown = series / roll_max - 1.0
    return drawdown.min()

def run_market_scan():
    logger.info("Loading symbols and mapping...")
    symbols = load_nifty500_symbols()
    if "NIFTYBEES" not in symbols:
        symbols.append("NIFTYBEES")
        
    mapping = load_nifty500_industry_mapping()
    
    logger.info("Fetching bulk history (up to 6 years)...")
    end_date = pd.Timestamp.today().date()
    # Fetch max history available
    bulk_data = fetch_bulk_history(symbols, end_date=end_date, lookback_days=1600)
    
    if "NIFTYBEES" not in bulk_data:
        logger.error("NIFTYBEES data not found.")
        return
        
    nifty = bulk_data["NIFTYBEES"]
    nifty['Return'] = nifty['Close'].pct_change()
    
    # 1M = 21, 3M = 63, 6M = 126, 1Y = 252, 2Y = 504, 3Y = 756, 4Y = 1008, 5Y = 1260, 6Y = 1512
    periods = {
        "1_Month": 21,
        "3_Months": 63,
        "6_Months": 126,
        "1_Year": 252,
        "2_Years": 504,
        "3_Years": 756,
        "4_Years": 1008,
        "5_Years": 1260,
        "All_Time": len(nifty) - 1
    }
    
    results = []
    
    logger.info("Calculating metrics for each time horizon...")
    for period_name, days in periods.items():
        if days >= len(nifty):
            days = len(nifty) - 1
            if days <= 0:
                continue
                
        # Slice benchmark
        nifty_slice = nifty.iloc[-days-1:]
        start_price = nifty_slice['Close'].iloc[0]
        end_price = nifty_slice['Close'].iloc[-1]
        
        bench_ret = (end_price / start_price) - 1.0
        bench_vol = nifty_slice['Return'].std() * np.sqrt(252)
        bench_mdd = calculate_max_drawdown(nifty_slice['Close'])
        
        start_idx = len(nifty) - days - 1
        start_date = nifty.index[start_idx]
        end_date = nifty.index[-1]
        
        # Stock performance
        stock_returns = []
        sectors_perf = {}
        
        for sym, df in bulk_data.items():
            if sym == "NIFTYBEES" or df.empty:
                continue
                
            # Filter for this period
            df_slice = df[df.index >= start_date]
            if len(df_slice) < 2:
                continue
                
            s_price = df_slice['Close'].iloc[0]
            e_price = df_slice['Close'].iloc[-1]
            ret = (e_price / s_price) - 1.0
            stock_returns.append(ret)
            
            ind = mapping.get(sym, "Unknown")
            if ind not in sectors_perf:
                sectors_perf[ind] = []
            sectors_perf[ind].append(ret)
            
        avg_stock_ret = np.mean(stock_returns) if stock_returns else 0
        med_stock_ret = np.median(stock_returns) if stock_returns else 0
        
        sector_avgs = {k: np.mean(v) for k, v in sectors_perf.items() if len(v) >= 3}
        sorted_sectors = sorted(sector_avgs.items(), key=lambda x: x[1], reverse=True)
        
        top_sectors = [f"{k} ({v:.1%})" for k, v in sorted_sectors[:3]] if sorted_sectors else []
        bot_sectors = [f"{k} ({v:.1%})" for k, v in sorted_sectors[-3:]] if sorted_sectors else []
        
        # Determine Regime Label for the period based on Nifty performance
        if bench_ret > 0.10:
            regime = "Strong Bull"
        elif bench_ret > 0:
            regime = "Mild Bull"
        elif bench_ret > -0.10:
            regime = "Choppy/Sideways"
        else:
            regime = "Bear Market"
            
        results.append({
            "Time_Horizon": period_name,
            "Trading_Days": days,
            "Benchmark_Return": f"{bench_ret:.2%}",
            "Benchmark_Vol_Ann": f"{bench_vol:.2%}",
            "Benchmark_Max_DD": f"{bench_mdd:.2%}",
            "Avg_Stock_Return": f"{avg_stock_ret:.2%}",
            "Median_Stock_Return": f"{med_stock_ret:.2%}",
            "Top_Sectors": " | ".join(top_sectors),
            "Bottom_Sectors": " | ".join(bot_sectors),
            "Regime": regime
        })
        
    df_results = pd.DataFrame(results)
    
    csv_path = os.path.join(OUT_DIR, "market_scan_report.csv")
    df_results.to_csv(csv_path, index=False)
    logger.info(f"Report saved to {csv_path}")
    
    md_path = os.path.join(OUT_DIR, "market_scan_summary.md")
    with open(md_path, "w") as f:
        f.write("# Deep Market Scan Summary\n\n")
        f.write("This report provides a multi-timeframe analysis of the Indian Market (Nifty 500) to identify structural trends, volatility regimes, and sector rotations.\n\n")
        f.write(df_results.to_markdown(index=False))
        
    logger.info(f"Markdown summary saved to {md_path}")

if __name__ == "__main__":
    run_market_scan()
