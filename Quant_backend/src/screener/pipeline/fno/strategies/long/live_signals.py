import os
import sys
import json
import logging
from datetime import date, timedelta
import pandas as pd
import requests
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))))

from src.data.nse_fetcher import load_fno_symbols, load_nifty500_industry_mapping
from src.data.live_tv_fetcher import get_tv_fetcher
from src.screener.pipeline.fno.strategies.long.config_fno import STRATEGY_CONFIG
from src.screener.pipeline.fno.strategies.long.screener import FnoLongScreener
from src.screener.pipeline.intraday.features import calculate_atr

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
STATE_FILE = os.path.join(OUT_DIR, "active_fno_long_trades.json")

# Load environment variables (for Telegram bot tokens)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))), ".env")
load_dotenv(env_path)

def send_telegram_message(message: str):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN_FNO")
    chat_id = os.getenv("TELEGRAM_CHAT_ID_FNO")
    
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID not found in .env. Skipping Telegram notification.")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Successfully sent Telegram notification.")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")

def send_telegram_document(file_path: str, caption: str = ""):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN_FNO")
    chat_id = os.getenv("TELEGRAM_CHAT_ID_FNO")
    
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID not found in .env. Skipping Telegram document.")
        return
        
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            response = requests.post(url, data=data, files=files, timeout=60)
            response.raise_for_status()
            logger.info(f"Successfully sent Telegram document: {file_path}")
    except Exception as e:
        logger.error(f"Failed to send Telegram document: {e}")

def is_last_thursday(d: date) -> bool:
    """Returns True if the given date is the last Thursday of the month."""
    return d.weekday() == 3 and (d + timedelta(days=7)).month != d.month

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return []

def save_state(trades):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(trades, f, indent=4)

def check_open_trades_live(trades, cash_data, today_date):
    """Check if open trades hit SL/Target/Expiry based on live data."""
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    closed_signals = []
    
    if not open_trades:
        return closed_signals
        
    for t in open_trades:
        sym = t["symbol"]
        df = cash_data.get(sym)
        if df is None or df.empty:
            continue
            
        live_low = df['Low'].iloc[-1]
        live_high = df['High'].iloc[-1]
        live_close = df['Close'].iloc[-1]
        
        exit_price = 0
        action = ""
        
        # Check SL/Target
        if live_low <= t["stop_loss"]:
            exit_price = t["stop_loss"]
            action = "SELL (STOP LOSS)"
        elif live_high >= t["target"]:
            exit_price = t["target"]
            action = "SELL (TARGET)"
            
        # Check Expiry Force Close
        if exit_price == 0 and is_last_thursday(today_date):
            exit_price = live_close
            action = "SELL (EXPIRY CLOSE)"
            
        if exit_price > 0:
            t["status"] = "CLOSED"
            t["exit_price"] = exit_price
            t["exit_date"] = today_date.strftime("%Y-%m-%d")
            pnl = ((exit_price - t["entry_price"]) / t["entry_price"]) * 100
            
            closed_signals.append({
                "Date": today_date.strftime("%Y-%m-%d"),
                "Symbol": sym,
                "Action": action,
                "Exit_Price": round(exit_price, 2),
                "PnL_Pct": round(pnl, 2)
            })
            
    return closed_signals

def print_terminal_table(title, df):
    print("\n" + "="*80)
    print(f"🔥 {title} 🔥".center(80))
    print("="*80)
    if df.empty:
        print("No signals found.")
    else:
        print(df.to_markdown(index=False))
    print("="*80 + "\n")

def generate_live_signals():
    logger.info("Initializing F&O Long Live Signal Generator (With State Tracking)...")
    
    symbols = load_fno_symbols()
    ind_map = load_nifty500_industry_mapping()
    
    today = date.today()
    logger.info(f"Fetching REAL-TIME live data from TradingView for {today}...")
    
    fetcher = get_tv_fetcher()
    cash_data = fetcher.fetch_bulk_live(symbols + ["NIFTY"], n_bars=100, max_workers=10)
    
    # 1. Check existing open trades
    logger.info("Evaluating existing open portfolio trades...")
    trades = load_state()
    closed_signals_list = check_open_trades_live(trades, cash_data, today)
    
    closed_df = pd.DataFrame(closed_signals_list)
    print_terminal_table(f"SELL SIGNALS FOR: {today}", closed_df)
    
    # 2. Check position capacity
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    slots_available = STRATEGY_CONFIG['max_open_positions'] - len(open_trades)
    
    logger.info(f"Portfolio slots available: {slots_available} / {STRATEGY_CONFIG['max_open_positions']}")
    
    buy_signals_list = []
    
    if slots_available > 0:
        screener = FnoLongScreener(STRATEGY_CONFIG)
        picks = screener.screen(today, cash_data, ind_map)
        
        if picks:
            for sym in picks:
                if slots_available <= 0:
                    break
                # Don't double down
                if any(p["symbol"] == sym for p in open_trades):
                    continue
                    
                df = cash_data.get(sym)
                if df is None or df.empty:
                    continue
                    
                current_price = df['Close'].iloc[-1]
                atr = calculate_atr(df, period=STRATEGY_CONFIG['atr_period'])
                
                stop_loss = current_price - (atr * STRATEGY_CONFIG['atr_stop_loss_multiplier'])
                risk = current_price - stop_loss
                target = current_price + (risk * STRATEGY_CONFIG['target_r_multiple'])
                
                new_trade = {
                    "symbol": sym,
                    "entry_date": today.strftime("%Y-%m-%d"),
                    "entry_price": round(current_price, 2),
                    "stop_loss": round(stop_loss, 2),
                    "target": round(target, 2),
                    "status": "OPEN",
                    "exit_date": None,
                    "exit_price": None
                }
                trades.append(new_trade)
                open_trades.append(new_trade)
                
                buy_signals_list.append({
                    "Date": today.strftime("%Y-%m-%d"),
                    "Symbol": sym,
                    "Action": "BUY",
                    "Instrument": "Current Month Futures",
                    "Entry_Price_Proxy": round(current_price, 2),
                    "Stop_Loss": round(stop_loss, 2),
                    "Target": round(target, 2),
                    "Risk_Per_Share": round(risk, 2)
                })
                
                slots_available -= 1
        else:
            logger.info("MARKET REGIME OR SETUP BLOCK: No valid Long signals generated for today.")
    else:
        logger.info("Portfolio is full. Skipping new BUY signal generation.")
        
    buy_df = pd.DataFrame(buy_signals_list)
    print_terminal_table(f"BUY SIGNALS FOR: {today}", buy_df)
    
    # Save the updated ledger
    save_state(trades)
    logger.info(f"Ledger state saved to {STATE_FILE}")
    
    # Save today's exact buy recommendations for reference
    out_path = os.path.join(OUT_DIR, "daily_signals.csv")
    buy_df.to_csv(out_path, index=False)
    
    # Send Telegram Notification
    tg_msg = f"<b>🔥 F&O Long Strategy: {today} 🔥</b>\n\n"
    
    tg_msg += "<b>🔴 SELL SIGNALS:</b>\n"
    if closed_df.empty:
        tg_msg += "No signals found.\n\n"
    else:
        for _, row in closed_df.iterrows():
            tg_msg += (
                f"• <b>{row['Symbol']}</b> | {row['Action']}\n"
                f"  Exit Price: ₹{row['Exit_Price']}\n"
                f"  PnL: {row['PnL_Pct']}%\n"
            )
        tg_msg += "\n"
        
    # Run VisuQuant Deep Analysis Pipeline for BUY candidates
    visuquant_reports = []
    if not buy_df.empty:
        logger.info(f"Running VisuQuant AI Pipeline on {len(buy_df)} F&O candidate(s)...")
        try:
            from src.workflow.graph import build_graph
            from src.reporting.storage import persist_pipeline_results
            import time
            
            app_graph = build_graph()
            today_str = today.strftime("%Y-%m-%d")
            
            for _, row in buy_df.iterrows():
                symbol = row["Symbol"]
                logger.info(f">>> Invoking VisuQuant Graph for {symbol} <<<")
                try:
                    t0 = time.time()
                    payload = {"ticker": symbol, "as_of_date": today_str}
                    final_state = app_graph.invoke(payload)
                    t1 = time.time()
                    
                    pdf_path = persist_pipeline_results(final_state, t0, t1)
                    decision_info = final_state.get("decision", {})
                    confluence_info = final_state.get("confluence_analysis", {})
                    unified_trend = final_state.get("unified_trend", {})
                    
                    meta = {
                        "decision": decision_info.get("action") or decision_info.get("decision", "ANALYZED"),
                        "confidence": decision_info.get("confidence", "-"),
                        "trend": unified_trend.get("direction", "-"),
                        "score": confluence_info.get("confluence_score", "-")
                    }
                    visuquant_reports.append((symbol, pdf_path, meta))
                except Exception as e:
                    logger.error(f"VisuQuant analysis failed for {symbol}: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize VisuQuant graph: {e}")

    tg_msg += "<b>🟢 BUY SIGNALS:</b>\n"
    if buy_df.empty:
        if slots_available <= 0:
            tg_msg += "Portfolio full (0/2 slots available). Skipping new generation.\n"
        else:
            tg_msg += "No signals found.\n"
    else:
        # Map VisuQuant meta by symbol
        vq_map = {item[0]: item[2] for item in visuquant_reports}
        for _, row in buy_df.iterrows():
            sym = row['Symbol']
            tg_msg += (
                f"• <b>{sym}</b> | {row['Action']}\n"
                f"  Entry Proxy: ₹{row['Entry_Price_Proxy']}\n"
                f"  Stop Loss: ₹{row['Stop_Loss']}\n"
                f"  Target: ₹{row['Target']}\n"
                f"  Risk/Share: ₹{row['Risk_Per_Share']}\n"
            )
            if sym in vq_map:
                m = vq_map[sym]
                tg_msg += (
                    f"  🤖 <b>VisuQuant AI:</b> {m['decision']} (Conf: {m['confidence']})\n"
                    f"  📊 Trend: {m['trend']} | Confluence: {m['score']}\n"
                )
            tg_msg += "\n"
            
    send_telegram_message(tg_msg)
    
    # Send PDF reports for analyzed candidates
    for symbol, pdf_path, meta in visuquant_reports:
        if pdf_path and os.path.exists(pdf_path):
            caption = f"📄 <b>VisuQuant Report: {symbol}</b>\nVerdict: <b>{meta.get('decision', 'ANALYZED')}</b>"
            send_telegram_document(pdf_path, caption=caption)
    
if __name__ == "__main__":
    generate_live_signals()
