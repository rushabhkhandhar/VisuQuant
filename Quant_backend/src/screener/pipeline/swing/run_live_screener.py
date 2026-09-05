import os
import sys
import logging
import json
import uuid
import requests
import numpy as np
import pandas as pd
from datetime import datetime, date
from dotenv import load_dotenv

# Load environment variables for Telegram
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), ".env")
load_dotenv(env_path)

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from src.data.nse_fetcher import load_nifty500_symbols, load_nifty500_industry_mapping
from src.data.live_tv_fetcher import get_tv_fetcher
from src.screener.pipeline.swing.run_front_test import (
    load_state, STATE_FILE, save_state,
    dual_avwap_pullback_eval, volatility_compression_eval,
    trend_pullback_eval, connors_rsi_eval,
)
from src.screener.pipeline.swing.e19_strategy import generate_e19_signals, MAX_HOLDING_SESSIONS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ACTIVE_STRATEGY_NAME = "E19_Dual_AVWAP_Confluence"
MAX_PORTFOLIO_SLOTS = 5
DEFAULT_BASE_CAPITAL = 100000.0
SLOT_CAPITAL = DEFAULT_BASE_CAPITAL / MAX_PORTFOLIO_SLOTS  # 20,000 INR per slot
PORTFOLIO_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_state.json")


def send_telegram_message(message: str):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN_SWING")
    chat_id = os.getenv("TELEGRAM_CHAT_ID_SWING")
    
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
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN_SWING")
    chat_id = os.getenv("TELEGRAM_CHAT_ID_SWING")
    
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID not found. Skipping Telegram document.")
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


def load_portfolio_state():
    """Load persistent portfolio ledger. Backward-compatible with list-based state."""
    if os.path.exists(PORTFOLIO_STATE_FILE):
        try:
            with open(PORTFOLIO_STATE_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {
                        "strategy": ACTIVE_STRATEGY_NAME,
                        "base_capital": DEFAULT_BASE_CAPITAL,
                        "max_slots": MAX_PORTFOLIO_SLOTS,
                        "slot_capital": SLOT_CAPITAL,
                        "updated_at": None,
                        "trades": data
                    }
                return data
        except Exception as e:
            logger.error(f"Error loading {PORTFOLIO_STATE_FILE}: {e}")
            
    # Fallback to legacy STATE_FILE if exists
    legacy_trades = load_state()
    return {
        "strategy": ACTIVE_STRATEGY_NAME,
        "base_capital": DEFAULT_BASE_CAPITAL,
        "max_slots": MAX_PORTFOLIO_SLOTS,
        "slot_capital": SLOT_CAPITAL,
        "updated_at": None,
        "trades": legacy_trades
    }


def save_portfolio_state(portfolio: dict):
    """Save persistent portfolio ledger to tracked repository directory and mirror to front_testing."""
    portfolio["updated_at"] = datetime.now().isoformat()
    try:
        with open(PORTFOLIO_STATE_FILE, "w") as f:
            json.dump(portfolio, f, indent=4)
        logger.info(f"Saved live portfolio state to {PORTFOLIO_STATE_FILE}")
        
        # Mirror to STATE_FILE for compatibility with EOD scripts
        save_state(portfolio.get("trades", []))
    except Exception as e:
        logger.error(f"Error saving portfolio state: {e}")


def get_live_market_regime(nifty_hist):
    if nifty_hist is not None and not nifty_hist.empty and len(nifty_hist) >= 60:
        sma_50 = nifty_hist["Close"].rolling(50).mean()
        sma_50_diff = sma_50.diff()
        
        curr_close = nifty_hist["Close"].iloc[-1]
        curr_sma50 = sma_50.iloc[-1]
        curr_sma50_diff = sma_50_diff.iloc[-1]
        
        if curr_close > curr_sma50 and curr_sma50_diff > 0:
            return "Bullish"
        elif curr_close < curr_sma50 and curr_sma50_diff < 0:
            return "Bearish"
        else:
            return "Choppy"
    return "Unknown"


def compute_live_bcr(bulk_data, lookback_days=120, outcome_days=20, min_gap_days=30):
    """Breakout Continuation Rate using historical data only."""
    cutoff_end = pd.Timestamp.today() - pd.Timedelta(days=min_gap_days)
    cutoff_start = pd.Timestamp.today() - pd.Timedelta(days=lookback_days + outcome_days)
    
    continued = []
    for sym, df in bulk_data.items():
        if len(df) < 60:
            continue
        high_40 = df['High'].rolling(40).max().shift(1)
        mask = (df.index >= cutoff_start) & (df.index <= cutoff_end)
        for idx in df.index[mask]:
            pos = df.index.get_loc(idx)
            if pos + outcome_days >= len(df):
                continue
            if pd.notna(high_40.iloc[pos]) and df['Close'].iloc[pos] > high_40.iloc[pos]:
                entry_p = df['Close'].iloc[pos]
                future_p = df['Close'].iloc[pos + outcome_days]
                continued.append(1 if future_p > entry_p else 0)
    
    if len(continued) < 10:
        return 0.5
    return sum(continued) / len(continued)


def compute_live_breadth(bulk_data):
    """Market breadth: fraction of stocks with Close > 50-day SMA."""
    above = 0
    total = 0
    for sym, df in bulk_data.items():
        if len(df) < 50:
            continue
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        close = df['Close'].iloc[-1]
        if pd.notna(sma50):
            total += 1
            if close > sma50:
                above += 1
    return above / total if total > 0 else 0.5


def run_live_strategies(bulk_data, nifty_hist):
    """Execute canonical E19 Dual AVWAP Confluence strategy scanner."""
    return generate_e19_signals(
        bulk_data=bulk_data,
        nifty_hist=nifty_hist,
        as_of_date=pd.Timestamp.now(),
        industry_mapping=load_nifty500_industry_mapping(),
        evaluators={
            "dual_avwap_pullback": dual_avwap_pullback_eval,
            "volatility_compression": volatility_compression_eval,
            "trend_pullback": trend_pullback_eval,
            "connors_rsi": connors_rsi_eval,
        },
    )


def process_portfolio_exits(portfolio: dict, bulk_data: dict):
    """
    Evaluates all currently OPEN trades against live 3:15 PM market prices.
    Checks:
      1. Stop Loss: Low <= stop_loss
      2. Target: High >= target
      3. Time Stop: days_held >= MAX_HOLDING_SESSIONS (25 sessions)
    Marks closed trades with exit details and calculates live unrealized PnL for active holdings.
    """
    closed_today = []
    active_holdings = []
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')
    slot_cap = portfolio.get("slot_capital", SLOT_CAPITAL)
    
    for t in portfolio.get("trades", []):
        if t.get("status") != "OPEN":
            continue
            
        sym = t["symbol"]
        entry_price = float(t["entry_price"])
        stop_loss = float(t["stop_loss"])
        target = float(t["target"])
        shares = int(t.get("shares", max(1, int(slot_cap / entry_price))))
        t["shares"] = shares
        
        # Calculate holding period in business sessions
        try:
            entry_dt = datetime.strptime(t.get("entry_date", today_str), "%Y-%m-%d").date()
            days_held = int(np.busday_count(entry_dt, today))
        except Exception:
            days_held = 0
        t["days_held"] = days_held
        
        if sym in bulk_data and not bulk_data[sym].empty:
            df = bulk_data[sym]
            live_low = float(df['Low'].iloc[-1])
            live_high = float(df['High'].iloc[-1])
            live_close = float(df['Close'].iloc[-1])
            t["current_price"] = live_close
            
            # 1. Stop Loss Check
            if live_low <= stop_loss:
                pnl_pct = ((live_close - entry_price) / entry_price) * 100
                pnl_rs = (live_close - entry_price) * shares
                t["status"] = "CLOSED"
                t["exit_date"] = today_str
                t["exit_price"] = live_close
                t["exit_reason"] = "STOP LOSS"
                t["pnl_pct"] = round(pnl_pct, 2)
                t["pnl_rs"] = round(pnl_rs, 2)
                closed_today.append({
                    "symbol": sym,
                    "action": "SELL (STOP LOSS 🛑)",
                    "reason": "Hard Stop Loss Hit",
                    "price": live_close,
                    "stop_loss": stop_loss,
                    "target": target,
                    "pnl_pct": pnl_pct,
                    "pnl_rs": pnl_rs,
                    "shares": shares,
                    "days_held": days_held,
                    "strategy": t.get("strategy_name", ACTIVE_STRATEGY_NAME)
                })
            # 2. Profit Target Check
            elif live_high >= target:
                pnl_pct = ((live_close - entry_price) / entry_price) * 100
                pnl_rs = (live_close - entry_price) * shares
                t["status"] = "CLOSED"
                t["exit_date"] = today_str
                t["exit_price"] = live_close
                t["exit_reason"] = "TARGET"
                t["pnl_pct"] = round(pnl_pct, 2)
                t["pnl_rs"] = round(pnl_rs, 2)
                closed_today.append({
                    "symbol": sym,
                    "action": "SELL (TARGET 🎯)",
                    "reason": "Profit Target Hit",
                    "price": live_close,
                    "stop_loss": stop_loss,
                    "target": target,
                    "pnl_pct": pnl_pct,
                    "pnl_rs": pnl_rs,
                    "shares": shares,
                    "days_held": days_held,
                    "strategy": t.get("strategy_name", ACTIVE_STRATEGY_NAME)
                })
            # 3. Time Stop Check (25 trading sessions)
            elif days_held >= MAX_HOLDING_SESSIONS:
                pnl_pct = ((live_close - entry_price) / entry_price) * 100
                pnl_rs = (live_close - entry_price) * shares
                t["status"] = "CLOSED"
                t["exit_date"] = today_str
                t["exit_price"] = live_close
                t["exit_reason"] = f"TIME STOP ({days_held}d)"
                t["pnl_pct"] = round(pnl_pct, 2)
                t["pnl_rs"] = round(pnl_rs, 2)
                closed_today.append({
                    "symbol": sym,
                    "action": f"SELL (TIME STOP ⏳ {days_held}d)",
                    "reason": f"Max Holding {MAX_HOLDING_SESSIONS}d Reached",
                    "price": live_close,
                    "stop_loss": stop_loss,
                    "target": target,
                    "pnl_pct": pnl_pct,
                    "pnl_rs": pnl_rs,
                    "shares": shares,
                    "days_held": days_held,
                    "strategy": t.get("strategy_name", ACTIVE_STRATEGY_NAME)
                })
            else:
                # Active position continues
                unrealized_pct = ((live_close - entry_price) / entry_price) * 100
                unrealized_rs = (live_close - entry_price) * shares
                t["unrealized_pnl_pct"] = round(unrealized_pct, 2)
                t["unrealized_pnl_rs"] = round(unrealized_rs, 2)
                active_holdings.append(t)
        else:
            # Fallback if no fresh bar
            last_p = t.get("current_price", entry_price)
            unrealized_pct = ((last_p - entry_price) / entry_price) * 100
            unrealized_rs = (last_p - entry_price) * shares
            t["current_price"] = last_p
            t["unrealized_pnl_pct"] = round(unrealized_pct, 2)
            t["unrealized_pnl_rs"] = round(unrealized_rs, 2)
            active_holdings.append(t)
            
    return closed_today, active_holdings


def process_fresh_buys(portfolio: dict, active_holdings: list, raw_signals: list):
    """
    Slices and sizes fresh candidate signals based on available portfolio slots.
    Each slot allocates 20% equity (20,000 INR on standard 1 Lakh portfolio).
    """
    max_slots = portfolio.get("max_slots", MAX_PORTFOLIO_SLOTS)
    slot_capital = portfolio.get("slot_capital", SLOT_CAPITAL)
    today_str = date.today().strftime('%Y-%m-%d')
    now_iso = datetime.now().isoformat()
    
    active_symbols = {t["symbol"] for t in active_holdings}
    unique_candidates = [s for s in raw_signals if s["symbol"] not in active_symbols]
    
    available_slots = max(0, max_slots - len(active_holdings))
    
    actionable_buys = []
    watchlist_buys = []
    
    for i, cand in enumerate(unique_candidates):
        sym = cand["symbol"]
        price = float(cand["price"])
        sl = float(cand["stop_loss"])
        tgt = float(cand["target"])
        shares = max(1, int(slot_capital / price))
        alloc_rs = round(shares * price, 2)
        sl_pct = round(((price - sl) / price) * 100, 2)
        tgt_pct = round(((tgt - price) / price) * 100, 2)
        
        cand_enriched = {
            **cand,
            "recommended_shares": shares,
            "allocation_rs": alloc_rs,
            "sl_pct": sl_pct,
            "tgt_pct": tgt_pct,
        }
        
        if i < available_slots:
            actionable_buys.append(cand_enriched)
            # Add to persistent ledger
            new_trade = {
                "trade_id": str(uuid.uuid4()),
                "strategy_name": cand["strategy_name"],
                "symbol": sym,
                "signal_date": today_str,
                "signal_timestamp": now_iso,
                "entry_date": today_str,
                "entry_price": price,
                "current_price": price,
                "stop_loss": sl,
                "target": tgt,
                "shares": shares,
                "risk_pct": cand.get("risk_pct", 0.02),
                "alpha_score": cand.get("alpha_score", 0.0),
                "regime_state": cand.get("regime_state", 1),
                "bcr": cand.get("bcr", 0.5),
                "breadth": cand.get("breadth", 0.5),
                "status": "OPEN",
                "days_held": 0,
                "unrealized_pnl_pct": 0.0,
                "unrealized_pnl_rs": 0.0,
                "exit_date": None,
                "exit_price": None,
                "exit_reason": None,
                "pnl_pct": None,
            }
            portfolio.setdefault("trades", []).append(new_trade)
            active_holdings.append(new_trade)
        else:
            watchlist_buys.append(cand_enriched)
            
    return actionable_buys, watchlist_buys, available_slots


def build_unified_telegram_message(
    today_str: str,
    regime: str,
    bcr: float,
    breadth: float,
    closed_signals: list,
    actionable_buys: list,
    watchlist_buys: list,
    active_holdings: list,
    portfolio: dict
) -> str:
    """Constructs the institutional-grade unified single Telegram update."""
    max_slots = portfolio.get("max_slots", MAX_PORTFOLIO_SLOTS)
    slot_capital = portfolio.get("slot_capital", SLOT_CAPITAL)
    
    lines = []
    lines.append("<b>🏛️ E19 DUAL AVWAP CONFLUENCE — DAILY UPDATE</b>")
    lines.append(f"📅 Date: <code>{today_str}</code> | 3:15 PM MOC Execution\n")
    
    # -------------------------------------------------------------
    # 1. 🟢 FRESH BUY ORDERS TODAY
    # -------------------------------------------------------------
    lines.append("<b>🟢 FRESH BUY ORDERS TODAY (3:15 PM MOC):</b>")
    if not actionable_buys:
        if watchlist_buys and len(active_holdings) >= max_slots:
            lines.append("• <i>No slots available (Portfolio 5/5 Full). Top candidates for watchlist:</i>")
            for item in watchlist_buys[:2]:
                lines.append(
                    f"• <b>{item['symbol']}</b> (Watchlist Only)\n"
                    f"  ├ Price: ₹{item['price']:.2f} | Alpha: {item.get('alpha_score', 0):.3f}\n"
                    f"  └ SL: ₹{item['stop_loss']:.2f} | TGT: ₹{item['target']:.2f}"
                )
        else:
            lines.append(f"• None today (Regime: {regime} | Cash preserved)")
    else:
        for item in actionable_buys:
            lines.append(
                f"• <b>{item['symbol']}</b> | {item.get('strategy', 'E19 Confluence')}\n"
                f"  ├ Entry Price (CMP): <b>₹{item['price']:.2f}</b>\n"
                f"  ├ Hard Stop Loss: ₹{item['stop_loss']:.2f} (-{item.get('sl_pct', 0):.1f}%)\n"
                f"  ├ Target: ₹{item['target']:.2f} (+{item.get('tgt_pct', 0):.1f}%)\n"
                f"  ├ Sizing: 1 Slot (₹{slot_capital:,.0f} / 20% equity)\n"
                f"  └ <b>Recommended Qty: {item.get('recommended_shares', 1)} shares</b> (₹{item.get('allocation_rs', 0):,.0f})"
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
            pnl_sign = "+" if item.get('pnl_pct', 0) >= 0 else ""
            lines.append(
                f"• <b>{item['symbol']}</b> — {item.get('action', 'EXIT')}\n"
                f"  ├ Exit Price: ₹{item.get('price', 0):.2f}\n"
                f"  ├ Realized PnL: <b>{pnl_sign}{item.get('pnl_pct', 0):.2f}%</b> ({pnl_sign}₹{item.get('pnl_rs', 0):,.0f})\n"
                f"  └ Held: {item.get('days_held', 0)} sessions"
            )
    lines.append("")
    
    # -------------------------------------------------------------
    # 3. 💼 ACTIVE PORTFOLIO TRACKER (HOLDINGS)
    # -------------------------------------------------------------
    lines.append("<b>💼 ACTIVE PORTFOLIO TRACKER (Holdings):</b>")
    if not active_holdings:
        lines.append("• No open positions currently (100% Cash buffer preserved)")
    else:
        for idx, pos in enumerate(active_holdings, 1):
            cur_p = pos.get("current_price", pos["entry_price"])
            ent_p = pos["entry_price"]
            pnl_pct = pos.get("unrealized_pnl_pct", ((cur_p - ent_p) / ent_p) * 100)
            pnl_rs = pos.get("unrealized_pnl_rs", (cur_p - ent_p) * pos.get("shares", 1))
            pnl_sign = "+" if pnl_pct >= 0 else ""
            held = pos.get("days_held", 0)
            tag = " <i>(NEW)</i>" if held == 0 else ""
            held_str = f"Held: {held} / {MAX_HOLDING_SESSIONS} sessions" if held > 0 else "Held: Day 0 (New Entry Today)"
            
            lines.append(
                f"<b>{idx}. {pos['symbol']}</b>{tag} ({pos.get('shares', 1)} shares)\n"
                f"   ├ Entry: ₹{ent_p:.2f} | CMP: ₹{cur_p:.2f}\n"
                f"   ├ PnL: <b>{pnl_sign}{pnl_pct:.2f}%</b> ({pnl_sign}₹{pnl_rs:,.0f})\n"
                f"   ├ SL: ₹{pos['stop_loss']:.2f} | TGT: ₹{pos['target']:.2f}\n"
                f"   └ {held_str}"
            )
    lines.append("")
    
    # -------------------------------------------------------------
    # 4. 📊 PORTFOLIO HEALTH & CAPITAL ALLOCATION
    # -------------------------------------------------------------
    occupied_slots = len(active_holdings)
    invested_pct = (occupied_slots / max_slots) * 100
    cash_pct = 100.0 - invested_pct
    cash_amount = max(0, max_slots - occupied_slots) * slot_capital
    
    total_unrealized_rs = sum(
        (p.get("current_price", p["entry_price"]) - p["entry_price"]) * p.get("shares", 1)
        for p in active_holdings
    )
    total_invested_cost = sum(
        p["entry_price"] * p.get("shares", 1) for p in active_holdings
    )
    total_pnl_pct = (total_unrealized_rs / total_invested_cost * 100) if total_invested_cost > 0 else 0.0
    pnl_sign = "+" if total_unrealized_rs >= 0 else ""
    
    lines.append("<b>📊 PORTFOLIO HEALTH & CAPITAL ALLOCATION:</b>")
    lines.append(f"• Slots: <b>{occupied_slots} / {max_slots} Occupied</b> ({invested_pct:.0f}% Invested, {cash_pct:.0f}% Cash)")
    lines.append(f"• Cash Buffer: ₹{cash_amount:,.0f} ({cash_pct:.0f}%)")
    if occupied_slots > 0:
        lines.append(f"• Total Unrealized PnL: <b>{pnl_sign}₹{total_unrealized_rs:,.0f}</b> ({pnl_sign}{total_pnl_pct:.2f}%)")
    lines.append(f"• Market Regime: <b>{regime}</b> (BCR: {bcr*100:.1f}% | Breadth: {breadth*100:.1f}%)")
    
    return "\n".join(lines)


def print_terminal_dashboard(closed_signals, actionable_buys, active_holdings, regime, bcr, breadth):
    print(f"\n{'='*95}")
    print(f"{'E19 DUAL AVWAP CONFLUENCE — LIVE PORTFOLIO DASHBOARD (3:15 PM MOC)'.center(95)}")
    print(f"{'='*95}")
    print(f"Market Regime: {regime:<10} | BCR: {bcr*100:.1f}% | Breadth: {breadth*100:.1f}%")
    print(f"{'-'*95}")
    
    # Exits
    print(f"\n[1] 🔴 SELL / EXIT SIGNALS TODAY ({len(closed_signals)}):")
    if not closed_signals:
        print("    None. All positions holding.")
    else:
        print(f"    {'SYMBOL':<14} | {'ACTION':<22} | {'EXIT PRICE':<12} | {'PNL %':<10} | {'REASON'}")
        print("    " + "-"*75)
        for s in closed_signals:
            print(f"    {s['symbol']:<14} | {s['action']:<22} | ₹{s['price']:<11.2f} | {s['pnl_pct']:>+6.2f}%    | {s['reason']}")
            
    # Fresh Buys
    print(f"\n[2] 🟢 FRESH BUY ORDERS TODAY ({len(actionable_buys)}):")
    if not actionable_buys:
        print("    None today.")
    else:
        print(f"    {'SYMBOL':<14} | {'ENTRY (CMP)':<12} | {'STOP LOSS':<12} | {'TARGET':<12} | {'QTY':<6} | {'ALLOCATION'}")
        print("    " + "-"*75)
        for b in actionable_buys:
            print(f"    {b['symbol']:<14} | ₹{b['price']:<11.2f} | ₹{b['stop_loss']:<11.2f} | ₹{b['target']:<11.2f} | {b['recommended_shares']:<6} | ₹{b['allocation_rs']:,.0f}")
            
    # Active Portfolio
    print(f"\n[3] 💼 ACTIVE PORTFOLIO TRACKER ({len(active_holdings)} / 5 SLOTS):")
    if not active_holdings:
        print("    No open positions (100% Cash cushion preserved).")
    else:
        print(f"    {'#':<3} {'SYMBOL':<12} | {'ENTRY':<10} | {'CMP':<10} | {'UNREALIZED PNL':<18} | {'HELD':<6} | {'STOP':<10} | {'TARGET'}")
        print("    " + "-"*85)
        for i, pos in enumerate(active_holdings, 1):
            cur_p = pos.get("current_price", pos["entry_price"])
            pnl_pct = pos.get("unrealized_pnl_pct", 0.0)
            pnl_rs = pos.get("unrealized_pnl_rs", 0.0)
            held = f"{pos.get('days_held', 0)}d/{MAX_HOLDING_SESSIONS}d"
            print(f"    {i:<3} {pos['symbol']:<12} | ₹{pos['entry_price']:<9.2f} | ₹{cur_p:<9.2f} | {pnl_pct:>+6.2f}% (₹{pnl_rs:>+7,.0f}) | {held:<6} | ₹{pos['stop_loss']:<9.2f} | ₹{pos['target']:.2f}")
            
    print(f"\n{'='*95}\n")


def main():
    print("\n" + "*"*70)
    print("LIVE MARKET SCREENER & PORTFOLIO ENGINE (3:15 PM MOC)".center(70))
    print("*"*70 + "\n")
    
    logger.info("Loading NIFTY 500 universe...")
    symbols = load_nifty500_symbols()
    symbols.append("NIFTYBEES")
    
    fetcher = get_tv_fetcher()
    bulk_data = fetcher.fetch_bulk_live_cached(symbols, n_bars=250)
    
    if "NIFTYBEES" not in bulk_data:
        logger.error("Failed to fetch NIFTYBEES for benchmark. Exiting.")
        return
        
    nifty_hist = bulk_data.pop("NIFTYBEES")
    regime = get_live_market_regime(nifty_hist)
    bcr = compute_live_bcr(bulk_data)
    breadth = compute_live_breadth(bulk_data)
    
    logger.info(f"Market Regime: {regime} | BCR: {bcr:.4f} | Breadth: {breadth:.4f}")
    
    # 1. Load persistent portfolio state
    portfolio = load_portfolio_state()
    
    # 2. Process exits for existing positions
    logger.info("Evaluating active portfolio positions against live prices...")
    closed_signals, active_holdings = process_portfolio_exits(portfolio, bulk_data)
    
    # 3. Scan for new candidate signals
    logger.info("Scanning for fresh E19 Dual AVWAP Confluence signals...")
    raw_signals = run_live_strategies(bulk_data, nifty_hist)
    
    # 4. Allocate into open slots
    actionable_buys, watchlist_buys, available_slots = process_fresh_buys(portfolio, active_holdings, raw_signals)
    
    # 5. Persist state
    save_portfolio_state(portfolio)
    
    # 6. Print terminal view
    print_terminal_dashboard(closed_signals, actionable_buys, active_holdings, regime, bcr, breadth)
    
    # 7. Construct and send unified Telegram message
    today_str = date.today().strftime('%Y-%m-%d')
    tg_msg = build_unified_telegram_message(
        today_str=today_str,
        regime=regime,
        bcr=bcr,
        breadth=breadth,
        closed_signals=closed_signals,
        actionable_buys=actionable_buys,
        watchlist_buys=watchlist_buys,
        active_holdings=active_holdings,
        portfolio=portfolio
    )
    
    send_telegram_message(tg_msg)
    

if __name__ == "__main__":
    main()
