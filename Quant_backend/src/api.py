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

from src.screener.pipeline.run_daily_screen import run_screener

app = FastAPI(title="VisuQuant Engine API")

# Allow Next.js frontend to communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
        from src.screener.pipeline.run_custom_screen import run_custom_screener
        try:
            results = run_custom_screener(
                as_of_date=as_of_date, 
                trading_tools=req.trading_tools, 
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
    payload = {"ticker": req.symbol, "as_of_date": req.date}
    
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
    from src.screener.pipeline.backtest import run_backtest
    try:
        results = run_backtest(months=req.months, symbols=[req.symbol], return_json=True)
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=5000, reload=True)
