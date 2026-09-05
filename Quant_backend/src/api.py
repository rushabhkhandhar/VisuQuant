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

from src.services.screener_service import run_e19_screener

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
    results = run_e19_screener(as_of_date=req.date, top_n=req.top_n, check_regime=True)
    return results

@app.post("/api/screener_stream")
def trigger_screener_stream(req: ScreenerRequest):
    q = queue.Queue()

    def progress_callback(msg, level="INFO"):
        q.put({"type": "log", "message": msg, "level": level})

    def run_engine():
        try:
            results = run_e19_screener(
                as_of_date=req.date,
                top_n=req.top_n,
                check_regime=True,
                progress_callback=progress_callback,
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
    from src.services.backtest_service import run_single_stock_backtest
    try:
        res = run_single_stock_backtest(symbol=req.symbol, months=req.months)
        if res.get("status") == "error":
            return res
        return {"status": "success", "data": res}
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
    from src.services.chart_service import fetch_chart_payload
    return fetch_chart_payload(symbol, period)


_SYMBOL_UNIVERSE_CACHE = []

def _load_symbol_universe():
    global _SYMBOL_UNIVERSE_CACHE
    if _SYMBOL_UNIVERSE_CACHE:
        return _SYMBOL_UNIVERSE_CACHE
    indices = ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY"]
    symbols = set(indices)
    try:
        from src.data.nse_fetcher import load_nifty500_symbols
        symbols.update(load_nifty500_symbols())
    except Exception:
        pass
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

@app.get("/api/market_overview")
def get_market_overview_endpoint(refresh: bool = False):
    from src.services.market_service import fetch_market_overview
    return fetch_market_overview(force_refresh=refresh)

@app.get("/api/market_stream")
def stream_market_overview(interval: int = 10):
    from src.services.market_service import fetch_market_overview
    import time
    def event_generator():
        while True:
            data = fetch_market_overview(force_refresh=False)
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(max(5, min(interval, 60)))
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=5000, reload=True)

