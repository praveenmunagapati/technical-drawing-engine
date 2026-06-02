import pytest
from pathlib import Path
from vectordraft.importers import load_document, load_raster, load_oda

def test_load_raster_extracts_paths(tmp_path):
    from PIL import Image, ImageDraw
    
    img_path = tmp_path / "test_raster.png"
    img = Image.new('RGB', (100, 100), color='white')
    d = ImageDraw.Draw(img)
    d.ellipse((10, 10, 90, 90), fill=(0, 0, 0))
    img.save(img_path)
    
    doc = load_raster(img_path)
    assert len(doc.paths) > 0, "Raster vectorizer should extract paths"
    assert doc.source_path == str(img_path)

def test_load_oda_missing_executable(tmp_path):
    # This should fail if ODA is not installed, or fail with a missing file error.
    # We just want to make sure it doesn't crash Python entirely.
    dwg_path = tmp_path / "test.dwg"
    dwg_path.write_text("dummy dwg")
    
    import shutil
    has_oda = shutil.which("ODAFileConverter") or shutil.which("ODAFileConverter.exe")
    
    if not has_oda:
        with pytest.raises(ValueError, match="ODA File Converter is not installed"):
            load_oda(dwg_path)
    else:
        # If installed, it will fail because 'dummy dwg' is invalid
        with pytest.raises(RuntimeError):
            load_oda(dwg_path)
