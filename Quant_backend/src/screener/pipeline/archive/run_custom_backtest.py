import pandas as pd
import numpy as np
import logging
from datetime import date
from typing import List, Dict, Any
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from src.data.nse_fetcher import load_nifty500_symbols, fetch_bulk_history
from src.screener.pipeline.archive.run_custom_screen import evaluate_custom_tools

logger = logging.getLogger(__name__)

def run_custom_backtest(
    months: int = 6,
    trading_tools: List[str] = None, 
    trading_filters: List[str] = None,
    risk_management: str = "ATR 1.5", 
    ai_logic_prompt: str = None,
    ai_filter_prompt: str = None,
    gemini_api_key: str = None,
    progress_callback=None
) -> Dict[str, Any]:
    
    if trading_tools is None: trading_tools = []
    if trading_filters is None: trading_filters = []
        
    def log_progress(msg, level="INFO"):
        if progress_callback:
            progress_callback(msg, level)
        if level == "ERROR": logger.error(msg)
        elif level == "WARNING": logger.warning(msg)
        else: logger.info(msg)
            
    log_progress(f"Starting Custom Strategy BACKTEST ({months} Months)...")
    
    # 1. Compile AI Logic & Filters
    has_ai_logic = False
    custom_ai_eval_func = None
    if ai_logic_prompt:
        log_progress("Generating dynamic AI Python logic...")
        try:
            from src.services.ai_coder import generate_pandas_logic
            generated_code = generate_pandas_logic(ai_logic_prompt, gemini_api_key)
            import pandas as pd
            import numpy as np
            import talib
            isolated_globals = {
                'pd': pd,
                'np': np,
                'talib': talib,
                '__builtins__': __builtins__
            }
            exec(generated_code, isolated_globals)
            if "custom_ai_eval" in isolated_globals:
                custom_ai_eval_func = isolated_globals["custom_ai_eval"]
                has_ai_logic = True
                log_progress("AI Logic compiled.")
        except Exception as e:
            log_progress(f"Failed to compile AI logic: {e}", level="ERROR")
            
    has_ai_filter = False
    custom_ai_filter_func = None
    if ai_filter_prompt:
        log_progress("Generating dynamic AI Filter Python logic...")
        try:
            from src.services.ai_coder import generate_filter_logic
            generated_filter_code = generate_filter_logic(ai_filter_prompt, gemini_api_key)
            isolated_globals_filter = {
                'pd': pd,
                'np': np,
                '__builtins__': __builtins__
            }
            exec(generated_filter_code, isolated_globals_filter)
            if "custom_ai_filter" in isolated_globals_filter:
                custom_ai_filter_func = isolated_globals_filter["custom_ai_filter"]
                has_ai_filter = True
                log_progress("AI Filter Logic compiled.")
        except Exception as e:
            log_progress(f"Failed to compile AI Filter logic: {e}", level="ERROR")

    # 2. Fetch Data
    universe = load_nifty500_symbols()
    log_progress("Fetching historical bulk data...")
    backtest_days = months * 21
    total_lookback = backtest_days + 300 
    bulk_data = fetch_bulk_history(universe, date.today(), lookback_days=total_lookback)
    
    all_dates = set()
    for df in bulk_data.values():
        if not df.empty:
            all_dates.update(df.index.tolist())
    sorted_dates = sorted(list(all_dates))
    
    if len(sorted_dates) <= backtest_days:
        log_progress("Not enough data fetched for backtest.", level="ERROR")
        return {}
        
    test_dates = sorted_dates[-backtest_days:]
    log_progress(f"Backtesting over {len(test_dates)} trading days...")
    
    trades = []
    
    # 3. Execution Loop
    
    for symbol, df in bulk_data.items():
        if df.empty or len(df) < 300:
            continue
            
        in_trade = False
        trade_entry_price = 0.0
        trade_target = 0.0
        trade_stop_loss = 0.0
        trade_entry_date = None
        
        for i in range(300, len(df)):
            current_date = df.index[i]
            if current_date not in test_dates:
                continue
                
            curr_row = df.iloc[i]
            
            if in_trade:
                # Fast forward evaluation
                high = curr_row['High']
                low = curr_row['Low']
                close = curr_row['Close']
                
                # Check Stop Loss First (Conservative)
                if low <= trade_stop_loss:
                    trade_return = (trade_stop_loss - trade_entry_price) / trade_entry_price
                    trades.append({
                        "symbol": symbol, "entry_date": str(trade_entry_date.date()), "exit_date": str(current_date.date()),
                        "entry_price": round(trade_entry_price, 2), "exit_price": round(trade_stop_loss, 2),
                        "return": round(trade_return, 4), "status": "Loss"
                    })
                    in_trade = False
                    continue
                    
                # Check Target
                if high >= trade_target:
                    trade_return = (trade_target - trade_entry_price) / trade_entry_price
                    trades.append({
                        "symbol": symbol, "entry_date": str(trade_entry_date.date()), "exit_date": str(current_date.date()),
                        "entry_price": round(trade_entry_price, 2), "exit_price": round(trade_target, 2),
                        "return": round(trade_return, 4), "status": "Win"
                    })
                    in_trade = False
                    continue
            else:
                # Signal Generation
                hist_df = df.iloc[:i+1] # Slice up to today to prevent lookahead bias
                
                eval_result = {"passed": True, "score": 1.0, "trigger_type": "None"}
                if trading_tools:
                    eval_result = evaluate_custom_tools(hist_df, trading_tools)
                    
                # Apply AI Logic dynamically
                ai_passed = True
                if has_ai_logic:
                    try:
                        ai_res = custom_ai_eval_func(hist_df)
                        if not ai_res.get("passed", False):
                            ai_passed = False
                    except Exception as e:
                        ai_passed = False
                        logger.warning(f"AI Logic crashed on {symbol} at {current_date}: {e}")
                        
                if eval_result["passed"] and ai_passed:
                    entry_price = hist_df['Close'].iloc[-1]
                    atr = (hist_df['High'] - hist_df['Low']).rolling(14).mean().iloc[-1]
                    
                    target = entry_price * 1.10
                    stop_loss = entry_price * 0.95
                    
                    if pd.notna(atr) and "ATR" in risk_management:
                        parts = risk_management.split()
                        mult = float(parts[1]) if len(parts) > 1 else 1.5
                        risk_amt = atr * mult
                        stop_loss = entry_price - risk_amt
                        target = entry_price + (risk_amt * 2) 
                    elif "PCT" in risk_management:
                        parts = risk_management.split()
                        pct = float(parts[1]) if len(parts) > 1 else 5.0
                        risk_amt = entry_price * (pct / 100)
                        stop_loss = entry_price - risk_amt
                        target = entry_price + (risk_amt * 2)
                        
                    risk_amount = entry_price - stop_loss
                    
                    # Evaluate Trading Filters
                    filters_passed = True
                    for filter_name in trading_filters:
                        if filter_name == "Require RR >= 1:2":
                            if risk_amount <= 0 or ((target - entry_price) / risk_amount) < 2.0:
                                filters_passed = False
                                break
                        elif filter_name == "Exclude Flat VWAP":
                            if len(hist_df) >= 5:
                                recent = hist_df.tail(5)
                                vwap_now = (recent['Volume'] * ((recent['High'] + recent['Low'] + recent['Close']) / 3)).sum() / (recent['Volume'].sum() + 1e-9)
                                past = hist_df.iloc[-10:-5]
                                if not past.empty:
                                    vwap_past = (past['Volume'] * ((past['High'] + past['Low'] + past['Close']) / 3)).sum() / (past['Volume'].sum() + 1e-9)
                                    if vwap_past > 0 and abs((vwap_now - vwap_past) / vwap_past) < 0.01:
                                        filters_passed = False
                                        break
                        elif filter_name == "Require High Liquidity (>100k Vol)":
                            avg_vol = hist_df['Volume'].rolling(20).mean().iloc[-1]
                            if pd.isna(avg_vol) or avg_vol < 100000:
                                filters_passed = False
                                break
                        elif filter_name == "Exclude High Volatility (ATR > 5%)":
                            if pd.isna(atr) or (atr / entry_price) > 0.05:
                                filters_passed = False
                                break
                    
                    # Evaluate Custom AI Filter
                    if filters_passed and has_ai_filter:
                        try:
                            ai_filter_res = custom_ai_filter_func(hist_df, entry_price, target, stop_loss, atr)
                            if not ai_filter_res.get("passed", False):
                                filters_passed = False
                        except Exception as e:
                            filters_passed = False
                            logger.warning(f"AI Filter crashed on {symbol} at {current_date}: {e}")
                    
                    if filters_passed:
                        in_trade = True
                        trade_entry_price = entry_price
                        trade_target = target
                        trade_stop_loss = stop_loss
                        trade_entry_date = current_date

    # 4. Compute Metrics
    wins = [t['return'] for t in trades if t['return'] > 0]
    losses = [t['return'] for t in trades if t['return'] <= 0]
    
    win_rate = (len(wins) / len(trades) * 100) if trades else 0
    avg_win = (np.mean(wins) * 100) if wins else 0
    avg_loss = (np.mean(losses) * 100) if losses else 0
    
    cagr = 0
    max_drawdown = 0
    
    if trades:
        returns_series = pd.Series([t['return'] for t in trades])
        cumulative = (1 + returns_series).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min() * 100
        
        years = months / 12
        compounded_growth = cumulative.iloc[-1]
        cagr = (compounded_growth ** (1/years) - 1) * 100 if years > 0 else 0
        
    metrics = {
        "Total Trades": len(trades),
        "Win Rate (%)": round(win_rate, 2),
        "Average Win (%)": round(avg_win, 2),
        "Average Loss (%)": round(avg_loss, 2),
        "Max Drawdown (%)": round(max_drawdown, 2),
        "CAGR (%)": round(cagr, 2)
    }
    
    log_progress(f"Backtest Complete. Found {len(trades)} historical trades.")
    
    trades.sort(key=lambda x: x['entry_date'], reverse=True)
    
    return {
        "metrics": metrics,
        "trades": trades
    }
