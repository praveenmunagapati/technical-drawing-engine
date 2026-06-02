import requests
from pathlib import Path

# Create a dummy gerber file
gerber_content = """%FSLAX24Y24*%
%MOMM*%
%ADD10C,1.0*%
D10*
X0Y0D02*
X10000Y10000D01*
M02*
"""

with open("test.gbr", "w") as f:
    f.write(gerber_content)

import sys
from vectordraft.importers import load_document
try:
    doc = load_document("test.gbr")
    print(len(doc.paths))
except Exception as e:
    import traceback
    traceback.print_exc()
