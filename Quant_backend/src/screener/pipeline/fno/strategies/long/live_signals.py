import os
import sys
import logging
from datetime import date
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))))

from src.data.nse_fetcher import load_fno_symbols, load_nifty500_industry_mapping
from src.data.live_tv_fetcher import get_tv_fetcher
from src.screener.pipeline.fno.strategies.long.config_fno import STRATEGY_CONFIG
from src.screener.pipeline.fno.strategies.long.screener import FnoLongScreener
from src.screener.pipeline.intraday.features import calculate_atr

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_live_signals():
    logger.info("Initializing F&O Long Live Signal Generator...")
    
    symbols = load_fno_symbols()
    ind_map = load_nifty500_industry_mapping()
    
    today = date.today()
    logger.info(f"Fetching REAL-TIME live data from TradingView for {today}...")
    
    # Use the live TV fetcher to get real-time daily candles at 3:15 PM
    fetcher = get_tv_fetcher()
    cash_data = fetcher.fetch_bulk_live(symbols + ["NIFTY"], n_bars=100, max_workers=10)
    
    screener = FnoLongScreener(STRATEGY_CONFIG)
    picks = screener.screen(today, cash_data, ind_map)
    
    if not picks:
        logger.info("MARKET REGIME OR SETUP BLOCK: No valid Long signals generated for today.")
        return
        
    logger.info(f"Top {len(picks)} Strongest F&O Setup(s) Found: {picks}")
    
    signals = []
    
    for sym in picks:
        df = cash_data.get(sym)
        if df is None or df.empty:
            continue
            
        # The entry price is the current market price (last closed candle)
        current_price = df['Close'].iloc[-1]
        
        # Calculate Stop Loss using ATR
        atr = calculate_atr(df, period=STRATEGY_CONFIG['atr_period'])
        
        stop_loss = current_price - (atr * STRATEGY_CONFIG['atr_stop_loss_multiplier'])
        risk = current_price - stop_loss
        target = current_price + (risk * STRATEGY_CONFIG['target_r_multiple'])
        
        signals.append({
            "Date": today.strftime("%Y-%m-%d"),
            "Symbol": sym,
            "Action": "BUY",
            "Instrument": "Current Month Futures",
            "Entry_Price_Proxy": round(current_price, 2),
            "Stop_Loss": round(stop_loss, 2),
            "Target": round(target, 2),
            "Risk_Per_Share": round(risk, 2)
        })
        
    sig_df = pd.DataFrame(signals)
    
    print("\n" + "="*50)
    print(f"🔥 LIVE SIGNALS FOR: {today} 🔥")
    print("="*50)
    if sig_df.empty:
        print("No valid signals could be generated due to missing data.")
    else:
        print(sig_df.to_markdown(index=False))
    print("="*50 + "\n")
    
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "daily_signals.csv")
    
    sig_df.to_csv(out_path, index=False)
    logger.info(f"Signals saved to {out_path}")

if __name__ == "__main__":
    generate_live_signals()
