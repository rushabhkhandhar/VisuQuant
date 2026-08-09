from src.data.screener_in_client import get_screener_data_sync
import logging

logger = logging.getLogger(__name__)

def evaluate_fundamentals_short(symbol: str) -> dict:
    """
    Evaluates fundamental weakness using Screener.in data (for Short Pipeline).
    
    Checks:
    1. ROE < 10% (Poor Profitability)
    2. Latest Quarterly Operating Profit YoY Growth <= 0 (Earnings Decay)
    3. Institutional Selling (FIIs or DIIs holding decreased in latest quarter)
    """
    data = get_screener_data_sync(symbol)
    
    result = {
        "passed": False,
        "roe": None,
        "op_growth": None,
        "inst_selling": None,
        "reasons": []
    }
    
    if not data or not data.get("ratios"):
        result["reasons"].append("Failed to fetch fundamental data.")
        return result

    # 1. Profitability (ROE) - Look for Weakness
    ratios = data["ratios"]
    roe_str = ratios.get("ROE", "0")
    try:
        roe = float(roe_str.split("/")[0].strip().replace('%', ''))
        result["roe"] = roe
    except Exception:
        roe = 100 # Default to high to fail short condition

    # For shorts, we want poor ROE.
    is_poor_roe = roe < 10.0
    if not is_poor_roe:
        result["reasons"].append(f"ROE ({roe}%) is too strong for shorting.")

    # 2. Earnings Decay (Quarterly OP)
    quarters = data.get("quarters", [])
    op_decay = False
    try:
        if len(quarters) >= 4:
            op_row = next((r for r in quarters if "Operating Profit" in r[0]), None)
            if op_row and len(op_row) > 5:
                latest_op_str = op_row[-1].replace(",", "")
                prev_year_op_str = op_row[-5].replace(",", "")
                
                latest_op = float(latest_op_str)
                prev_year_op = float(prev_year_op_str)
                
                if latest_op <= prev_year_op:
                    op_decay = True
                result["op_growth"] = f"{prev_year_op} -> {latest_op}"
    except Exception as e:
        logger.warning(f"Failed to parse OP growth for {symbol}: {e}")

    if not op_decay:
        result["reasons"].append(f"Operating Profit is still growing ({result['op_growth']}).")
        
    # 3. Institutional Selling (FIIs/DIIs)
    investors = data.get("investors", [])
    inst_selling = False
    try:
        if len(investors) >= 4:
            fii_row = next((r for r in investors if "FIIs" in r[0]), None)
            dii_row = next((r for r in investors if "DIIs" in r[0]), None)
            
            latest_fii = float(fii_row[-1].replace("%", "")) if fii_row else 0
            prev_fii = float(fii_row[-2].replace("%", "")) if fii_row else 0
            
            latest_dii = float(dii_row[-1].replace("%", "")) if dii_row else 0
            prev_dii = float(dii_row[-2].replace("%", "")) if dii_row else 0
            
            # If either FII or DII dumped shares, it's institutional selling
            if (latest_fii < prev_fii) or (latest_dii < prev_dii):
                inst_selling = True
            
            result["inst_selling"] = f"FII: {prev_fii}%->{latest_fii}%, DII: {prev_dii}%->{latest_dii}%"
    except Exception as e:
        logger.warning(f"Failed to parse Inst Buying for {symbol}: {e}")

    if not inst_selling:
         result["reasons"].append("No institutional distribution detected.")

    if is_poor_roe and op_decay and inst_selling:
        result["passed"] = True

    return result
