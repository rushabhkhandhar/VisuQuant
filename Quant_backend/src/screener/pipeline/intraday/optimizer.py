import os
import sys
import logging
from datetime import date
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from src.screener.pipeline.intraday.config import STRATEGY_CONFIG
from src.screener.pipeline.intraday.backtest_engine import BacktestEngine
from src.data.nse_fetcher import load_nifty100_symbols, fetch_bulk_history
from src.data.live_tv_fetcher import get_tv_fetcher
from tvDatafeed import Interval
from src.screener.pipeline.intraday.features import calculate_vwap

# Suppress noisy logs
logging.getLogger("src.screener.pipeline.intraday.backtest_engine").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def fetch_data():
    logger.info("Fetching static dataset for optimization loop...")
    symbols = load_nifty100_symbols()
    daily_data = fetch_bulk_history(symbols + ["NIFTY"], end_date=date.today(), lookback_days=100)
    
    CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "bhavcopy_cache", "intraday_5m")
    intraday_data = {}
    fetcher = get_tv_fetcher()
    
    for sym in (symbols + ["NIFTY"]):
        cache_path = os.path.join(CACHE_DIR, f"{sym}_5m.parquet")
        if os.path.exists(cache_path):
            try:
                df = pd.read_parquet(cache_path)
                if not df.empty:
                    intraday_data[sym] = df
            except:
                pass
                
    nifty_i = intraday_data.get("NIFTY")
    nifty_vwap_df = calculate_vwap(nifty_i)
    unique_dates = pd.Series(nifty_i.index.date).unique()[20:]
    
    return daily_data, intraday_data, nifty_i, nifty_vwap_df, unique_dates

def run_optimizer():
    daily_data, intraday_data, nifty_i, nifty_vwap_df, valid_dates = fetch_data()
    
    # Grid of parameters to test
    scores_to_test = [10, 13, 16]
    targets_to_test = [1.5, 2.0, 2.5]
    atr_multipliers = [0.5, 1.0, 1.5]
    
    results = []
    
    total_runs = len(scores_to_test) * len(targets_to_test) * len(atr_multipliers)
    run = 1
    
    for score in scores_to_test:
        for tgt in targets_to_test:
            for atr_mult in atr_multipliers:
                logger.info(f"[{run}/{total_runs}] Testing Config: Score>={score}, Target={tgt}R, SL={atr_mult}x ATR")
                
                # Clone config
                test_config = STRATEGY_CONFIG.copy()
                test_config['min_score'] = score
                test_config['target_r_multiple'] = tgt
                test_config['atr_multiplier'] = atr_mult
                
                engine = BacktestEngine(test_config)
                
                # Run simulate manually to bypass the built-in run() which fetches data
                all_trades = []
                for d in valid_dates:
                    day_trades = engine.simulate_day(d, daily_data, intraday_data, nifty_i, nifty_vwap_df)
                    day_trades = sorted(day_trades, key=lambda x: x['Score'], reverse=True)[:test_config['max_trades_per_day']]
                    for t in day_trades:
                        engine.capital += t['Net_PnL']
                    all_trades.extend(day_trades)
                    
                df = pd.DataFrame(all_trades)
                if df.empty:
                    win_rate = 0
                    net_pnl = 0
                    total_trades = 0
                else:
                    win_rate = (df['Net_PnL'] > 0).mean() * 100
                    net_pnl = df['Net_PnL'].sum()
                    total_trades = len(df)
                    
                results.append({
                    "Score": score,
                    "Target_R": tgt,
                    "ATR_SL": atr_mult,
                    "Trades": total_trades,
                    "Win_Rate": win_rate,
                    "Net_PnL": net_pnl
                })
                run += 1
                
    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values(by="Net_PnL", ascending=False)
    print("\n\n=== TOP 10 CONFIGURATIONS ===")
    print(df_res.head(10).to_string(index=False))

if __name__ == "__main__":
    run_optimizer()
