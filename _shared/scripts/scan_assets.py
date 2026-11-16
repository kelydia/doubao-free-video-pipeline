#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scan_assets.py — 全局素材库扫描/清单生成脚本（2026-11-16）

用法：
    python _shared/scripts/scan_assets.py                # 扫描全部项目，重建 素材库/清单.json + 各项目 md 段
    python _shared/scripts/scan_assets.py --project 2026-11-15_三只小熊橄榄球盲盒成片
                                                          # 只扫描/追加一个项目（项目收尾时用）
    python _shared/scripts/scan_assets.py --check         # 只校验清单与磁盘是否一致，不写文件

设计原则（用户 2026-11-16 决策）：
- **索引+清单，不移动原文件**：只记录路径、大小、来源项目、类型、用途，原文件原地保留。
- 收录范围（用户确认）：
    1) 最终成片      -> <proj>/06_deliver/*.mp4
    2) 通过验收视频段 -> <proj>/03_clips/*.mp4（03_clips_clean 优先视为"通过"版本）
    3) 关键帧        -> <proj>/02_keyframes/final/*.jpg
    4) 音效/音乐     -> <proj>/05_audio/**.{wav,mp3}（跳过 _mixbuild 之外的中间候选由 RULES 控制）
- 输出：
    _shared/素材库/清单.json   机器可读全量索引（权威）
    _shared/素材库/README.md    人读总览（每个项目一节，由脚本渲染）
- 本脚本是幂等的：重跑只会刷新清单，不产生重复行。

收尾调用约定（写进 SOP §11）：
    项目任务总结.md 完成后，**必须**执行
        python _shared/scripts/scan_assets.py --project <项目目录名>
    再在项目 任务总结.md 末尾的「素材库」小节引用 清单.json 中该项目条目。
"""
import argparse
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(ROOT, "_shared", "素材库")
MANIFEST = os.path.join(LIB_DIR, "清单.json")
README = os.path.join(LIB_DIR, "README.md")

AUDIO_EXT = {".wav", ".mp3"}
# 05_audio 下的中间/候选噪音目录：默认不逐个收录（数量巨大且未定稿）
AUDIO_SKIP_DIRS = {"cand", "fs4", "_tmp", "_alt", "_mixbuild", "audi", "audi2", "audi3", "final_aud"}
# 05_audio 下这些文件视为"定稿音效/混音成品"，优先收录
AUDIO_FINAL_HINT = ("mix_final", "bgm", "_final")


def is_project(name):
    # 形如 2026-11-15_主题 的目录，且不是 _shared/_archive 等
    if not name[:4].isdigit():
        return False
    if not os.path.isdir(os.path.join(ROOT, name)):
        return False
    # 至少有 01_plan 或 06_deliver 才算项目
    return os.path.isdir(os.path.join(ROOT, name, "01_plan")) or os.path.isdir(
        os.path.join(ROOT, name, "06_deliver")
    )


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def collect_files(base, exts, recursive=False):
    out = []
    if not os.path.isdir(base):
        return out
    if recursive:
        for dp, dns, fns in os.walk(base):
            # 跳过中间候选目录
            dns[:] = [d for d in dns if d not in AUDIO_SKIP_DIRS]
            for fn in fns:
                if os.path.splitext(fn)[1].lower() in exts:
                    fp = os.path.join(dp, fn)
                    out.append(fp)
    else:
        for fn in os.listdir(base):
            fp = os.path.join(base, fn)
            if os.path.isfile(fp) and os.path.splitext(fn)[1].lower() in exts:
                out.append(fp)
    return sorted(out)


def status_of(path):
    """粗略判断是否'通过验收'：有配套 _nocap 或不含 _vN 视为定稿；否则标 draft。"""
    fn = os.path.basename(path)
    stem = os.path.splitext(fn)[0]
    import re

    if re.search(r"_v\d+$", stem) or "_raw" in stem:
        return "draft"  # 有多版本痕迹，非最终
    return "final"


def scan_project(name):
    pdir = os.path.join(ROOT, name)
    entry = {"project": name, "assets": []}

    def add(kind, path, purpose):
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        entry["assets"].append(
            {
                "type": kind,
                "path": rel(path),
                "bytes": size,
                "status": status_of(path),
                "purpose": purpose,
            }
        )

    # 1) 最终成片
    for f in collect_files(os.path.join(pdir, "06_deliver"), {".mp4"}):
        add("deliver", f, "最终成片")
    # 2) 通过验收视频段：03_clips_clean 优先；已有 clean 时跳过 03_clips 里的多版本 draft
    clean = os.path.join(pdir, "03_clips_clean")
    have_clean = os.path.isdir(clean) and bool(collect_files(clean, {".mp4"}))
    if have_clean:
        for f in collect_files(clean, {".mp4"}):
            add("clip", f, "通过验收视频段（clean）")
    else:
        for f in collect_files(os.path.join(pdir, "03_clips"), {".mp4"}):
            add("clip", f, "视频段（03_clips，多版本可能含 draft）")
    # 3) 关键帧
    for f in collect_files(os.path.join(pdir, "02_keyframes", "final"), {".jpg", ".png"}):
        add("keyframe", f, "关键帧")
    # 4) 音效/音乐：05_audio 下非噪音目录的音频 + 顶层定稿混音
    audio_root = os.path.join(pdir, "05_audio")
    if os.path.isdir(audio_root):
        for f in collect_files(audio_root, AUDIO_EXT, recursive=False):
            add("audio", f, "混音/音乐成品")
        for f in collect_files(audio_root, AUDIO_EXT, recursive=True):
            # 递归跳过已在顶层收过的
            if os.path.dirname(f) == audio_root:
                continue
            add("sfx", f, "音效素材（子目录）")
    return entry


def all_projects():
    return sorted(n for n in os.listdir(ROOT) if is_project(n))


def build(only=None):
    if only:
        projs = [only] if is_project(only) else []
    else:
        projs = all_projects()
    manifest = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "索引+清单（不移动原文件）",
        "projects": [scan_project(p) for p in projs],
    }
    return manifest


def render_readme(manifest):
    lines = []
    lines.append("# 全局素材库 · 总览（索引 + 清单）")
    lines.append("")
    lines.append(
        "> **本文件由 `_shared/scripts/scan_assets.py` 自动生成，请勿手改**（重跑会被覆盖）。"
    )
    lines.append(
        "> 权威机器可读索引见同目录 [`清单.json`](清单.json)。素材文件**原地保留在各项目**，本库只做索引，复用直接按路径引用。"
    )
    lines.append(
        "> 收录范围：最终成片 `06_deliver/*.mp4`、通过验收视频段 `03_clips(_clean)/*.mp4`、关键帧 `02_keyframes/final/*`、音效/音乐 `05_audio/**`。"
    )
    lines.append("")
    total = sum(len(p["assets"]) for p in manifest["projects"])
    total_bytes = sum(a["bytes"] for p in manifest["projects"] for a in p["assets"])
    lines.append(
        f"**生成时间**：{manifest['generated_at']}　|　**项目数**：{len(manifest['projects'])}　|　**素材条目**：{total}　|　**合计大小**：{total_bytes/1024/1024:.1f} MB"
    )
    lines.append("")
    for p in manifest["projects"]:
        lines.append(f"## {p['project']}")
        lines.append("")
        if not p["assets"]:
            lines.append("_（无收录素材）_")
            lines.append("")
            continue
        # 按类型分组
        order = [
            ("deliver", "最终成片"),
            ("clip", "视频段"),
            ("keyframe", "关键帧"),
            ("audio", "混音/音乐"),
            ("sfx", "音效素材"),
        ]
        for typ, label in order:
            items = [a for a in p["assets"] if a["type"] == typ]
            if not items:
                continue
            lines.append(f"### {label}（{len(items)}）")
            lines.append("")
            lines.append("| 文件 | 大小 | 状态 | 用途 |")
            lines.append("| --- | --- | --- | --- |")
            for a in items:
                fn = a["path"].split("/")[-1]
                kb = a["bytes"] / 1024
                sz = f"{kb/1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB"
                lines.append(
                    f"| [`{fn}`](../../{a['path']}) | {sz} | {a['status']} | {a['purpose']} |"
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def cmd_check(manifest):
    bad = 0
    for p in manifest["projects"]:
        for a in p["assets"]:
            fp = os.path.join(ROOT, a["path"].replace("/", os.sep))
            if not os.path.isfile(fp):
                print(f"[MISSING] {a['path']}")
                bad += 1
    if bad == 0:
        print("ALL ASSET PATHS OK")
    else:
        print(f"{bad} missing asset path(s)")
    return 0 if bad == 0 else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="只扫描单个项目目录名")
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()

    if not os.path.isdir(LIB_DIR):
        os.makedirs(LIB_DIR, exist_ok=True)

    if args.check:
        if not os.path.isfile(MANIFEST):
            print("清单.json 不存在，先跑一次不带 --check 的扫描")
            return 1
        with open(MANIFEST, "r", encoding="utf-8") as fh:
            return cmd_check(json.load(fh))

    # 增量：--project 时只替换该项目条目，保留其它项目
    if args.project:
        if not is_project(args.project):
            print(f"不是有效项目目录：{args.project}")
            return 1
        if os.path.isfile(MANIFEST):
            with open(MANIFEST, "r", encoding="utf-8") as fh:
                old = json.load(fh)
        else:
            old = {"projects": []}
        newp = scan_project(args.project)
        projs = [p for p in old.get("projects", []) if p["project"] != args.project]
        projs.append(newp)
        projs.sort(key=lambda x: x["project"])
        manifest = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "索引+清单（不移动原文件）",
            "projects": projs,
        }
    else:
        manifest = build()

    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    with open(README, "w", encoding="utf-8") as fh:
        fh.write(render_readme(manifest))

    total = sum(len(p["assets"]) for p in manifest["projects"])
    print(f"WROTE {rel(MANIFEST)}  ({len(manifest['projects'])} projects, {total} assets)")
    print(f"WROTE {rel(README)}")
    return cmd_check(manifest)


if __name__ == "__main__":
    sys.exit(main())
