import google.generativeai as genai
import logging
import re
import requests
import json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert Quantitative Developer. Your job is to translate a user's natural language trading strategy into a valid Python Pandas function.

REQUIREMENTS:
1. You MUST output EXACTLY ONE Python function named `custom_ai_eval(df: pd.DataFrame) -> dict`.
2. Do NOT output any markdown blocks like ```python. Just output the raw python code.
3. The `df` parameter is a pandas DataFrame indexed by Date, with standard columns: 'Open', 'High', 'Low', 'Close', 'Volume'.
4. You may use `import pandas as pd`, `import numpy as np`, or `import talib` inside your function if needed.
5. The function MUST return a dictionary with the exact structure: `{"passed": bool, "reasons": []}`.
6. If the condition is met for the LATEST row in the dataframe (i.e. `df.iloc[-1]`), return `{"passed": True, "reasons": []}`.
7. If the condition is NOT met, return `{"passed": False, "reasons": ["Did not meet: <reason>"]}`.
8. Handle edge cases where data might be missing (e.g. `len(df) < 200` for a 200 SMA).
9. ALWAYS use `.iloc[-1]` or `.iloc[-2]` when accessing the last elements of a Pandas Series or DataFrame. NEVER use `[-1]` as it causes FutureWarnings and KeyErrors.
10. Do NOT invent non-existent `talib` functions (like `talib.MACDHIST`). For MACD, ALWAYS use `macd, macdsignal, macdhist = talib.MACD(...)`.
11. Make the code efficient and robust.

Example Output:
def custom_ai_eval(df):
    import pandas as pd
    if len(df) < 50:
        return {"passed": False, "reasons": ["Not enough data for 50 SMA"]}
    sma50 = df['Close'].rolling(50).mean().iloc[-1]
    curr_close = df['Close'].iloc[-1]
    if curr_close > sma50:
        return {"passed": True, "reasons": []}
    return {"passed": False, "reasons": ["Close is below 50 SMA"]}
"""

FILTER_SYSTEM_PROMPT = """
You are an expert Quantitative Developer. Your job is to translate a user's natural language trading filter into a valid Python function.

REQUIREMENTS:
1. You MUST output EXACTLY ONE Python function named `custom_ai_filter(df: pd.DataFrame, entry_price: float, target: float, stop_loss: float, atr: float) -> dict`.
2. Do NOT output any markdown blocks like ```python. Just output the raw python code.
3. The function MUST return a dictionary: `{"passed": bool, "reasons": []}`.
4. You may use `import pandas as pd` or `import numpy as np` if needed.

Example Output:
def custom_ai_filter(df, entry_price, target, stop_loss, atr):
    risk = entry_price - stop_loss
    reward = target - entry_price
    if risk <= 0: return {"passed": False, "reasons": ["Invalid risk"]}
    if (reward / risk) >= 3.0:
        return {"passed": True, "reasons": []}
    return {"passed": False, "reasons": ["RR is less than 3"]}
"""

def generate_pandas_logic(prompt: str, api_key: str = None) -> str:
    """
    Calls Gemini API to generate the custom python code, or falls back to local Ollama.
    """
    try:
        user_prompt = f"Write the Pandas logic for the following trading strategy:\n{prompt}"
        code = ""
        
        if api_key:
            logger.info("Routing to Google Gemini API...")
            genai.configure(api_key=api_key)
            # Use gemini-1.5-flash for fast reasoning
            model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=SYSTEM_PROMPT)
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0,
                )
            )
            code = response.text
        else:
            logger.info("Routing to local Ollama (qwen2.5-coder)...")
            # Fallback to Local Ollama
            ollama_url = "http://localhost:11434/api/generate"
            payload = {
                "model": "qwen2.5vl:7b",
                "system": SYSTEM_PROMPT,
                "prompt": user_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0
                }
            }
            try:
                res = requests.post(ollama_url, json=payload, timeout=120)
                res.raise_for_status()
                code = res.json().get("response", "")
            except requests.exceptions.RequestException as e:
                raise ValueError(f"Ollama connection failed. Is Ollama running on port 11434? Error: {e}")
        
        # Clean up markdown if the LLM hallucinated it despite instructions
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()
            
        return code.strip()
    except Exception as e:
        logger.error(f"Error generating AI logic: {e}")
        raise e

def generate_filter_logic(prompt: str, api_key: str = None) -> str:
    """
    Calls Gemini API to generate the custom filter code, or falls back to local Ollama.
    """
    try:
        user_prompt = f"Write the Python logic for the following trading filter:\n{prompt}"
        code = ""
        
        if api_key:
            logger.info("Routing filter generation to Google Gemini API...")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=FILTER_SYSTEM_PROMPT)
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(temperature=0.0)
            )
            code = response.text
        else:
            logger.info("Routing filter generation to local Ollama (qwen2.5-coder)...")
            ollama_url = "http://localhost:11434/api/generate"
            payload = {
                "model": "qwen2.5vl:7b",
                "system": FILTER_SYSTEM_PROMPT,
                "prompt": user_prompt,
                "stream": False,
                "options": {"temperature": 0.0}
            }
            try:
                res = requests.post(ollama_url, json=payload, timeout=120)
                res.raise_for_status()
                code = res.json().get("response", "")
            except requests.exceptions.RequestException as e:
                raise ValueError(f"Ollama connection failed. Error: {e}")
        
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()
            
        return code.strip()
    except Exception as e:
        logger.error(f"Error generating AI filter logic: {e}")
        raise e
