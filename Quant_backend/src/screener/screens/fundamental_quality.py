from src.data.screener_in_client import get_screener_data_sync
import logging

logger = logging.getLogger(__name__)

def evaluate_fundamentals(symbol: str) -> dict:
    """
    Evaluates fundamental quality using Screener.in data.
    
    Checks:
    1. ROE > 10%
    2. Latest Quarterly Operating Profit YoY Growth > 0 (Earnings Growth)
    3. Institutional Buying (FIIs/DIIs holding didn't decrease in latest quarter)
    """
    data = get_screener_data_sync(symbol)
    
    result = {
        "passed": False,
        "roe": None,
        "op_growth": None,
        "inst_buying": None,
        "reasons": []
    }
    
    if not data or not data.get("ratios"):
        result["reasons"].append("Failed to fetch fundamental data.")
        return result

    # 1. Profitability (ROE)
    ratios = data["ratios"]
    roe_str = ratios.get("ROE", "0")
    try:
        roe = float(roe_str.split("/")[0].strip().replace('%', ''))
        result["roe"] = roe
    except Exception:
        roe = 0

    if roe < 10.0:
        result["reasons"].append(f"ROE ({roe}%) is below 10%.")

    # 2. Earnings Growth (Quarterly OP)
    quarters = data.get("quarters", [])
    op_growth = False
    try:
        if len(quarters) >= 4:
            # Row 3 is typically Operating Profit
            op_row = next((r for r in quarters if "Operating Profit" in r[0]), None)
            if op_row and len(op_row) > 5:
                latest_op_str = op_row[-1].replace(",", "")
                prev_year_op_str = op_row[-5].replace(",", "") # roughly 4 quarters ago
                
                latest_op = float(latest_op_str)
                prev_year_op = float(prev_year_op_str)
                
                if latest_op > prev_year_op:
                    op_growth = True
                result["op_growth"] = f"{prev_year_op} -> {latest_op}"
    except Exception as e:
        logger.warning(f"Failed to parse OP growth for {symbol}: {e}")

    if not op_growth:
        result["reasons"].append(f"No YoY Operating Profit growth ({result['op_growth']}).")
        
    # 3. Institutional Buying (FIIs/DIIs)
    investors = data.get("investors", [])
    inst_buying = False
    try:
        if len(investors) >= 4:
            fii_row = next((r for r in investors if "FIIs" in r[0]), None)
            dii_row = next((r for r in investors if "DIIs" in r[0]), None)
            
            latest_fii = float(fii_row[-1].replace("%", "")) if fii_row else 0
            prev_fii = float(fii_row[-2].replace("%", "")) if fii_row else 0
            
            latest_dii = float(dii_row[-1].replace("%", "")) if dii_row else 0
            prev_dii = float(dii_row[-2].replace("%", "")) if dii_row else 0
            
            if (latest_fii >= prev_fii) or (latest_dii >= prev_dii):
                inst_buying = True
            
            result["inst_buying"] = f"FII: {prev_fii}%->{latest_fii}%, DII: {prev_dii}%->{latest_dii}%"
    except Exception as e:
        logger.warning(f"Failed to parse Inst Buying for {symbol}: {e}")

    if not inst_buying:
         result["reasons"].append("FII and DII holdings both decreased in the latest quarter.")

    if roe >= 10.0 and op_growth and inst_buying:
        result["passed"] = True

    return result
