from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

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

class ScreenerRequest(BaseModel):
    date: Optional[str] = None # format: YYYY-MM-DD
    top_n: int = 5

@app.post("/api/screener")
def trigger_screener(req: ScreenerRequest):
    as_of_date = None
    if req.date:
        as_of_date = datetime.strptime(req.date, "%Y-%m-%d").date()
        
    # We use dry_run=True so it doesn't trigger side effects, just returns the data
    results = run_screener(as_of_date=as_of_date, dry_run=True, top_n=req.top_n, check_regime=True)
    return results

@app.get("/api/health")
def health_check():
    return {"status": "VisuQuant Engine Online"}
