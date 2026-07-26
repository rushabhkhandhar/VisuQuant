import json
import jinja2
import os
from xhtml2pdf import pisa

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src/templates")
env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
template = env.get_template("report.html")

def load_json(filename):
    with open(f"tp/{filename}", 'r') as f:
        return json.load(f)

# The structure in `final_state` is typically:
# state["decision"] = JSON loaded from LLM string (which has a "decision" key)
# state["confluence_analysis"] = JSON loaded from LLM string
final_state = {
    "ticker": "TEST",
    "decision": load_json("decision.json"),
    "confluence_analysis": load_json("confluence_analysis.json"),
    "risk_analysis": load_json("risk_analysis.json"),
    "technical_indicators": load_json("technical_indicators.json"),
    "vision_features": load_json("vision_features.json"),
    "trade_validation": load_json("trade_validation.json")
}

html_content = template.render(
    ticker="TEST",
    date="2026-07-26",
    decision=final_state["decision"],
    risk=final_state["risk_analysis"],
    confluence=final_state["confluence_analysis"],
    tech=final_state["technical_indicators"],
    vision=final_state["vision_features"],
    validation=final_state["trade_validation"]
)

with open("test_output.pdf", "wb") as f:
    pisa.CreatePDF(html_content, dest=f)

with open("test_output.html", "w") as f:
    f.write(html_content)
print("Render complete!")
