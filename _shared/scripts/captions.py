import json, os, sys
from PIL import Image, ImageDraw, ImageFont

# 默认英文花字；--lang zh 生成中文版（保留旧能力）
LANG = "en"
for i, a in enumerate(sys.argv):
    if a == "--lang" and i + 1 < len(sys.argv):
        LANG = sys.argv[i + 1]

W, H = 1080, 1920

CAPTIONS_EN = {
    "S1": "Everyone needs this before Christmas",
    "S2": "Someone left this by the road",
    "S3": "It arrived · one bear, one bag",
    "S4": "3 styles · one bag each",
    "S5": "Gift-holding bear · insane detail",
    "S6": "All 3 in one set",
    "S7": "3-piece set · Christmas limited",
}

FONTS = {
    "en": ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ARIALN.TTF"],
    "zh": ["C:/Windows/Fonts/msyhbd.ttc"],
}

sb = json.load(open("01_plan/storyboard.json", encoding="utf-8"))
out_dir = "05_edit/cap" if LANG == "en" else "05_edit/cap_zh"
os.makedirs(out_dir, exist_ok=True)

for s in sb["shots"]:
    sid = s["shot_id"]
    if LANG == "en":
        txt = CAPTIONS_EN.get(sid, "").strip()
    else:
        txt = (s.get("caption") or "").strip()
    if not txt:
        continue
    fpath = next(p for p in FONTS[LANG] if os.path.exists(p))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 74 if LANG == "zh" else 80
    font = ImageFont.truetype(fpath, size)
    while d.textlength(txt, font=font) > W - 140 and size > 36:
        size -= 3
        font = ImageFont.truetype(fpath, size)
    tw = d.textlength(txt, font=font)
    asc, desc = font.getmetrics()
    th = asc + desc
    x = (W - tw) // 2
    y = 250
    pad = 28
    rad = max(8, int((th + 2 * pad) // 2))
    d.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=(0, 0, 0, 108))
    for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
        d.text((x + dx, y + dy), txt, font=font, fill=(0, 0, 0, 150))
    d.text((x, y), txt, font=font, fill=(255, 255, 255, 255))
    img.save(f"{out_dir}/{sid}.png")
    print(sid, size, txt, flush=True)
