#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用 Big-LaMa (torch) 去除豆包视频右下角「豆包AI生成」水印。
不裁画面：只对右下角原生 512x512 块做 inpaint，再羽化贴回。

模型: D:/lama_models/big-lama.pt  (必须在纯 ASCII 路径，torch.jit.load 不支持非 ASCII)

用法:
    python dewm_torch.py <输入.mp4> <输出.mp4> [--mask x1,y1,x2,y2] [--dilate N] [--limit N]
"""
import argparse
import os
import subprocess
import sys
import time

import cv2
import numpy as np
import torch
from PIL import Image

MODEL = "D:/lama_models/big-lama.pt"
FFMPEG = "D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"
FFPROBE = "D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe"

# 右下角原生 512x512 块（720 宽 -> x 从 208 起；1280 高 -> y 从 768 起）
BOX = (208, 768)
# 水印在原片坐标下的范围（每镜略有上下浮动，取并集）
DEFAULT_MASK = (495, 1188, 700, 1250)


def probe(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "default=nw=1", path],
        capture_output=True, text=True).stdout
    d = dict(l.split("=") for l in out.strip().splitlines() if "=" in l)
    num, den = d["r_frame_rate"].split("/")
    return int(d["width"]), int(d["height"]), float(num) / float(den)


def build_mask(mask_xyxy, dilate):
    bx, by = BOX
    x1, y1, x2, y2 = mask_xyxy
    m = np.zeros((512, 512), np.uint8)
    m[max(0, y1 - by):min(512, y2 - by), max(0, x1 - bx):min(512, x2 - bx)] = 255
    if dilate > 0:
        m = cv2.dilate(m, np.ones((dilate, dilate), np.uint8))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--mask", default=",".join(str(v) for v in DEFAULT_MASK))
    ap.add_argument("--dilate", type=int, default=7)
    ap.add_argument("--limit", type=int, default=0, help="仅处理前 N 帧（调试）")
    a = ap.parse_args()

    mask = build_mask(tuple(int(v) for v in a.mask.split(",")), a.dilate)
    # 羽化 alpha（贴回时用）
    alpha = cv2.GaussianBlur(mask, (0, 0), 2.5).astype(np.float32)[..., None] / 255.0

    W, H, fps = probe(a.src)
    bx, by = BOX
    if bx + 512 > W or by + 512 > H:
        print(f"画面 {W}x{H} 不足以容纳 512x512 块", file=sys.stderr)
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

    msk_t = torch.from_numpy((mask > 0).astype(np.float32))[None, None]
    fb = W * H * 3
    t0, n = time.time(), 0

    while True:
        buf = dec.stdout.read(fb)
        if len(buf) < fb:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
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
