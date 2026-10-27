#!/usr/bin/env python3
"""Generate scripts/world_map.png from the Natural Earth land polygons (public domain).

Miller projection with the constants of scripts/rotor_control.py (MAP_*), so that
the map and the GUI overlays line up exactly. Land in black, sea in white.

Data: ne_50m_land.geojson — https://www.naturalearthdata.com/downloads/50m-physical-vectors/
(« Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com »)

Usage: python3 tools/gen_world_map.py ne_50m_land.geojson scripts/world_map.png
"""
import json, math, sys
from PIL import Image, ImageDraw

# Same values as scripts/rotor_control.py
MAP_W, MAP_H = 720, 348
MAP_X0, MAP_KX = 349.88, 1.9300
MAP_Y0, MAP_KY = 219.11, 1.9063
SUR = 4   # supersampling, for clean coastlines after downscaling


def ll_to_xy(lon, lat):
    lat = max(-89.9, min(89.9, lat))
    ym = math.degrees(1.25 * math.log(math.tan(math.pi/4 + 0.4 * math.radians(lat))))
    return (MAP_X0 + MAP_KX * lon) * SUR, (MAP_Y0 - MAP_KY * ym) * SUR


def main(src, dst):
    img = Image.new("L", (MAP_W * SUR, MAP_H * SUR), 255)
    draw = ImageDraw.Draw(img)
    for feat in json.load(open(src, encoding="utf-8"))["features"]:
        geom = feat["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            # The map spans ≈ 373° of longitude: each land mass is also drawn at ±360°
            for dlon in (-360, 0, 360):
                for i, ring in enumerate(poly):          # 0 = outer ring, following ones = holes
                    pts = [ll_to_xy(lon + dlon, lat) for lon, lat in ring]
                    if len(pts) >= 3:
                        draw.polygon(pts, fill=0 if i == 0 else 255)
    img = img.resize((MAP_W, MAP_H), Image.LANCZOS).point(lambda v: 0 if v < 128 else 255)
    img.convert("1").save(dst, optimize=True)
    print(f"{dst} : {MAP_W} × {MAP_H} px")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
