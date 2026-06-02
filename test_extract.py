import ezdxf
from ezdxf.addons import text2path
from ezdxf import path as ezpath

doc = ezdxf.readfile(r"myowntest\Circuit diagram_OXB_T.dxf")
msp = doc.modelspace()

def extract(entities):
    paths_count = 0
    for e in entities:
        if e.dxftype() == 'INSERT':
            paths_count += extract(e.virtual_entities())
        elif e.dxftype() in {'TEXT', 'MTEXT'}:
            try:
                # make_paths_from_entity returns a list of ezdxf.path.Path objects
                paths = text2path.make_paths_from_entity(e)
                paths_count += len(paths)
            except Exception as ex:
                pass
        elif e.dxftype() in {'LINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'LWPOLYLINE', 'POLYLINE', 'SPLINE', 'HATCH'}:
            try:
                p = ezpath.make_path(e)
                # make_path can return a Single Path or a MultiPath
                if hasattr(p, 'paths'):
                    paths_count += len(p.paths)
                else:
                    paths_count += 1
            except Exception as ex:
                pass
    return paths_count

print("Total extracted paths:", extract(msp))
