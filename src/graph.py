from langgraph.graph import StateGraph, START, END
from src.state import TradingState
from src.nodes import (
    node_capture_chart,
    node_run_nse_scraper,
    node_vision_analysis,
    node_quantitative_analysis,
    node_trend_engine,
    node_confluence_engine,
    node_risk_management,
    node_decision_engine,
    node_trade_validator,
    node_report_generator
)

def build_graph() -> StateGraph:
    """
    Constructs and returns the LangGraph workflow.
    """
    # Initialize the graph with the typed state
    builder = StateGraph(TradingState)
    
    # Add nodes
    builder.add_node("capture_chart", node_capture_chart)
    builder.add_node("run_scraper", node_run_nse_scraper)
    builder.add_node("vision_analysis", node_vision_analysis)
    builder.add_node("quantitative_analysis", node_quantitative_analysis)
    builder.add_node("trend_engine", node_trend_engine)
    builder.add_node("confluence_engine", node_confluence_engine)
    builder.add_node("risk_management", node_risk_management)
    builder.add_node("decision_engine", node_decision_engine)
    builder.add_node("trade_validator", node_trade_validator)
    builder.add_node("report_generator", node_report_generator)
    
    # Define the execution flow
    # 1. START fans out to capture_chart AND run_scraper in parallel
    builder.add_edge(START, "capture_chart")
    builder.add_edge(START, "run_scraper")
    
    # 2. capture_chart feeds into vision_analysis
    builder.add_edge("capture_chart", "vision_analysis")
    
    # 3. run_scraper feeds into quantitative_analysis
    builder.add_edge("run_scraper", "quantitative_analysis")
    
    # 4. Both vision_analysis and quantitative_analysis fan-in to trend_engine
    builder.add_edge("vision_analysis", "trend_engine")
    builder.add_edge("quantitative_analysis", "trend_engine")
    
    # 5. trend_engine feeds into confluence_engine
    builder.add_edge("trend_engine", "confluence_engine")
    
    # 6. confluence_engine feeds into risk_management
    builder.add_edge("confluence_engine", "risk_management")

    # 7. risk_management feeds into decision_engine
    builder.add_edge("risk_management", "decision_engine")
    
    # 8. decision_engine feeds into trade_validator
    builder.add_edge("decision_engine", "trade_validator")
    
    # 9. trade_validator feeds into report_generator
    builder.add_edge("trade_validator", "report_generator")

    # 10. report_generator feeds into END
    builder.add_edge("report_generator", END)
    
    # Compile the graph
    return builder.compile()
