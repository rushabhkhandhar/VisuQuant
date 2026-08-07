import jinja2
from xhtml2pdf import pisa
import os

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src/templates")
env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
template = env.get_template("report.html")

dummy_state = {
    "decision": {"recommendation": "BUY", "confidence": "0.9"},
    "confluence": {"reasoning": []},
    "risk": {"metrics": {}},
    "vision": {"trend": {}, "market_structure": {}},
    "validation": {"valid": True, "summary": {}},
    "tech": {"interpretations": {}}
}

html = template.render(ticker="TEST", date="2026-07-25", **dummy_state)
with open("test2.pdf", "wb") as f:
    pisa.CreatePDF(html, dest=f)
print("Done")
