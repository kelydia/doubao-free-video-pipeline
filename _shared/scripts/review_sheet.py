# -*- coding: utf-8 -*-
"""审片图标准工具（省 token 版）。

为什么要它：看图成本 ≈ 像素面积 / 750。直接读豆包原始帧（720x1280 PNG，约 1.2k tokens/张）
或一次性读 5 张，就是 6k+ tokens；同样的信息拼成一张低分辨率 sheet 只要 300-700 tokens。

用法：
    python review_sheet.py strip <video|img...> --n 5 --out x.jpg
    python review_sheet.py pair  <上一镜视频.mp4> <下一镜首帧.jpg> --out join.jpg
    python review_sheet.py one   <img> --h 900 --out detail.jpg

约定（见 _shared/工作流_SOP.md §4.5）：
    - 动作/机位/衔接 判定 → strip，单帧高默认 330px
    - 商品细节/文字 核对 → one，单帧高 900px，一次只看 1 张
    - 禁止逐帧直读 720x1280 或 1080x1920 原图
"""
import argparse
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FFMPEG = shutil.which("ffmpeg") or "D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"
FFPROBE = shutil.which("ffprobe") or "D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe"
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
LABEL_H = 22

_TMP_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "work")
_seen = set()


def _scratch():
    """沙箱内不能写系统 Temp，也不能让 tempfile 自建目录（权限被拦），固定缓存目录。"""
    os.makedirs(_TMP_ROOT, exist_ok=True)
    return _TMP_ROOT


def _font():
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        try:
            return ImageFont.truetype(p, 16)
        except Exception:
            pass
    return ImageFont.load_default()


def probe_duration(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def grab_frame(video, t):
    """用管道取帧，避免向磁盘写临时文件（沙箱下最稳）。"""
    p = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}",
         "-i", video, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, check=True)
    import io
    return Image.open(io.BytesIO(p.stdout)).convert("RGB")


def even_frames(video, n):
    """按时间均匀抽 n 帧（避开首末 3%，那里常是黑场/过渡）。"""
    dur = probe_duration(video)
    return [grab_frame(video, dur * (0.03 + 0.94 * (i / max(n - 1, 1))))
            for i in range(n)]


def last_frame(video):
    return grab_frame(video, max(probe_duration(video) - 0.15, 0))


def _fit(im, h):
    w = max(1, round(im.width * h / im.height))
    return im.resize((w, h), Image.LANCZOS)


def _place(cells, out, h, cols, labels, gap=6):
    rows = (len(cells) + cols - 1) // cols
    col_w = [0] * cols
    for i, c in enumerate(cells):
        col_w[i % cols] = max(col_w[i % cols], c.width)
    W = sum(col_w) + gap * (cols + 1)
    H = rows * (h + (LABEL_H if labels else 0)) + gap * (rows + 1)
    canvas = Image.new("RGB", (W, H), (20, 20, 24))
    d = ImageDraw.Draw(canvas)
    f = _font()
    for i, c in enumerate(cells):
        r, col = divmod(i, cols)
        x = gap + sum(col_w[:col]) + gap * col
        y = gap + r * (h + (LABEL_H if labels else 0) + gap)
        canvas.paste(c, (x, y))
        if labels:
            d.text((x + 2, y + h + 3), labels[i], fill=(235, 235, 235), font=f)
    canvas.save(out, quality=82, optimize=True)
    return canvas


def report(out, canvas):
    px = canvas.width * canvas.height
    w, h = min(canvas.width, 1568), min(canvas.height, 1568)
    tok = -(-w // 28) * -(-h // 28)
    kb = os.path.getsize(out) / 1024
    print(f"[sheet] {out}  {canvas.width}x{canvas.height}  {px/1e3:.0f}k px  "
          f"≈{tok} tokens  {kb:.0f}KB")


def _cells_for(paths, n, idx0=0):
    cells = []
    for i, p in enumerate(paths):
        if os.path.splitext(p)[1].lower() in VIDEO_EXT:
            cells.extend(even_frames(p, n or 5))
        else:
            cells.append(Image.open(p).convert("RGB"))
    return cells


def cmd_strip(a):
    cells = [_fit(c, a.h) for c in _cells_for(a.inputs, a.n)]
    if a.no_label:
        labels = None
    else:
        labels = [str(i + 1) for i in range(len(cells))]
    cols = a.cols or len(cells)
    canvas = _place(cells, a.out, a.h, cols, labels)
    report(a.out, canvas)


def cmd_one(a):
    im = Image.open(a.input).convert("RGB")
    im = _fit(im, a.h)
    im.save(a.out, quality=86, optimize=True)
    w, h = min(im.width, 1568), min(im.height, 1568)
    print(f"[one] {a.out}  {im.width}x{im.height}  ≈{-(-w//28)*-(-h//28)} tokens")


def cmd_pair(a):
    cells = [_fit(last_frame(a.video), a.h),
             _fit(Image.open(a.next_first).convert("RGB"), a.h)]
    canvas = _place(cells, a.out, a.h, 2, ["prev last", "next first"])
    report(a.out, canvas)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("strip", help="多帧横向/网格拼接")
    s.add_argument("inputs", nargs="+")
    s.add_argument("--out", required=True)
    s.add_argument("--h", type=int, default=330, help="单帧高，默认 330")
    s.add_argument("--n", type=int, default=5, help="每个视频抽几帧，默认 5")
    s.add_argument("--cols", type=int, default=0)
    s.add_argument("--no-label", action="store_true")
    s.set_defaults(func=cmd_strip)

    o = sub.add_parser("one", help="单帧细节（唯一允许的高分辨率读图）")
    o.add_argument("input")
    o.add_argument("--out", required=True)
    o.add_argument("--h", type=int, default=900)
    o.set_defaults(func=cmd_one)

    p = sub.add_parser("pair", help="上一镜末帧 + 下一镜首帧 两联图")
    p.add_argument("video")
    p.add_argument("next_first")
    p.add_argument("--out", default="join.jpg")
    p.add_argument("--h", type=int, default=620)
    p.set_defaults(func=cmd_pair)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
