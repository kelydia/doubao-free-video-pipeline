# -*- coding: utf-8 -*-
"""多区域去水印（LaMa）：支持一次处理多个 512x512 块，覆盖水印漂移。

用法:
    python dewm_multi.py <输入.mp4> <输出.mp4> [--zip x1,y1,x2,y2 [--zip ...]] [--dilate N] [--limit N]

默认区域（720x1280 原片坐标）：
    A 右下 (320,760,720,1280)  -> 块原点 (208,768)
    B 左上 (0,0,232,115)       -> 块原点 (0,0)

实测豆包 Seedance 水印位置：
  - 主位置：右下角 y≈1160–1260、x≈490–700（整片常驻）
  - 漂移位置：左上角 y≈25–90、x≈40–220（结尾几帧闪入）
"""
import argparse
import os
import subprocess
import sys
import time

import cv2
import numpy as np
import torch

MODEL = "D:/lama_models/big-lama.pt"
FFMPEG = "D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"
FFPROBE = "D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe"

# (块原点 x, 块原点 y, mask 矩形 x1,y1,x2,y2) —— 全部为原片坐标
REGIONS = [
    (208, 768, (470, 1150, 720, 1280)),   # 右下
    (0, 0, (0, 10, 240, 105)),            # 左上
]


def probe(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "default=nw=1", path],
        capture_output=True, text=True).stdout
    d = dict(l.split("=") for l in out.strip().splitlines() if "=" in l)
    num, den = d["r_frame_rate"].split("/")
    return int(d["width"]), int(d["height"]), float(num) / float(den)


def build_mask(bx, by, rect, dilate):
    x1, y1, x2, y2 = rect
    m = np.zeros((512, 512), np.uint8)
    m[max(0, y1 - by):min(512, y2 - by), max(0, x1 - bx):min(512, x2 - bx)] = 255
    if dilate > 0:
        m = cv2.dilate(m, np.ones((dilate, dilate), np.uint8))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--zip", action="append", default=None,
                    help="追加/覆盖区域，格式 bx,by,x1,y1,x2,y2（块原点 + mask 矩形）")
    ap.add_argument("--dilate", type=int, default=11)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    regions = REGIONS
    if a.zip:
        regions = [tuple(int(v) for v in z.split(",")) for z in a.zip]

    masks, alphas = [], []
    for bx, by, rect in regions:
        m = build_mask(bx, by, rect, a.dilate)
        masks.append(torch.from_numpy((m > 0).astype(np.float32))[None, None])
        alphas.append(cv2.GaussianBlur(m, (0, 0), 2.5).astype(np.float32)[..., None] / 255.0)

    W, H, fps = probe(a.src)
    for bx, by, _ in regions:
        if bx + 512 > W or by + 512 > H:
            print(f"画面 {W}x{H} 容纳不下块 ({(bx, by)})", file=sys.stderr)
            sys.exit(1)

    model = torch.jit.load(MODEL, map_location="cpu").eval()
    torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))

    dec = subprocess.Popen(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", a.src,
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    enc = subprocess.Popen(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-i", a.src, "-map", "0:v", "-map", "1:a?",
         "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart", a.dst],
        stdin=subprocess.PIPE)

    fb = W * H * 3
    t0, n = time.time(), 0

    while True:
        buf = dec.stdout.read(fb)
        if len(buf) < fb:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()

        for (bx, by, _), msk_t, alpha in zip(regions, masks, alphas):
            patch = frame[by:by + 512, bx:bx + 512]
            t_img = torch.from_numpy(np.ascontiguousarray(patch)).permute(2, 0, 1).float()[None] / 255.0
            with torch.no_grad():
                out = model(t_img, msk_t)
            outn = (torch.clamp(out[0], 0, 1).permute(1, 2, 0).numpy() * 255.0).astype(np.float32)
            frame[by:by + 512, bx:bx + 512] = (
                outn * alpha + patch.astype(np.float32) * (1 - alpha)).astype(np.uint8)

        enc.stdin.write(frame.tobytes())
        n += 1
        if n % 30 == 0:
            el = time.time() - t0
            print(f"  {n} frames  {el:.0f}s  ({el / n:.2f}s/frame)", flush=True)
        if a.limit and n >= a.limit:
            dec.stdout.close()
            dec.kill()
            break

    enc.stdin.close()
    enc.wait()
    dec.wait()
    print(f"[OK] {a.dst}  {n} frames  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
