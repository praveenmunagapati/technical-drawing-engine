import ezdxf

doc = ezdxf.readfile(r"myowntest\Circuit diagram_OXB_T.dxf")
msp = doc.modelspace()
counts = {}
for e in msp:
    counts[e.dxftype()] = counts.get(e.dxftype(), 0) + 1

print("Modelspace entities:")
for k, v in counts.items():
    print(f"  {k}: {v}")

blocks = doc.blocks
print(f"Total blocks: {len(blocks)}")
