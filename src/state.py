from typing import TypedDict, Optional

class TradingState(TypedDict):
    """
    Represents the state of the trading pipeline at any point in the graph.
    """
    ticker: str
    chart_image_path: Optional[str]
    scraped_data: Optional[dict]
    vision_analysis: Optional[str]
    vision_features: Optional[dict]
    validation_result: Optional[str]
    final_decision: Optional[str]
