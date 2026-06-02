import gerbonara
from gerbonara.rs274x import GerberFile

gerber_content = """
%FSLAX24Y24*%
%MOMM*%
%ADD10C,1.0*%
D10*
X0Y0D02*
X10000Y10000D01*
M02*
"""

with open("test.gbr", "w") as f:
    f.write(gerber_content)

try:
    g = GerberFile.open("test.gbr")
    print(g.to_svg())
except Exception as e:
    print("Error:", e)
