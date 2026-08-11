import google.generativeai as genai
import logging
import re

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
9. Make the code efficient and robust.

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

def generate_pandas_logic(prompt: str, api_key: str) -> str:
    """
    Calls Gemini API to generate the custom python code.
    """
    try:
        genai.configure(api_key=api_key)
        
        # Use gemini-1.5-flash or gemini-2.5-flash for fast reasoning
        model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=SYSTEM_PROMPT)
        
        response = model.generate_content(
            f"Write the Pandas logic for the following trading strategy:\n{prompt}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
            )
        )
        
        code = response.text
        
        # Clean up markdown if the LLM hallucinated it despite instructions
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()
            
        return code.strip()
    except Exception as e:
        logger.error(f"Error generating AI logic: {e}")
        raise e
