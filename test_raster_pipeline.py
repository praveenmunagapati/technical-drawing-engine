from PIL import Image, ImageDraw
from vectordraft.importers import load_document

# Create a test image
img = Image.new('RGB', (200, 200), color = 'white')
d = ImageDraw.Draw(img)
d.ellipse((50, 50, 150, 150), fill=(255, 0, 0), outline=(0, 0, 0))
d.text((70, 90), "VectorDraft", fill=(0, 0, 255))
img.save('test_raster.png')

# Load the raster using our new pipeline
doc = load_document('test_raster.png')
print(f"Raster vectorization successful! Paths extracted: {len(doc.paths)}")

# Check bounds
print(f"Bounds: {doc.bounds}")
