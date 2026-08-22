import os
import sys
import logging
from datetime import date
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))))

from src.data.nse_fetcher import fetch_bulk_history, load_fno_symbols, load_nifty500_industry_mapping
from src.screener.pipeline.fno.strategies.long.config_cash import STRATEGY_CONFIG
from src.screener.pipeline.fno.strategies.long.screener import FnoLongScreener
from src.screener.pipeline.intraday.features import calculate_atr
from src.screener.pipeline.metrics import calculate_and_log_metrics

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class CashLongBacktest:
    def __init__(self, config):
        self.config = config
        self.capital = config['starting_capital']
        self.trades = []
        self.daily_equity = []
        self.screener = FnoLongScreener(config)

    def run(self):
        logger.info("Initializing Cash Swing Long Backtest (1 Lakh Account)...")
        symbols = load_fno_symbols()
        ind_map = load_nifty500_industry_mapping()
        
        logger.info("Fetching static Cash EOD data for 1700 days. This might take a few minutes if not cached...")
        cash_data = fetch_bulk_history(symbols, end_date=date.today(), lookback_days=1700)
        
        if not cash_data:
            logger.error("No cash data downloaded.")
            return
            
        # Get common trading days based on the stock with the most complete history
        longest_symbol = max(cash_data.keys(), key=lambda s: len(cash_data[s]))
        ref_df = cash_data.get(longest_symbol)
        trading_days = pd.Series(ref_df.index.date).unique()[50:] # Skip first 50 days for lookback buffers
        
        logger.info(f"Running simulation over {len(trading_days)} days...")
        
        open_positions = []
        
        for current_date in trading_days:
            # 1. Manage open positions
            remaining_positions = []
            for pos in open_positions:
                sym = pos['symbol']
                sym_df = cash_data.get(sym)
                if sym_df is None: continue
                
                # Get today's candle
                today_df = sym_df[sym_df.index.date == current_date]
                if today_df.empty: 
                    remaining_positions.append(pos)
                    continue
                    
                t_row = today_df.iloc[0]
                exit_price = 0
                exit_type = ""
                
                # Check for stop loss or target (assume SL hit first if both hit in same day for conservative backtest)
                if t_row['Low'] <= pos['sl']:
                    exit_price = pos['sl']
                    exit_type = "STOP_LOSS"
                elif t_row['High'] >= pos['target']:
                    exit_price = pos['target']
                    exit_type = "TARGET"
                    
                if exit_price > 0:
                    # Execute Exit
                    gross_pnl = (exit_price - pos['entry_price']) * pos['qty']
                    
                    # Estimate costs for Equity Delivery (0.1% STT on both buy and sell, max 20 Rs brokerage)
                    turnover = (pos['entry_price'] + exit_price) * pos['qty']
                    stt = turnover * 0.001 # 0.1% STT on delivery trades
                    brokerage = 40 # 20 on buy, 20 on sell
                    exchange_charges = turnover * 0.0000325
                    costs = stt + brokerage + exchange_charges
                    
                    net_pnl = gross_pnl - costs
                    self.capital += net_pnl
                    
                    self.trades.append({
                        "Date_Entry": pos['entry_date'],
                        "Date_Exit": current_date,
                        "Symbol": sym,
                        "Entry": pos['entry_price'],
                        "Exit": exit_price,
                        "Qty": pos['qty'],
                        "Net_PnL": net_pnl,
                        "Type": exit_type
                    })
                else:
                    remaining_positions.append(pos)
                    
            open_positions = remaining_positions
            
            # 2. Find new setups if we have room
            slots_available = self.config['max_open_positions'] - len(open_positions)
            if slots_available > 0:
                picks = self.screener.screen(current_date, cash_data, ind_map)
                
                for sym in picks:
                    if slots_available == 0: break
                    # Don't double down
                    if any(p['symbol'] == sym for p in open_positions): continue
                    
                    # Execute entry on Cash Market
                    sym_df = cash_data.get(sym)
                    if sym_df is None: continue
                    
                    slice_df = sym_df[sym_df.index.date <= current_date]
                    if slice_df.empty: continue
                    
                    # Assume entry at Close price (3:15 PM proxy)
                    entry_price = slice_df['Close'].iloc[-1]
                    
                    atr = calculate_atr(slice_df, period=self.config['atr_period'])
                    if atr == 0: continue
                    
                    sl = entry_price - (atr * self.config['atr_stop_loss_multiplier'])
                    risk_per_share = entry_price - sl
                    if risk_per_share <= 0: continue
                    
                    # Exact Fractional/Integer Position Sizing for Cash Market
                    max_risk = self.capital * self.config['risk_per_trade_pct']
                    desired_qty = int(max_risk / risk_per_share)
                    
                    if desired_qty == 0: continue
                    
                    # Check if we can afford the total capital for delivery
                    # Since we only buy 2 stocks max, we divide total capital by 2 for max allocation per trade
                    max_capital_per_trade = self.capital / float(self.config['max_open_positions'])
                    cost_to_buy = desired_qty * entry_price
                    
                    if cost_to_buy > max_capital_per_trade:
                        # Cap the quantity to what we can physically afford
                        desired_qty = int(max_capital_per_trade / entry_price)
                        if desired_qty == 0: continue
                        
                    target = entry_price + (risk_per_share * self.config['target_r_multiple'])
                    
                    open_positions.append({
                        "symbol": sym,
                        "entry_date": current_date,
                        "entry_price": entry_price,
                        "qty": desired_qty,
                        "sl": sl,
                        "target": target
                    })
                    slots_available -= 1
                    
            # Track daily equity (MTM)
            total_equity = self.capital
            for pos in open_positions:
                sym_df = cash_data.get(pos['symbol'])
                if sym_df is not None:
                    today_df = sym_df[sym_df.index.date <= current_date]
                    if not today_df.empty:
                        current_price = today_df.iloc[-1]['Close']
                        unrealized_pnl = (current_price - pos['entry_price']) * pos['qty']
                        total_equity += unrealized_pnl
            
            self.daily_equity.append({"Date": current_date, "Equity": total_equity})
            
        self.generate_report()

    def generate_report(self):
        trades_df = pd.DataFrame(self.trades)
        
        # Calculate summary metrics using the standardized metrics pipeline
        output_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(output_dir, exist_ok=True)
        
        metrics = calculate_and_log_metrics(
            strategy_name="Cash Long",
            config=self.config,
            trades=self.trades,
            daily_equity=self.daily_equity,
            output_dir=output_dir
        )
        
        if not trades_df.empty:
            trades_df.to_csv(os.path.join(output_dir, "cash_long_results.csv"), index=False)
            
        if metrics:
            summary_text = (
                f"=== CASH LONG STRATEGY RESULTS ===\n"
                f"Total Trades: {metrics['Total Trades']}\n"
                f"Win Rate: {metrics['Win Rate (%)']:.2f}%\n"
                f"Total Net PnL: Rs {metrics['Overall Profit (Rs)']:.2f}\n"
                f"Final Capital: Rs {self.capital:.2f}\n"
                f"CAGR: {metrics['CAGR (%)']:.2f}%\n"
                f"Max Drawdown: {metrics['Max Drawdown (%)']:.2f}%\n"
                f"Sharpe Ratio: {metrics['Sharpe Ratio']:.2f}\n"
                f"Sortino Ratio: {metrics['Sortino Ratio']:.2f}\n"
            )
            print("\n" + summary_text)
            
            with open(os.path.join(output_dir, "cash_long_summary.txt"), "w") as f:
                f.write(summary_text)
                
            logger.info(f"Results saved to {output_dir}")

if __name__ == "__main__":
    backtest = CashLongBacktest(STRATEGY_CONFIG)
    backtest.run()
