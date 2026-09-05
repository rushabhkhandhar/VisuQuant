from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
import shutil
import queue
import threading
import json
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Add the project root (Quant_backend) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.screener.pipeline.archive.run_daily_screen import run_screener

app = FastAPI(title="VisuQuant Engine API")

# Allow Next.js frontend to communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.29.120:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

outputs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
os.makedirs(outputs_dir, exist_ok=True)

class ScreenerRequest(BaseModel):
    date: Optional[str] = None # format: YYYY-MM-DD
    top_n: int = 5

class CustomScreenerRequest(BaseModel):
    date: Optional[str] = None # format: YYYY-MM-DD
    top_n: int = 20
    trading_tools: list[str] = []
    trading_filters: list[str] = []
    risk_management: str = "1.5x ATR"
    ai_logic_prompt: Optional[str] = None
    ai_filter_prompt: Optional[str] = None
    gemini_api_key: Optional[str] = None

class BacktestRequest(BaseModel):
    symbol: str
    months: int = 60

@app.post("/api/screener")
def trigger_screener(req: ScreenerRequest):
    as_of_date = None
    if req.date:
        as_of_date = datetime.strptime(req.date, "%Y-%m-%d").date()
        
    # We use dry_run=True so it doesn't trigger side effects, just returns the data
    results = run_screener(as_of_date=as_of_date, dry_run=True, top_n=req.top_n, check_regime=True)
    return results

@app.post("/api/screener_stream")
def trigger_screener_stream(req: ScreenerRequest):
    as_of_date = None
    if req.date:
        as_of_date = datetime.strptime(req.date, "%Y-%m-%d").date()

    q = queue.Queue()

    def progress_callback(msg, level="INFO"):
        q.put({"type": "log", "message": msg, "level": level})

    def run_engine():
        try:
            results = run_screener(as_of_date=as_of_date, dry_run=True, top_n=req.top_n, check_regime=True, progress_callback=progress_callback)
            q.put({"type": "result", "data": results})
        except Exception as e:
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(None)  # Sentinel to stop stream

    thread = threading.Thread(target=run_engine)
    thread.start()

    def event_generator():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/custom_screener_stream")
def trigger_custom_screener_stream(req: CustomScreenerRequest):
    as_of_date = None
    if req.date:
        as_of_date = datetime.strptime(req.date, "%Y-%m-%d").date()

    q = queue.Queue()

    def progress_callback(msg, level="INFO"):
        q.put({"type": "log", "message": msg, "level": level})

    def run_engine():
        from src.screener.pipeline.archive.run_custom_screen import run_custom_screener
        try:
            results = run_custom_screener(
                as_of_date=as_of_date, 
                trading_tools=req.trading_tools,
                trading_filters=req.trading_filters,
                risk_management=req.risk_management,
                ai_logic_prompt=req.ai_logic_prompt,
                ai_filter_prompt=req.ai_filter_prompt,
                gemini_api_key=req.gemini_api_key,
                top_n=req.top_n, 
                progress_callback=progress_callback
            )
            q.put({"type": "result", "data": results})
        except Exception as e:
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(None)  # Sentinel to stop stream

    thread = threading.Thread(target=run_engine)
    thread.start()

    def event_generator():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/health")
def health_check():
    return {"status": "VisuQuant Engine Online"}

class AnalyzeRequest(BaseModel):
    symbol: str
    date: Optional[str] = None

@app.post("/api/analyze")
def run_analysis(req: AnalyzeRequest):
    from src.workflow.graph import build_graph
    from src.reporting.storage import persist_pipeline_results
    import time
    
    app_graph = build_graph()
    payload = {"ticker": req.symbol.strip(), "as_of_date": req.date}
    
    start_time = time.time()
    final_state = app_graph.invoke(payload)
    end_time = time.time()
    
    pdf_path = persist_pipeline_results(final_state, start_time, end_time)
    
    if pdf_path:
        rel_path = os.path.relpath(pdf_path, outputs_dir)
        return {"status": "success", "pdf_url": f"http://localhost:5000/api/download_report?path={rel_path}"}
    
    return {"status": "error", "message": "Failed to generate PDF"}

@app.get("/api/download_report")
def download_report(path: str, background_tasks: BackgroundTasks):
    if not path.endswith(".pdf"):
        return {"error": "Only PDF files are allowed"}
        
    full_path = os.path.abspath(os.path.join(outputs_dir, path))
    
    # Security check to prevent directory traversal
    if not full_path.startswith(outputs_dir):
        return {"error": "Invalid path"}
        
    if not os.path.exists(full_path):
        return {"error": "File not found or already deleted. Please run the analysis again."}
        
    # Parent directory to delete
    folder_to_delete = os.path.dirname(full_path)
    
    def cleanup():
        import time
        # Wait for FastAPI to stream the file to the client before deleting
        time.sleep(3)
        try:
            if os.path.exists(folder_to_delete) and folder_to_delete.startswith(outputs_dir):
                shutil.rmtree(folder_to_delete)
                print(f"Auto-deleted output folder: {folder_to_delete}")
        except Exception as e:
            print(f"Failed to cleanup folder: {e}")
            
    background_tasks.add_task(cleanup)
    
    
    filename = os.path.basename(full_path)
    return FileResponse(path=full_path, filename=filename, media_type="application/pdf")

@app.post("/api/backtest")
def run_strategy_backtest(req: BacktestRequest):
    from src.screener.pipeline.swing.backtest import run_backtest
    try:
        results = run_backtest(months=req.months, symbols=[req.symbol.strip()], return_json=True)
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/backtest_custom_strategy")
def backtest_custom_strategy_endpoint(req: CustomScreenerRequest):
    from src.screener.pipeline.archive.run_custom_backtest import run_custom_backtest
    try:
        results = run_custom_backtest(
            months=12,
            trading_tools=req.trading_tools,
            trading_filters=req.trading_filters,
            risk_management=req.risk_management,
            ai_logic_prompt=req.ai_logic_prompt,
            ai_filter_prompt=req.ai_filter_prompt,
            gemini_api_key=req.gemini_api_key
        )
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/company_filings")
def get_company_filings(symbol: str):
    from src.data.screener_in_client import get_screener_data_sync
    try:
        data = get_screener_data_sync(symbol.strip().upper())
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/chart_data")
def get_chart_data(symbol: str, period: str = "6mo"):
    import yfinance as yf
    import numpy as np
    try:
        raw_sym = symbol.strip().upper()
        clean_sym = raw_sym.replace("NSE:", "").replace("BSE:", "").replace(".NS", "").replace(".BO", "").strip()

        if clean_sym in ["NIFTY", "NIFTY 50", "^NSEI", "NIFTY50"]:
            ticker_str = "^NSEI"
            display_sym = "NIFTY 50"
        elif clean_sym in ["BANKNIFTY", "BANK NIFTY", "^NSEBANK"]:
            ticker_str = "^NSEBANK"
            display_sym = "BANK NIFTY"
        elif clean_sym in ["SENSEX", "^BSESN"]:
            ticker_str = "^BSESN"
            display_sym = "SENSEX"
        else:
            ticker_str = f"{clean_sym}.NS"
            display_sym = clean_sym

        t = yf.Ticker(ticker_str)
        df = t.history(period=period)
        if df.empty and not ticker_str.endswith(".BO") and not ticker_str.startswith("^"):
            ticker_str = f"{clean_sym}.BO"
            t = yf.Ticker(ticker_str)
            df = t.history(period=period)

        if df.empty:
            # Fallback to local NSE Bhavcopy history cache (2,600+ symbols)
            from datetime import date as dt_date
            from src.data.nse_fetcher import fetch_bulk_history
            lookback = 30 if period == "1mo" else 90 if period == "3mo" else 365 if period == "1y" else 180
            bulk = fetch_bulk_history([clean_sym], dt_date.today(), lookback)
            if clean_sym in bulk and not bulk[clean_sym].empty:
                df = bulk[clean_sym].copy()

        if df.empty:
            return {"status": "error", "message": f"Symbol '{raw_sym}' is not a valid NSE/BSE ticker or has no trading data."}

        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

        # Bollinger Bands (20, 2)
        sma20 = df["Close"].rolling(window=20, min_periods=1).mean()
        std20 = df["Close"].rolling(window=20, min_periods=1).std().fillna(0)
        df["BB_Upper"] = sma20 + (std20 * 2)
        df["BB_Lower"] = sma20 - (std20 * 2)

        # 14-period RSI
        delta = df["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = np.where(avg_loss != 0, avg_gain / avg_loss, 0)
        df["RSI"] = np.where(np.isnan(rs), 50.0, 100 - (100 / (1 + rs)))

        # MACD (12, 26, 9)
        ema12 = df["Close"].ewm(span=12, adjust=False).mean()
        ema26 = df["Close"].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        df["MACD"] = macd
        df["MACD_Signal"] = macd_signal
        df["MACD_Hist"] = macd - macd_signal

        # Cumulative Anchored VWAP
        v = df["Volume"].values
        tp = ((df["High"] + df["Low"] + df["Close"]) / 3.0).values
        cum_v = np.cumsum(v)
        cum_vp = np.cumsum(tp * v)
        avwap = np.where(cum_v > 0, cum_vp / cum_v, df["Close"].values)
        df["AVWAP"] = avwap

        candles = []
        volume = []
        avwap_data = []
        ema20_data = []
        ema50_data = []
        ema200_data = []
        bb_upper_data = []
        bb_lower_data = []
        rsi_data = []
        macd_data = []
        macd_signal_data = []
        macd_hist_data = []

        for idx, row in df.iterrows():
            time_str = idx.strftime("%Y-%m-%d")
            o = round(float(row["Open"]), 2)
            h = round(float(row["High"]), 2)
            l = round(float(row["Low"]), 2)
            c = round(float(row["Close"]), 2)
            vol = int(row["Volume"]) if not np.isnan(row["Volume"]) else 0

            candles.append({"time": time_str, "open": o, "high": h, "low": l, "close": c})
            volume.append({
                "time": time_str,
                "value": vol,
                "color": "rgba(0, 255, 136, 0.5)" if c >= o else "rgba(255, 51, 102, 0.5)"
            })
            avwap_data.append({"time": time_str, "value": round(float(row["AVWAP"]), 2)})
            ema20_data.append({"time": time_str, "value": round(float(row["EMA20"]), 2)})
            ema50_data.append({"time": time_str, "value": round(float(row["EMA50"]), 2)})
            ema200_data.append({"time": time_str, "value": round(float(row["EMA200"]), 2)})
            bb_upper_data.append({"time": time_str, "value": round(float(row["BB_Upper"]), 2)})
            bb_lower_data.append({"time": time_str, "value": round(float(row["BB_Lower"]), 2)})
            rsi_val = round(float(row["RSI"]), 2) if not np.isnan(row["RSI"]) else 50.0
            rsi_data.append({"time": time_str, "value": rsi_val})
            macd_data.append({"time": time_str, "value": round(float(row["MACD"]), 2)})
            macd_signal_data.append({"time": time_str, "value": round(float(row["MACD_Signal"]), 2)})
            m_hist = round(float(row["MACD_Hist"]), 2)
            macd_hist_data.append({
                "time": time_str,
                "value": m_hist,
                "color": "rgba(0, 255, 136, 0.6)" if m_hist >= 0 else "rgba(255, 51, 102, 0.6)"
            })

        return {
            "status": "success",
            "symbol": clean_sym,
            "candles": candles,
            "volume": volume,
            "avwap": avwap_data,
            "ema20": ema20_data,
            "ema50": ema50_data,
            "ema200": ema200_data,
            "bb_upper": bb_upper_data,
            "bb_lower": bb_lower_data,
            "rsi": rsi_data,
            "macd": macd_data,
            "macd_signal": macd_signal_data,
            "macd_hist": macd_hist_data,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

_SYMBOL_UNIVERSE_CACHE = []

def _load_symbol_universe():
    global _SYMBOL_UNIVERSE_CACHE
    if _SYMBOL_UNIVERSE_CACHE:
        return _SYMBOL_UNIVERSE_CACHE
    indices = ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY"]
    symbols = set(indices)
    try:
        import glob
        bhavcopy_files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "data/bhavcopy_cache/*.parquet")))
        if bhavcopy_files:
            import pandas as pd
            df = pd.read_parquet(bhavcopy_files[-1])
            symbols.update(df.index.astype(str).tolist())
    except Exception:
        pass
    _SYMBOL_UNIVERSE_CACHE = sorted(list(symbols))
    return _SYMBOL_UNIVERSE_CACHE

@app.get("/api/search_symbols")
def search_symbols(q: str = ""):
    query = q.strip().upper().replace("NSE:", "").replace("BSE:", "").replace(".NS", "")
    universe = _load_symbol_universe()
    if not query:
        return {
            "query": "",
            "symbols": ["NIFTY", "BANKNIFTY", "TCS", "INFY", "RELIANCE", "TATASTEEL", "TATAPOWER", "HDFCBANK", "ICICIBANK", "DIXON", "MTARTECH"]
        }
    prefix_matches = [s for s in universe if s.startswith(query)]
    contains_matches = [s for s in universe if query in s and not s.startswith(query)]
    results = (prefix_matches + contains_matches)[:12]
    return {"query": query, "symbols": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=5000, reload=True)

