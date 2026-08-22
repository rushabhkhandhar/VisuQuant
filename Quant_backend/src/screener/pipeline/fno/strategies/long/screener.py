import os
import sys
import logging
import pandas as pd
from datetime import date
from typing import Dict, List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))))

from src.data.nse_fetcher import fetch_bulk_history, load_fno_symbols, load_nifty500_industry_mapping
from src.screener.pipeline.fno.strategies.long.config_cash import STRATEGY_CONFIG

logger = logging.getLogger(__name__)

class FnoLongScreener:
    def __init__(self, config):
        self.config = config
        
    def calculate_returns(self, df: pd.DataFrame, periods: int) -> float:
        if len(df) < periods:
            return 0.0
        start_price = df['Close'].iloc[-periods]
        end_price = df['Close'].iloc[-1]
        return ((end_price - start_price) / start_price) * 100.0
        
    def screen(self, target_date: date, daily_data: Dict[str, pd.DataFrame], industry_map: Dict[str, str]) -> List[str]:
        """
        Returns the list of strongest F&O stocks within the strongest sectors on the target_date.
        """
        # 1. Calculate Market Regime (Breadth) & stock momentum
        stock_returns = {}
        sector_returns = {}
        stocks_above_50sma = 0
        total_valid_stocks = 0
        
        for sym, df in daily_data.items():
            if sym == "NIFTY": continue
            
            # Slice up to target date
            slice_df = df[df.index.date <= target_date]
            if len(slice_df) < 50: continue
            
            # Market Breadth check
            sma50 = slice_df['Close'].rolling(50).mean().iloc[-1]
            if slice_df['Close'].iloc[-1] > sma50:
                stocks_above_50sma += 1
            total_valid_stocks += 1
            
            ret = self.calculate_returns(slice_df, self.config['sector_momentum_lookback'])
            stock_returns[sym] = ret
            
            ind = industry_map.get(sym, "Unknown")
            if ind not in sector_returns:
                sector_returns[ind] = []
            sector_returns[ind].append(ret)
            
        # Regime Filter: If < 50% of F&O stocks are above their 50 SMA, we are in a Bear Market. Block all longs.
        if total_valid_stocks > 0:
            breadth_pct = stocks_above_50sma / total_valid_stocks
            if breadth_pct < 0.50:
                logger.debug(f"Bear Market Regime detected (Breadth {breadth_pct:.1%}). Blocking long trades.")
                return []
            
        # 2. Aggregate sector momentum (Median return of constituents)
        sector_momentum = {}
        for ind, rets in sector_returns.items():
            if len(rets) >= 2: # Require at least 2 F&O stocks to form a valid sector proxy
                sector_momentum[ind] = sum(rets) / len(rets)
                
        if not sector_momentum:
            return []
            
        # Sort sectors by strongest first
        strongest_sectors = sorted(sector_momentum.keys(), key=lambda k: sector_momentum[k], reverse=True)[:self.config['top_n_sectors']]
        
        # 3. Find strongest stocks within those sectors
        candidates = []
        for sym, ret in stock_returns.items():
            ind = industry_map.get(sym, "Unknown")
            if ind in strongest_sectors:
                # Basic trend filter: Close > 50 SMA (must be in an uptrend)
                slice_df = daily_data[sym][daily_data[sym].index.date <= target_date]
                if len(slice_df) >= 50:
                    sma50 = slice_df['Close'].rolling(50).mean().iloc[-1]
                    if slice_df['Close'].iloc[-1] > sma50:
                        candidates.append((sym, ret, ind))
                        
        # Sort candidates by strongest first
        candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
        
        # Return top N strongest stocks
        return [c[0] for c in candidates[:self.config['max_open_positions']]]

if __name__ == "__main__":
    from datetime import timedelta
    logging.basicConfig(level=logging.INFO)
    
    symbols = load_fno_symbols()
    ind_map = load_nifty500_industry_mapping()
    
    logger.info("Fetching F&O daily data...")
    daily_data = fetch_bulk_history(symbols, lookback_days=100)
    
    screener = FnoLongScreener(STRATEGY_CONFIG)
    
    # Test on yesterday's date to see what it would have picked
    yesterday = date.today() - timedelta(days=1)
    picks = screener.screen(yesterday, daily_data, ind_map)
    
    logger.info(f"Strongest stocks identified for longing: {picks}")
