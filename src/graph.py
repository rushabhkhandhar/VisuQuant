from langgraph.graph import StateGraph, START, END
from src.state import TradingState
from src.nodes import (
    node_capture_chart,
    node_run_nse_scraper,
    node_vision_analysis,
    node_validation_and_decision
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
    builder.add_node("validation_and_decision", node_validation_and_decision)
    
    # Define the execution flow
    # 1. START fans out to capture_chart AND run_scraper in parallel
    builder.add_edge(START, "capture_chart")
    builder.add_edge(START, "run_scraper")
    
    # 2. capture_chart feeds into vision_analysis
    builder.add_edge("capture_chart", "vision_analysis")
    
    # 3. Both vision_analysis and run_scraper fan-in to validation_and_decision
    builder.add_edge("vision_analysis", "validation_and_decision")
    builder.add_edge("run_scraper", "validation_and_decision")
    
    # 4. validation_and_decision feeds into END
    builder.add_edge("validation_and_decision", END)
    
    # Compile the graph
    return builder.compile()
