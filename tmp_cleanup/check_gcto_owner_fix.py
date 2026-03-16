from pathlib import Path
import sys
sys.path.insert(0, str(Path('src').resolve()))
from rag_worker.app import _extract_gcto_template_fields

text = """On Track
Sami H. Alzomaia Project Owner
Develop a Proposal For Implementing Circular Economy Principles Across All Subsidiaries, Starting With It Services Offered By Solutions"""
print(_extract_gcto_template_fields(text))