from PIL import Image
import sys, os, glob

def sheet(files, out, cols=4, cell=360, labels=None):
    rows = (len(files) + cols - 1) // cols
    sh = Image.new("RGB", (cols * cell, rows * (cell + 24)), "white")
    from PIL import ImageDraw, ImageFont
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
    except Exception:
        f = ImageFont.load_default()
    d = ImageDraw.Draw(sh)
    for i, p in enumerate(files):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell - 8, cell - 8))
        x, y = (i % cols) * cell, (i // cols) * (cell + 24)
        sh.paste(im, (x + 4, y + 4))
        lab = labels[i] if labels else os.path.basename(p)
        d.text((x + 5, y + cell), lab, fill="black", font=f)
    sh.save(out, quality=88)
    return out, sh.size

if __name__ == "__main__":
    out = sys.argv[1]
    files = sys.argv[2:]
    print(sheet(files, out))
