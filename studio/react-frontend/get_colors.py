import json
from PIL import Image

img_path = r'C:\Users\Eduardo\.gemini\antigravity\brain\097ab371-8200-48dd-a4c0-20c1a5350ffe\media__1780915587182.png'
img = Image.open(img_path)

# Sample background colors
left_color = img.getpixel((100, 100))
right_color = img.getpixel((img.width - 100, 100))

# Convert to hex
def to_hex(rgba):
    return '#{:02x}{:02x}{:02x}'.format(rgba[0], rgba[1], rgba[2])

data = {
    'width': img.width,
    'height': img.height,
    'left_bg': to_hex(left_color),
    'right_bg': to_hex(right_color)
}

with open('image_info.json', 'w') as f:
    json.dump(data, f)
print("Done")
