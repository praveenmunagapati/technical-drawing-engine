import ezdxf
try:
    from ezdxf.addons import text2path
    print("text2path imported successfully")
except ImportError:
    print("text2path import failed")

import sys
print("ezdxf version:", ezdxf.__version__)
