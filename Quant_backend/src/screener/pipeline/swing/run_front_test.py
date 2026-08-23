import os
import sys
import json
import csv
import logging
from datetime import date, datetime
import pandas as pd
import numpy as np
import uuid
import talib
from sklearn.linear_model import LinearRegression

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

# from src.screener.pipeline.run_custom_screen import run_custom_screener
from src.data.nse_fetcher import fetch_bulk_history, load_nifty500_symbols, cleanup_cache

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FRONT_TEST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "front_testing")
os.makedirs(FRONT_TEST_DIR, exist_ok=True)

STATE_FILE = os.path.join(FRONT_TEST_DIR, "active_trades.json")
METRICS_FILE = os.path.join(FRONT_TEST_DIR, "metrics.csv")

# Global dict to track benchmark relative strength
BENCHMARK_RETURNS = {"20d": 0.0, "60d": 0.0}

def trend_pullback_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
    
    # 0. NIFTY REGIME FILTER (Avoid longs in market correction)
    if nifty_hist is not None and len(nifty_hist) > 50:
        nifty_ema50 = nifty_hist['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        if nifty_hist['Close'].iloc[-1] < nifty_ema50:
             return {"passed": False, "reasons": ["Nifty below 50 EMA"]}
             
    # 1. LONG-TERM TREND
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    
    ema50_20d_ago = df['Close'].ewm(span=50, adjust=False).mean().iloc[-20]
    close = df['Close'].iloc[-1]
    
    if not (close > sma200 and ema50 > sma200):
        return {"passed": False, "reasons": ["Failed Long-Term Trend"]}
        
    if ema50 <= ema50_20d_ago:
        return {"passed": False, "reasons": ["50 EMA is not rising"]}
        
    # 2. MEDIUM-TERM TREND
    if not (ema20 > ema50):
        return {"passed": False, "reasons": ["Failed Medium-Term Trend"]}
        
    # 4. RSI CONDITION (Slightly relaxed for deeper pullbacks)
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if pd.isna(rsi) or not (40 <= rsi <= 65):
        return {"passed": False, "reasons": ["RSI not between 40 and 65"]}
        
    # 9. VOLATILITY
    atr = talib.ATR(df['High'], df['Low'], df['Close'], timeperiod=14).iloc[-1]
    if pd.isna(atr) or (atr / close) > 0.05:
        return {"passed": False, "reasons": ["High Volatility (ATR > 5%)"]}
        
    # 8. AVOID CHASING
    if close > (ema20 * 1.05):
        return {"passed": False, "reasons": ["Extended > 5% above 20 EMA"]}
        
    # 3. CONTROLLED PULLBACK & 5. SUPPORT & 6. PRICE ACTION
    # We want a pullback near 20 EMA or 50 EMA, and a bullish stabilization.
    # Check if close is near 20 or 50 EMA (within 3%)
    dist_20 = abs(close - ema20) / ema20
    dist_50 = abs(close - ema50) / ema50
    
    if dist_20 > 0.03 and dist_50 > 0.03:
         return {"passed": False, "reasons": ["Not near 20 or 50 EMA Support"]}
         
    # Bullish stabilization: Today's close > Today's open (green candle) and Today's close > Yesterday's high
    if close <= df['Open'].iloc[-1] or close <= df['High'].iloc[-2]:
         return {"passed": False, "reasons": ["No bullish confirmation"]}
         
    # Volume confirmation on the bounce
    vol = df['Volume'].iloc[-1]
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-1]
    if vol < vol_sma20:
        return {"passed": False, "reasons": ["Bounce volume below average"]}
         
    return {"passed": True, "score": 1.0, "trigger_type": "Trend Pullback"}

def momentum_breakout_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
        
    if nifty_hist is not None and len(nifty_hist) >= 60 and len(df) >= 60:
        n_20 = (nifty_hist['Close'].iloc[-1] / nifty_hist['Close'].iloc[-20]) - 1
        n_60 = (nifty_hist['Close'].iloc[-1] / nifty_hist['Close'].iloc[-60]) - 1
        s_20 = (df['Close'].iloc[-1] / df['Close'].iloc[-20]) - 1
        s_60 = (df['Close'].iloc[-1] / df['Close'].iloc[-60]) - 1
        
        if s_20 <= n_20 or s_60 <= n_60:
            return {"passed": False, "reasons": ["Relative Strength vs NIFTY failed"]}
        
    close = df['Close'].iloc[-1]
    
    # 1. LONG-TERM TREND & 2. MEDIUM-TERM TREND
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    
    if not (close > sma200 and ema50 > sma200 and ema20 > ema50):
        return {"passed": False, "reasons": ["Failed Trend Conditions"]}
        
    # VCP (Volatility Contraction Pattern) CHECK
    # Check that the 10-day range before the breakout is tight (< 10%)
    recent_10d_high = df['High'].iloc[-11:-1].max()
    recent_10d_low = df['Low'].iloc[-11:-1].min()
    if recent_10d_low > 0:
        if (recent_10d_high - recent_10d_low) / recent_10d_low > 0.10:
            return {"passed": False, "reasons": ["VCP Failed (Too Volatile Before Breakout)"]}
        
    # 3. RESISTANCE BREAKOUT
    # Calculate the maximum high of the previous 40 trading days (excluding today)
    recent_resistance = df['High'].iloc[-41:-1].max()
    if close <= recent_resistance:
        return {"passed": False, "reasons": ["No Resistance Breakout"]}
        
    # 8. PRICE EXTENSION
    # Do not chase if price is already > 5% above the breakout level
    if close > (recent_resistance * 1.05):
        return {"passed": False, "reasons": ["Excessively Extended Breakout"]}
        
    # 4. BREAKOUT STRENGTH
    high = df['High'].iloc[-1]
    low = df['Low'].iloc[-1]
    day_range = high - low
    if day_range == 0 or ((close - low) / day_range) < 0.6:
        return {"passed": False, "reasons": ["Weak Close (Not near Highs)"]}
        
    # 5. VOLUME CONFIRMATION
    vol = df['Volume'].iloc[-1]
    avg_vol_20 = df['Volume'].rolling(20).mean().iloc[-2] # using past average
    if pd.isna(avg_vol_20) or vol < (2.0 * avg_vol_20):
        return {"passed": False, "reasons": ["Volume < 2.0x Average"]}
        
    # 6. RSI
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if pd.isna(rsi) or rsi < 60:
        return {"passed": False, "reasons": ["RSI not > 60"]}
        
    # 7. MACD
    macd, macdsignal, macdhist = talib.MACD(df['Close'], fastperiod=12, slowperiod=26, signalperiod=9)
    if pd.isna(macd.iloc[-1]) or macd.iloc[-1] < macdsignal.iloc[-1]:
        return {"passed": False, "reasons": ["MACD below Signal Line"]}
        
    # 9. VOLATILITY
    atr = talib.ATR(df['High'], df['Low'], df['Close'], timeperiod=14).iloc[-1]
    # if pd.isna(atr) or (atr / close) > 0.05:
    #     return {"passed": False, "reasons": ["High Volatility (ATR > 5%)"]}


    return {"passed": True, "score": 1.0, "trigger_type": "Momentum Breakout"}

def oversold_uptrend_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
        
    close = df['Close'].iloc[-1]
    open_p = df['Open'].iloc[-1]
    high = df['High'].iloc[-1]
    low = df['Low'].iloc[-1]
    prev_high = df['High'].iloc[-2]
    
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    
    if pd.isna(sma200) or pd.isna(ema50):
        return {"passed": False, "reasons": ["MAs not calculated"]}
        
    # 1. Long term bullish
    if not (close > sma200 and ema50 > sma200):
        return {"passed": False, "reasons": ["Not long-term bullish"]}
        
    # 2. RSI Condition
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if pd.isna(rsi) or not (30 <= rsi <= 45):
        return {"passed": False, "reasons": [f"RSI {rsi:.2f} not in (30, 45)"]}
        
    # 3. Support Proximity (near 50 EMA)
    dist_50 = abs(close - ema50) / ema50
    if dist_50 > 0.06 and close < ema50:
        return {"passed": False, "reasons": ["Broken too far below 50 EMA"]}
        
    # 4. Volatility
    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    if atr / close > 0.05:
        return {"passed": False, "reasons": ["ATR > 5%"]}
        
    # 5. Reversal Confirmation
    candle_range = high - low
    if candle_range == 0:
        return {"passed": False, "reasons": ["Zero candle range"]}
    
    close_strength = (close - low) / candle_range
    is_strong_close = close_strength > 0.6
    is_engulfing = close > prev_high
    is_hammer = (open_p - low) / candle_range > 0.6 and (close - low) / candle_range > 0.6
    
    if not (is_strong_close or is_engulfing or is_hammer):
        return {"passed": False, "reasons": ["No reversal confirmation"]}
        
    return {"passed": True, "score": 1.0, "trigger_type": "Oversold Uptrend"}

def volatility_compression_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
        
    close = df['Close'].iloc[-1]
    
    # 1. & 2. TRENDS
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    
    if not (close > sma200 and ema50 > sma200 and ema20 >= ema50):
        return {"passed": False, "reasons": ["Trend not aligned"]}
        
    # 3. CONSOLIDATION (Look at past 10 days excluding today)
    past_10_high = df['High'].iloc[-11:-1].max()
    past_10_low = df['Low'].iloc[-11:-1].min()
    consolidation_range = (past_10_high - past_10_low) / past_10_low
    
    if consolidation_range > 0.06: # Max 6% consolidation range
        return {"passed": False, "reasons": ["Consolidation too loose (>6%)"]}
        
    # 8. BREAKOUT & 5. RESISTANCE
    # Today must break above the past 10-day high
    if close <= past_10_high:
        return {"passed": False, "reasons": ["No breakout above consolidation"]}
        
    # 9. EXTENSION
    if close > past_10_high * 1.05:
        return {"passed": False, "reasons": ["Overextended breakout (>5%)"]}
        
    # 4. VOLATILITY CONTRACTION
    atr = (df['High'] - df['Low']).rolling(14).mean()
    current_atr = atr.iloc[-1]
    avg_atr_past = atr.iloc[-11:-1].mean()
    if current_atr > avg_atr_past:
        return {"passed": False, "reasons": ["ATR not declining"]}
        
    # 6. MOMENTUM
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if rsi <= 55:
        return {"passed": False, "reasons": [f"RSI {rsi:.2f} too low (<=55)"]}
        
    macd, macdsignal, _ = talib.MACD(df['Close'], fastperiod=12, slowperiod=26, signalperiod=9)
    if pd.isna(macd.iloc[-1]) or macd.iloc[-1] <= macdsignal.iloc[-1]:
        return {"passed": False, "reasons": ["MACD not improving"]}
        
    # 7. VOLUME
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-1]
    if df['Volume'].iloc[-1] < vol_sma20 * 1.5:
        return {"passed": False, "reasons": ["Volume < 1.5x average"]}
        
    return {"passed": True, "score": 1.0, "trigger_type": "Volatility Compression Breakout"}

def relative_strength_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
        
    close = df['Close'].iloc[-1]
    
    # 1. & 2. TRENDS
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    
    if not (close > sma200 and ema50 > sma200 and ema20 > ema50):
        return {"passed": False, "reasons": ["Trend not aligned"]}
        
    # 3. ABSOLUTE MOMENTUM
    close_20 = df['Close'].iloc[-21] if len(df) > 20 else df['Close'].iloc[0]
    close_60 = df['Close'].iloc[-61] if len(df) > 60 else df['Close'].iloc[0]
    
    ret_20 = (close - close_20) / close_20
    ret_60 = (close - close_60) / close_60
    
    if ret_20 <= 0 or ret_60 <= 0:
        return {"passed": False, "reasons": ["Negative absolute momentum"]}
        
    # 4. FACTOR STRIPPING (IDIOSYNCRATIC MOMENTUM)
    if nifty_hist is not None and sector_hist is not None and len(nifty_hist) > 60 and len(sector_hist) > 60:
        # Get daily returns as pandas Series to preserve date index
        stock_ret = df['Close'].pct_change().fillna(0)
        nifty_ret = nifty_hist['Close'].pct_change().fillna(0)
        sector_ret = sector_hist['Close'].pct_change().fillna(0)
        
        # Enforce strict date alignment to prevent forward bias (comparing misaligned days)
        aligned = pd.concat([stock_ret, nifty_ret, sector_ret], axis=1, join='inner').dropna()
        aligned = aligned.iloc[-60:]
        
        if len(aligned) < 30:
            return {"passed": False, "reasons": ["Not enough aligned dates for regression"]}
            
        # Regress Stock = Alpha + B1*Nifty + B2*Sector
        y = aligned.iloc[:, 0].values
        X = aligned.iloc[:, 1:3].values
        
        model = LinearRegression()
        model.fit(X, y)
        
        # Alpha is daily residual return. Multiply by window to get total 60-day alpha
        idiosyncratic_return = model.intercept_ * len(aligned)
        alpha_score = idiosyncratic_return
        
        if idiosyncratic_return <= 0.05: # Require at least 5% alpha over 60 days
            return {"passed": False, "reasons": [f"Low Idiosyncratic Momentum (Alpha: {idiosyncratic_return:.3f})"]}
    else:
        n_ret_20 = 0.0
        n_ret_60 = 0.0
        if nifty_hist is not None and len(nifty_hist) > 60:
            nifty_close_20 = nifty_hist['Close'].iloc[-21]
            nifty_close_60 = nifty_hist['Close'].iloc[-61]
            nifty_close = nifty_hist['Close'].iloc[-1]
            n_ret_20 = (nifty_close - nifty_close_20) / nifty_close_20
            n_ret_60 = (nifty_close - nifty_close_60) / nifty_close_60
            
        if ret_20 <= n_ret_20 or ret_60 <= n_ret_60:
            return {"passed": False, "reasons": ["Underperforming Nifty"]}
        alpha_score = (ret_60 - n_ret_60)  # Excess return as proxy
        
    # 5. RSI
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if not (55 <= rsi <= 80):
        return {"passed": False, "reasons": [f"RSI {rsi:.2f} not in (55, 80)"]}
        
    # 7. VOLUME (Ensure reasonable volume)
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-1]
    if df['Volume'].iloc[-1] < vol_sma20 * 0.8:
        return {"passed": False, "reasons": ["Low relative volume"]}
        
    # 8. AVOID EXTENSION
    if close > ema20 * 1.10:
        return {"passed": False, "reasons": ["Overextended >10% from 20 EMA"]}
        
    # 9. VOLATILITY
    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    if atr / close > 0.05:
        return {"passed": False, "reasons": ["ATR > 5%"]}
        
    return {"passed": True, "score": 1.0, "alpha_score": alpha_score, "trigger_type": "Relative Strength Momentum"}

# Define strategies here.
STRATEGIES = [
    {
        "name": "Momentum Breakout",
        "trading_tools": [],
        "trading_filters": ["Require High Liquidity (>100k Vol)", "Require RR >= 1:2"],
        "risk_management": "ATR 1.5",
        "ai_logic_prompt": None,
        "ai_filter_prompt": None,
        "precompiled_eval_func": momentum_breakout_eval
    },
    {
        "name": "Volatility Compression",
        "description": "NIFTY 500 stocks undergoing declining volatility and a tight 10-day consolidation before breaking out on high volume.",
        "trading_tools": [],
        "trading_filters": [
            "Require High Liquidity (>100k Vol)"
        ],
        "risk_management": "ATR 1.5",
        "ai_logic_prompt": None,
        "ai_filter_prompt": None,
        "precompiled_eval_func": volatility_compression_eval
    },
    {
        "name": "Relative Strength",
        "description": "NIFTY 500 stocks that are significantly outperforming the broader market during a bullish regime, buying on minor consolidations.",
        "trading_tools": [],
        "trading_filters": [
            "Require High Liquidity (>100k Vol)"
        ],
        "risk_management": "ATR 2.0",
        "ai_logic_prompt": None,
        "ai_filter_prompt": None,
        "precompiled_eval_func": relative_strength_eval
    }
]

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            trades = json.load(f)
            # Backfill for backward compatibility
            for t in trades:
                if "entry_regime" not in t or t["entry_regime"] == "Unknown":
                    # Parse the entry date string back to a date object
                    try:
                        e_date = datetime.strptime(t["entry_date"], "%Y-%m-%d").date()
                        t["entry_regime"] = get_market_regime(e_date)
                    except Exception:
                        t["entry_regime"] = "Unknown"
                if "exit_regime" not in t: 
                    t["exit_regime"] = None
            return trades
    return []

def save_state(trades):
    with open(STATE_FILE, "w") as f:
        json.dump(trades, f, indent=4)

def get_market_regime(as_of_date):
    bulk_data = fetch_bulk_history(["NIFTYBEES"], as_of_date, lookback_days=100)
    nifty = bulk_data.get("NIFTYBEES")
    if nifty is not None and not nifty.empty and len(nifty) >= 60:
        # Calculate benchmark returns globally
        close_0 = nifty['Close'].iloc[-1]
        close_20 = nifty['Close'].iloc[-21] if len(nifty) > 20 else nifty['Close'].iloc[0]
        close_60 = nifty['Close'].iloc[-61] if len(nifty) > 60 else nifty['Close'].iloc[0]
        BENCHMARK_RETURNS["20d"] = (close_0 - close_20) / close_20
        BENCHMARK_RETURNS["60d"] = (close_0 - close_60) / close_60
        
        sma_50 = nifty["Close"].rolling(50).mean()
        sma_50_diff = sma_50.diff()
        
        curr_close = nifty["Close"].iloc[-1]
        curr_sma50 = sma_50.iloc[-1]
        curr_sma50_diff = sma_50_diff.iloc[-1]
        
        if curr_close > curr_sma50 and curr_sma50_diff > 0:
            return "Bullish"
        elif curr_close < curr_sma50 and curr_sma50_diff < 0:
            return "Bearish"
        else:
            return "Choppy"
    return "Unknown"

def update_open_trades(trades, as_of_date):
    """
    Checks open trades against today's EOD data to see if they hit SL or Target.
    """
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    if not open_trades:
        return trades
        
    logger.info(f"Checking {len(open_trades)} open trades against {as_of_date} data...")
    
    # We only need to fetch data for the symbols in open trades
    symbols = list(set([t["symbol"] for t in open_trades]))
    bulk_data = fetch_bulk_history(symbols, as_of_date, lookback_days=5)
    
    date_str = as_of_date.strftime("%Y-%m-%d")
    current_regime = get_market_regime(as_of_date)
    
    for t in open_trades:
        sym = t["symbol"]
        if sym in bulk_data and not bulk_data[sym].empty:
            df = bulk_data[sym]
            # Check the last row (today)
            today_high = df['High'].iloc[-1]
            today_low = df['Low'].iloc[-1]
            today_close = df['Close'].iloc[-1]
            
            # Simple check: did it hit stop loss or target today?
            # Note: We prioritize Stop Loss hit over Target hit on the same day for conservatism.
            if today_low <= t["stop_loss"]:
                t["status"] = "LOSS"
                t["exit_date"] = date_str
                t["exit_price"] = t["stop_loss"]
                t["exit_regime"] = current_regime
                t["pnl_pct"] = ((t["exit_price"] - t["entry_price"]) / t["entry_price"]) * 100
                logger.info(f"Trade {t['trade_id']} ({sym}) CLOSED at LOSS: {t['pnl_pct']:.2f}%")
            elif today_high >= t["target"]:
                t["status"] = "WIN"
                t["exit_date"] = date_str
                t["exit_price"] = t["target"]
                t["exit_regime"] = current_regime
                t["pnl_pct"] = ((t["exit_price"] - t["entry_price"]) / t["entry_price"]) * 100
                logger.info(f"Trade {t['trade_id']} ({sym}) CLOSED at WIN: {t['pnl_pct']:.2f}%")

    return trades

def run_strategies(trades, as_of_date):
    """
    Runs all predefined strategies on today's EOD data and adds new trades to state.
    """
    date_str = as_of_date.strftime("%Y-%m-%d")
    current_regime = get_market_regime(as_of_date)
    
    logger.info("Loading NIFTY 500 universe...")
    symbols = load_nifty500_symbols()
    if "NIFTYBEES" not in symbols:
        symbols.append("NIFTYBEES")
        
    logger.info(f"Fetching bulk history up to {date_str}...")
    bulk_data = fetch_bulk_history(symbols, end_date=as_of_date, lookback_days=300)
    
    nifty_hist = bulk_data.pop("NIFTYBEES") if "NIFTYBEES" in bulk_data else None
    
    # Build sector indices for consistency with backtester
    from src.data.nse_fetcher import load_nifty500_industry_mapping
    industry_mapping = load_nifty500_industry_mapping()
    sector_indices = {}
    sectors = {}
    for sym, df in bulk_data.items():
        if sym in industry_mapping and not df.empty:
            ind = industry_mapping[sym]
            if ind not in sectors:
                sectors[ind] = []
            sectors[ind].append(df['Close'].pct_change().fillna(0))
    for ind, returns_list in sectors.items():
        avg_returns = pd.concat(returns_list, axis=1).mean(axis=1)
        synthetic_price = 100 * (1 + avg_returns).cumprod()
        sector_indices[ind] = pd.DataFrame({"Close": synthetic_price})
    
    all_raw_candidates = []
    
    for strategy in STRATEGIES:
        logger.info(f"Running strategy: {strategy['name']}...")
        eval_func = strategy.get("precompiled_eval_func")
        if not eval_func:
            continue
            
        strategy_candidates = []
        for symbol, df in bulk_data.items():
            # Explicit date slice for safety against timezone/caching edge cases
            df = df[df.index <= pd.Timestamp(as_of_date)]
            if len(df) < 200:
                continue
            
            try:
                # Build sector_hist for this symbol
                sector_hist = None
                if symbol in industry_mapping:
                    ind = industry_mapping[symbol]
                    if ind in sector_indices:
                        sector_hist = sector_indices[ind][sector_indices[ind].index <= pd.Timestamp(as_of_date)]
                
                res = eval_func(df, nifty_hist=nifty_hist, sector_hist=sector_hist)
                if res and res.get("passed", False):
                    close_price = df['Close'].iloc[-1]
                    
                    # Compute score for ranking
                    close_20 = df['Close'].iloc[-21] if len(df) > 20 else df['Close'].iloc[0]
                    score = (close_price - close_20) / close_20
                    
                    # Calculate ATR for stop loss
                    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
                    risk_str = strategy.get("risk_management", "ATR 1.5")
                    try:
                        mult = float(risk_str.split(" ")[1])
                    except:
                        mult = 1.5
                    
                    stop_loss = close_price - (mult * atr) if pd.notna(atr) else close_price * 0.95
                    risk = close_price - stop_loss
                    target = close_price + (2.0 * risk) # RR 1:2
                    
                    strategy_candidates.append({
                        "strategy_name": strategy["name"],
                        "symbol": symbol,
                        "tradingview_link": f"https://in.tradingview.com/chart/?symbol=NSE:{symbol}",
                        "entry_date": date_str,
                        "entry_regime": current_regime,
                        "entry_price": close_price,
                        "close_price": close_price,
                        "stop_loss": stop_loss,
                        "target": target,
                        "status": "OPEN",
                        "exit_date": None,
                        "exit_regime": None,
                        "exit_price": None,
                        "pnl_pct": None,
                        "score": score
                    })
            except Exception as e:
                pass
                
        all_raw_candidates.extend(strategy_candidates)
        
    # Build Ensemble Strategy
    symbol_counts = {}
    for t in all_raw_candidates:
        if t["entry_date"] == date_str:
            symbol = t["symbol"]
            if symbol not in symbol_counts:
                symbol_counts[symbol] = []
            symbol_counts[symbol].append(t)
            
    ensemble_candidates = []
    for symbol, t_list in symbol_counts.items():
        if len(t_list) >= 2:
            base_t = t_list[0]
            strategy_names = [t["strategy_name"] for t in t_list]
            ensemble_t = base_t.copy()
            ensemble_t["trade_id"] = str(uuid.uuid4())
            ensemble_t["strategy_name"] = "Ensemble Strategy"
            ensemble_t["note"] = f"Passed {len(t_list)} strategies: {', '.join(strategy_names)}"
            ensemble_t["score"] = base_t["score"] + 1000 # Boost to top
            ensemble_candidates.append(ensemble_t)
            
    all_raw_candidates.extend(ensemble_candidates)
    
    # Filter by strategy, sort by score, take top 5, and add to trades
    strategies_to_process = [s["name"] for s in STRATEGIES] + ["Ensemble Strategy"]
    for s_name in strategies_to_process:
        s_cands = [c for c in all_raw_candidates if c["strategy_name"] == s_name]
        s_cands = sorted(s_cands, key=lambda x: x.get("score", 0), reverse=True)[:5]
        
        if s_cands:
            logger.info(f"Strategy '{s_name}' found {len(s_cands)} candidates today after ranking.")
            
        for c in s_cands:
            is_duplicate = any(t["symbol"] == c["symbol"] and t["strategy_name"] == s_name and t["status"] == "OPEN" for t in trades)
            if is_duplicate:
                logger.info(f"Skipping {c['symbol']} - already have an OPEN trade for this strategy.")
                continue
                
            c["trade_id"] = str(uuid.uuid4())
            
            # Remove score before saving
            trade_to_save = {k: v for k, v in c.items() if k != "score"}
            trades.append(trade_to_save)
            logger.info(f"Logged new OPEN trade: {c['symbol']} at {c['entry_price']} (Data from {date_str})")
            
    return trades

def calculate_metrics(trades):
    """
    Calculates performance metrics per strategy and writes to strategy-specific metrics.csv
    """
    strategy_names = list(set([t["strategy_name"] for t in trades]))
    
    for s_name in strategy_names:
        s_trades = [t for t in trades if t["strategy_name"] == s_name]
        closed_trades = [t for t in s_trades if t["status"] in ["WIN", "LOSS"]]
        
        total_trades = len(closed_trades)
        if total_trades == 0:
            continue
            
        wins = [t for t in closed_trades if t["status"] == "WIN"]
        losses = [t for t in closed_trades if t["status"] == "LOSS"]
        
        win_rate = (len(wins) / total_trades) * 100
        
        avg_win = sum([t["pnl_pct"] for t in wins]) / len(wins) if wins else 0.0
        avg_loss = sum([t["pnl_pct"] for t in losses]) / len(losses) if losses else 0.0
        
        # Max Drawdown calculation
        closed_trades.sort(key=lambda x: x["exit_date"])
        cumulative_pnl = 0
        peak = 0
        max_dd = 0
        
        for t in closed_trades:
            cumulative_pnl += t["pnl_pct"]
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            dd = peak - cumulative_pnl
            if dd > max_dd:
                max_dd = dd
                
        metrics = [{
            "Strategy": s_name,
            "Total Closed Trades": total_trades,
            "Win Rate %": round(win_rate, 2),
            "Avg Win %": round(avg_win, 2),
            "Avg Loss %": round(avg_loss, 2),
            "Max Drawdown %": round(max_dd, 2)
        }]
        
        safe_name = s_name.replace(" ", "_").replace("/", "_")
        strat_dir = os.path.join(FRONT_TEST_DIR, safe_name)
        os.makedirs(strat_dir, exist_ok=True)
        metrics_file = os.path.join(strat_dir, "metrics.csv")
        
        keys = metrics[0].keys()
        with open(metrics_file, 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, keys)
            dict_writer.writeheader()
            dict_writer.writerows(metrics)

def export_to_csv(trades):
    """
    Exports the trades into individual CSV files per strategy for easy user viewing.
    """
    if not trades:
        return
        
    strategy_names = list(set([t["strategy_name"] for t in trades]))
    
    for s_name in strategy_names:
        s_trades = [t for t in trades if t["strategy_name"] == s_name]
        
        if not s_trades:
            continue
            
        safe_name = s_name.replace(" ", "_").replace("/", "_")
        strat_dir = os.path.join(FRONT_TEST_DIR, safe_name)
        os.makedirs(strat_dir, exist_ok=True)
        csv_path = os.path.join(strat_dir, "trades.csv")
        
        # Sort trades by entry date descending
        s_trades.sort(key=lambda x: x["entry_date"], reverse=True)
        
        # Collect all unique keys across all trades to prevent missing field errors
        keys = list(s_trades[0].keys())
        for t in s_trades:
            for k in t.keys():
                if k not in keys:
                    keys.append(k)
                    
        with open(csv_path, 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(s_trades)
            
        logger.info(f"Exported {len(s_trades)} trades to {csv_path}")

def main():
    date_input = input("Enter the date to run the screener for (YYYY-MM-DD) or press Enter for today: ").strip()
    
    if date_input:
        try:
            as_of_date = datetime.strptime(date_input, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date format. Using today's date instead.")
            as_of_date = date.today()
    else:
        as_of_date = date.today()
    
    logger.info(f"--- Starting Forward Test Engine for requested date: {as_of_date} ---")
    
    trades = load_state()
    logger.info(f"Loaded {len(trades)} historical/open trades.")
    
    # 1. Update Open Trades
    trades = update_open_trades(trades, as_of_date)
    
    # 2. Run Strategies to find new candidates
    trades = run_strategies(trades, as_of_date)
    
    # 3. Save State (JSON for machine readability)
    save_state(trades)
    
    # 4. Export individual CSVs for human viewing
    export_to_csv(trades)
    
    # 5. Calculate Metrics
    calculate_metrics(trades)
    
    # 6. Continuous Portfolio Tracking & Optimization
    date_str = as_of_date.strftime("%Y-%m-%d")
    
    strategy_names = ["Momentum Breakout", "Volatility Compression", "Relative Strength", "Ensemble Strategy"]
    for s_name in strategy_names:
        s_candidates = [t for t in trades if t.get("entry_date") == date_str and t.get("status") == "OPEN" and t["strategy_name"] == s_name]
        
        try:
            from src.screener.portfolio.portfolio_tracker import step_portfolio
            step_portfolio(s_candidates, as_of_date, strategy_name=s_name)
        except Exception as e:
            logger.error(f"Error during portfolio tracking/optimization for {s_name}: {e}")
    
    logger.info("--- Forward Test Engine Completed ---")
    cleanup_cache()

if __name__ == "__main__":
    main()
