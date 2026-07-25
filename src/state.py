from typing import TypedDict, Optional, Any

class TradingState(TypedDict):
    """
    Represents the state of the trading pipeline at any point in the graph.
    """
    ticker: str
    chart_image_path: Optional[str]
    scraped_data: Optional[dict]
    vision_analysis: Optional[str]
    vision_features: Optional[dict]
    technical_indicators: Optional[dict]
    confluence_analysis: Optional[dict]
    validation_result: Any
    final_decision: Optional[str]
