import json
import jinja2

template = jinja2.Template("""
{% set interpretations = tech.get('interpretations', {}) if tech else {} %}
{% if interpretations %}
    {% for k, v in interpretations.items() %}
    {{ k }} = {{ v }}
    {% endfor %}
{% else %}
    EMPTY
{% endif %}
""")

with open("tp/technical_indicators.json", "r") as f:
    tech = json.load(f)

print(template.render(tech=tech))
