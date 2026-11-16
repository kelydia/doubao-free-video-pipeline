# -*- coding: utf-8 -*-
"""锚点先行（C 模式）辅助工具。

用法：
    python anchor_gate.py join   <上一镜视频.mp4> <下一镜首帧.jpg> [--out 输出.png]
    python anchor_gate.py drift  <上一镜视频.mp4> <上一镜尾帧.jpg>

子命令：
    join   抽上一镜视频的**末帧**，与下一镜首帧并排拼成两联对比图，供人工判断能否接上。
    drift  抽末帧与上一镜尾帧对比，打印像素差指标，判断"偏离小/大"。

判定口径（2026-11-11 用户确认，见 _shared/工作流_SOP.md §4.3）：
    **以 join 两联图为准**——看左（上一镜末帧）与右（下一镜首帧）在叙事与空间上
    能不能接上：卡车朝同一方向、被抛物件已脱离、镜头高度可接受、主光方向一致。

    drift 的 mean_abs **只作参考，不是硬指标**。动作推进型末帧（卡车驶远、箱子已飞离）
    与静态关键帧的像素差天然很大（S1 实测 74.46 仍放行）；drift 主要用来抓
    "主体完全跑偏 / 物件消失或多出 / 方向反转"这类真问题。
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

FFMPEG = "D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"
FFPROBE = "D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe"
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_gate_tmp.png")


def last_frame(video, out=TMP):
    """从视频末尾 0.15s 处抽一帧。"""
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-sseof", "-0.15", "-i", video, "-frames:v", "1", out], check=True)
    return Image.open(out).convert("RGB")


def _resize(im, size=(540, 960)):
    return im.resize(size, Image.LANCZOS)


def join(video, next_first, out):
    a = _resize(last_frame(video))
    b = _resize(Image.open(next_first).convert("RGB"))
    W, H = 540 * 2 + 20, 960
    canvas = Image.new("RGB", (W, H), (24, 24, 28))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (560, 0))
    canvas.save(out)
    print(f"[join] {out}  (左=上一镜视频末帧, 右=下一镜首帧)")


def drift(video, last_keyframe):
    """像素差只作参考：动作推进型末帧天然差异大，真判定靠 join 两联图。"""
    a = last_frame(video)
    b = Image.open(last_keyframe).convert("RGB").resize(a.size, Image.LANCZOS)
    d = np.abs(np.asarray(a, np.float32) - np.asarray(b, np.float32))
    mean_abs = float(d.mean())
    print(f"[drift] mean_abs={mean_abs:.2f}  (仅参考，请看 join 两联图判断能否接上)")
    return mean_abs


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "join" and len(sys.argv) >= 4:
        out = "anchor_join.png"
        if "--out" in sys.argv:
            out = sys.argv[sys.argv.index("--out") + 1]
        join(sys.argv[2], sys.argv[3], out)
    elif cmd == "drift" and len(sys.argv) >= 4:
        drift(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
