import os
import sys
import json
import logging
from datetime import date, datetime, timedelta
import numpy as np
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
    """Returns True if the given date is the last Thursday of the month (NSE Monthly F&O Expiry)."""
    return d.weekday() == 3 and (d + timedelta(days=7)).month != d.month


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {STATE_FILE}: {e}")
    return []


def save_state(trades):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(trades, f, indent=4)


def check_open_trades_live(trades, cash_data, today_date):
    """
    Evaluates open F&O trades against live market data.
    Checks:
      1. Stop Loss: live_low <= stop_loss
      2. Target: live_high >= target
      3. Monthly Expiry: is_last_thursday(today_date)
    Returns: (closed_signals, active_holdings)
    """
    closed_signals = []
    active_holdings = []
    today_str = today_date.strftime("%Y-%m-%d")
    
    for t in trades:
        if t.get("status") != "OPEN":
            continue
            
        sym = t["symbol"]
        df = cash_data.get(sym)
        entry_price = float(t["entry_price"])
        
        # Calculate business days held
        try:
            entry_dt = datetime.strptime(t.get("entry_date", today_str), "%Y-%m-%d").date()
            days_held = int(np.busday_count(entry_dt, today_date))
        except Exception:
            days_held = 0
        t["days_held"] = days_held
        
        if df is not None and not df.empty:
            live_low = float(df['Low'].iloc[-1])
            live_high = float(df['High'].iloc[-1])
            live_close = float(df['Close'].iloc[-1])
            t["current_price"] = round(live_close, 2)
            
            exit_price = 0
            action = ""
            reason = ""
            
            # 1. Stop Loss
            if live_low <= t["stop_loss"]:
                exit_price = t["stop_loss"]
                action = "SELL (STOP LOSS 🛑)"
                reason = "Hard Stop Loss Hit"
            # 2. Profit Target
            elif live_high >= t["target"]:
                exit_price = t["target"]
                action = "SELL (TARGET 🎯)"
                reason = "Target Hit"
            # 3. Monthly Expiry Force Close
            elif is_last_thursday(today_date):
                exit_price = live_close
                action = "SELL (EXPIRY CLOSE ⌛)"
                reason = "Monthly Contract Expiry"
                
            if exit_price > 0:
                pnl = ((exit_price - entry_price) / entry_price) * 100
                t["status"] = "CLOSED"
                t["exit_price"] = round(exit_price, 2)
                t["exit_date"] = today_str
                t["exit_reason"] = action
                t["pnl_pct"] = round(pnl, 2)
                
                closed_signals.append({
                    "Date": today_str,
                    "Symbol": sym,
                    "Action": action,
                    "Reason": reason,
                    "Exit_Price": round(exit_price, 2),
                    "PnL_Pct": round(pnl, 2),
                    "Days_Held": days_held,
                })
            else:
                unrealized_pct = ((live_close - entry_price) / entry_price) * 100
                t["unrealized_pnl_pct"] = round(unrealized_pct, 2)
                active_holdings.append(t)
        else:
            # Price data missing today
            cur_p = t.get("current_price", entry_price)
            unrealized_pct = ((cur_p - entry_price) / entry_price) * 100
            t["current_price"] = cur_p
            t["unrealized_pnl_pct"] = round(unrealized_pct, 2)
            active_holdings.append(t)
            
    return closed_signals, active_holdings


def build_unified_fno_telegram_message(
    today_str: str,
    closed_signals: list,
    actionable_buys: list,
    active_holdings: list,
    max_slots: int,
    base_capital: float
) -> str:
    """Constructs the unified institutional-grade Telegram update for F&O Long Strategy."""
    slot_margin = base_capital / max_slots
    lines = []
    lines.append("<b>🔥 F&O LONG STRATEGY — DAILY PORTFOLIO UPDATE 🔥</b>")
    lines.append(f"📅 Date: <code>{today_str}</code> | 3:15 PM MOC Execution\n")
    
    # -------------------------------------------------------------
    # 1. 🟢 FRESH BUY ORDERS TODAY
    # -------------------------------------------------------------
    lines.append("<b>🟢 FRESH F&O BUY ORDERS TODAY (3:15 PM MOC):</b>")
    if not actionable_buys:
        if len(active_holdings) >= max_slots:
            lines.append(f"• <i>Portfolio full ({max_slots}/{max_slots} slots occupied). Skipping new entries.</i>")
        else:
            lines.append("• None today (Market regime filter active | Margin preserved)")
    else:
        for b in actionable_buys:
            lines.append(
                f"• <b>{b['Symbol']}</b> | Current Month Futures\n"
                f"  ├ Entry Proxy (CMP): <b>₹{b['Entry_Price_Proxy']:.2f}</b>\n"
                f"  ├ Hard Stop Loss: ₹{b['Stop_Loss']:.2f} (-{b.get('sl_pct', 0):.1f}%)\n"
                f"  ├ Target: ₹{b['Target']:.2f} (+{b.get('tgt_pct', 0):.1f}%)\n"
                f"  ├ Risk / Share: ₹{b['Risk_Per_Share']:.2f}\n"
                f"  └ <b>Sizing: 1 Lot</b> (₹{slot_margin:,.0f} Margin Allocated / 50% Equity)"
            )
    lines.append("")
    
    # -------------------------------------------------------------
    # 2. 🔴 SELL & EXIT ORDERS TODAY
    # -------------------------------------------------------------
    lines.append("<b>🔴 SELL & EXIT ORDERS TODAY:</b>")
    if not closed_signals:
        lines.append("• None today (All active positions holding)")
    else:
        for item in closed_signals:
            pnl_sign = "+" if item.get('PnL_Pct', 0) >= 0 else ""
            lines.append(
                f"• <b>{item['Symbol']}</b> — {item.get('Action', 'EXIT')}\n"
                f"  ├ Exit Price: ₹{item.get('Exit_Price', 0):.2f}\n"
                f"  ├ Realized PnL: <b>{pnl_sign}{item.get('PnL_Pct', 0):.2f}%</b>\n"
                f"  └ Held: {item.get('Days_Held', 0)} sessions ({item.get('Reason', 'Trade Exit')})"
            )
    lines.append("")
    
    # -------------------------------------------------------------
    # 3. 💼 ACTIVE F&O PORTFOLIO TRACKER (HOLDINGS)
    # -------------------------------------------------------------
    lines.append("<b>💼 ACTIVE F&O PORTFOLIO TRACKER (Holdings):</b>")
    if not active_holdings:
        lines.append("• No open positions currently (100% Margin cash cushion preserved)")
    else:
        for idx, pos in enumerate(active_holdings, 1):
            cur_p = pos.get("current_price", pos["entry_price"])
            ent_p = pos["entry_price"]
            pnl_pct = pos.get("unrealized_pnl_pct", ((cur_p - ent_p) / ent_p) * 100)
            pnl_sign = "+" if pnl_pct >= 0 else ""
            held = pos.get("days_held", 0)
            tag = " <i>(NEW)</i>" if held == 0 else ""
            held_str = f"Held: {held} sessions" if held > 0 else "Held: Day 0 (New Entry Today)"
            
            lines.append(
                f"<b>{idx}. {pos['symbol']}</b>{tag} (Current Month Futures)\n"
                f"   ├ Entry: ₹{ent_p:.2f} | CMP: ₹{cur_p:.2f}\n"
                f"   ├ PnL: <b>{pnl_sign}{pnl_pct:.2f}%</b>\n"
                f"   ├ SL: ₹{pos['stop_loss']:.2f} | TGT: ₹{pos['target']:.2f}\n"
                f"   └ {held_str}"
            )
    lines.append("")
    
    # -------------------------------------------------------------
    # 4. 📊 PORTFOLIO HEALTH & CAPITAL ALLOCATION
    # -------------------------------------------------------------
    occupied = len(active_holdings)
    invested_pct = (occupied / max_slots) * 100
    cash_pct = 100.0 - invested_pct
    free_cash = max(0, max_slots - occupied) * slot_margin
    
    total_unrealized_pct = (
        sum(p.get("unrealized_pnl_pct", 0.0) for p in active_holdings) / occupied
    ) if occupied > 0 else 0.0
    pnl_sign = "+" if total_unrealized_pct >= 0 else ""
    
    lines.append("<b>📊 F&O PORTFOLIO HEALTH & CAPITAL ALLOCATION:</b>")
    lines.append(f"• Slots: <b>{occupied} / {max_slots} Occupied</b> ({invested_pct:.0f}% Margin Deployed, {cash_pct:.0f}% Free Cash)")
    lines.append(f"• Account Base: ₹{base_capital:,.0f} | Free Margin: ₹{free_cash:,.0f} ({cash_pct:.0f}%)")
    if occupied > 0:
        lines.append(f"• Avg Position PnL: <b>{pnl_sign}{total_unrealized_pct:.2f}%</b>")
        
    return "\n".join(lines)


def print_terminal_dashboard(closed_signals, actionable_buys, active_holdings, max_slots, base_capital):
    slot_margin = base_capital / max_slots
    print(f"\n{'='*85}")
    print(f"{'F&O LONG STRATEGY — LIVE PORTFOLIO DASHBOARD (3:15 PM MOC)'.center(85)}")
    print(f"{'='*85}")
    
    # Exits
    print(f"\n[1] 🔴 SELL / EXIT SIGNALS TODAY ({len(closed_signals)}):")
    if not closed_signals:
        print("    None. All active F&O positions holding.")
    else:
        print(f"    {'SYMBOL':<14} | {'ACTION':<24} | {'EXIT PRICE':<12} | {'PNL %':<10} | {'REASON'}")
        print("    " + "-"*75)
        for s in closed_signals:
            print(f"    {s['Symbol']:<14} | {s['Action']:<24} | ₹{s['Exit_Price']:<11.2f} | {s['PnL_Pct']:>+6.2f}%    | {s['Reason']}")
            
    # Fresh Buys
    print(f"\n[2] 🟢 FRESH BUY ORDERS TODAY ({len(actionable_buys)}):")
    if not actionable_buys:
        print("    None today.")
    else:
        print(f"    {'SYMBOL':<14} | {'ENTRY (CMP)':<12} | {'STOP LOSS':<12} | {'TARGET':<12} | {'RISK/SH':<10} | {'MARGIN'}")
        print("    " + "-"*75)
        for b in actionable_buys:
            print(f"    {b['Symbol']:<14} | ₹{b['Entry_Price_Proxy']:<11.2f} | ₹{b['Stop_Loss']:<11.2f} | ₹{b['Target']:<11.2f} | ₹{b['Risk_Per_Share']:<9.2f} | ₹{slot_margin:,.0f}")
            
    # Active Portfolio
    print(f"\n[3] 💼 ACTIVE F&O PORTFOLIO TRACKER ({len(active_holdings)} / {max_slots} SLOTS):")
    if not active_holdings:
        print("    No open positions (100% Margin cash cushion preserved).")
    else:
        print(f"    {'#':<3} {'SYMBOL':<12} | {'ENTRY':<10} | {'CMP':<10} | {'UNREALIZED PNL':<16} | {'HELD':<6} | {'STOP':<10} | {'TARGET'}")
        print("    " + "-"*80)
        for i, pos in enumerate(active_holdings, 1):
            cur_p = pos.get("current_price", pos["entry_price"])
            pnl_pct = pos.get("unrealized_pnl_pct", 0.0)
            held = f"{pos.get('days_held', 0)}d"
            print(f"    {i:<3} {pos['symbol']:<12} | ₹{pos['entry_price']:<9.2f} | ₹{cur_p:<9.2f} | {pnl_pct:>+6.2f}%          | {held:<6} | ₹{pos['stop_loss']:<9.2f} | ₹{pos['target']:.2f}")
            
    print(f"\n{'='*85}\n")


def generate_live_signals():
    logger.info("Initializing F&O Long Live Signal Generator (With Full Portfolio Tracking)...")
    
    max_slots = STRATEGY_CONFIG['max_open_positions']
    base_capital = STRATEGY_CONFIG['starting_capital']
    
    symbols = load_fno_symbols()
    ind_map = load_nifty500_industry_mapping()
    
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    logger.info(f"Fetching REAL-TIME live data from TradingView for {today}...")
    
    fetcher = get_tv_fetcher()
    cash_data = fetcher.fetch_bulk_live_cached(symbols + ["NIFTY"], n_bars=100)
    
    # 1. Load persistent trade ledger
    trades = load_state()
    
    # 2. Check existing open trades and mark-to-market
    logger.info("Evaluating existing open portfolio trades...")
    closed_signals, active_holdings = check_open_trades_live(trades, cash_data, today)
    
    # 3. Position capacity check
    slots_available = max_slots - len(active_holdings)
    logger.info(f"Portfolio slots available: {slots_available} / {max_slots}")
    
    # 4. Screen for fresh buys if slots available
    actionable_buys = []
    
    if slots_available > 0:
        screener = FnoLongScreener(STRATEGY_CONFIG)
        picks = screener.screen(today, cash_data, ind_map)
        
        if picks:
            active_symbols = {p["symbol"] for p in active_holdings}
            for sym in picks:
                if slots_available <= 0:
                    break
                if sym in active_symbols:
                    continue
                    
                df = cash_data.get(sym)
                if df is None or df.empty:
                    continue
                    
                current_price = df['Close'].iloc[-1]
                atr = calculate_atr(df, period=STRATEGY_CONFIG['atr_period'])
                
                stop_loss = current_price - (atr * STRATEGY_CONFIG['atr_stop_loss_multiplier'])
                risk = current_price - stop_loss
                target = current_price + (risk * STRATEGY_CONFIG['target_r_multiple'])
                
                sl_pct = round(((current_price - stop_loss) / current_price) * 100, 2)
                tgt_pct = round(((target - current_price) / current_price) * 100, 2)
                
                new_trade = {
                    "symbol": sym,
                    "instrument": "Current Month Futures (1 Lot)",
                    "entry_date": today_str,
                    "entry_price": round(current_price, 2),
                    "current_price": round(current_price, 2),
                    "stop_loss": round(stop_loss, 2),
                    "target": round(target, 2),
                    "status": "OPEN",
                    "days_held": 0,
                    "unrealized_pnl_pct": 0.0,
                    "exit_date": None,
                    "exit_price": None,
                    "exit_reason": None,
                    "pnl_pct": None,
                }
                trades.append(new_trade)
                active_holdings.append(new_trade)
                
                actionable_buys.append({
                    "Date": today_str,
                    "Symbol": sym,
                    "Action": "BUY",
                    "Instrument": "Current Month Futures",
                    "Entry_Price_Proxy": round(current_price, 2),
                    "Stop_Loss": round(stop_loss, 2),
                    "Target": round(target, 2),
                    "Risk_Per_Share": round(risk, 2),
                    "sl_pct": sl_pct,
                    "tgt_pct": tgt_pct,
                })
                
                slots_available -= 1
        else:
            logger.info("MARKET REGIME OR SETUP BLOCK: No valid Long signals generated for today.")
    else:
        logger.info("Portfolio is full. Skipping new BUY signal generation.")
        
    # 5. Persist ledger state to output directory (cached by GitHub Actions)
    save_state(trades)
    logger.info(f"Ledger state saved to {STATE_FILE}")
    
    # Save today's buy recommendations CSV
    out_path = os.path.join(OUT_DIR, "daily_signals.csv")
    pd.DataFrame(actionable_buys).to_csv(out_path, index=False)
    
    # 6. Print terminal dashboard
    print_terminal_dashboard(closed_signals, actionable_buys, active_holdings, max_slots, base_capital)
    
    # 7. Construct and send unified Telegram Notification
    tg_msg = build_unified_fno_telegram_message(
        today_str=today_str,
        closed_signals=closed_signals,
        actionable_buys=actionable_buys,
        active_holdings=active_holdings,
        max_slots=max_slots,
        base_capital=base_capital
    )
    
    send_telegram_message(tg_msg)
    

if __name__ == "__main__":
    generate_live_signals()
