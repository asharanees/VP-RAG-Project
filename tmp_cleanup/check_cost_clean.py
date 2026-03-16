from pathlib import Path
import sys
sys.path.insert(0, str(Path('src').resolve()))
import common.structured_analyst as sa

raw = """Sector Weekly Report
IT Efficiency Initiatives - Cost Optimization
0
mSAR
0
mSAR
0
mSAR
Sector Weekly Report"""
print(sa._clean_section_text('cost_optimization', raw))