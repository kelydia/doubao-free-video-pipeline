#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目复盘机械检查 / 复用资产台账自动维护（跨任务唯一入口）。

默认只读：扫描工作区所有任务目录，输出「复盘状态 / 已独立资产 / 散落候选」三张表。
--apply ：把三张表幂等写入 _shared/复用资产登记.md 的 AUTO 区块（只重写标记之间，
          标记之上的人工说明一律不动；不删除、不移动、不修改任何项目文件）。
--json  ：机器可读输出，供任务收尾 agent 使用。

「自动复盘」的分工（见 _shared/专题手册/07_项目复盘与经验沉淀规范.md）：
  脚本 = 机械部分（哪些项目在台账里没记录、哪些资产没独立、自动生成台账区块）
  agent = 语义部分（判断哪些经验可复用、合并进 SOP / 手册 / 模板、写台账人工区）

用法：python _shared/scripts/project_retro.py [--apply] [--json]
"""
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "_shared"
LEDGER = SHARED / "复用资产登记.md"
AUTO_S = "<!-- AUTO:START -->"
AUTO_E = "<!-- AUTO:END -->"

RETRO_MARKERS = ("复盘", "经验", "教训", "工作流优化", "可复用")
ASSET_EXT = (".md", ".py", ".mjs", ".sh", ".json")
SCRIPT_EXT = (".py", ".mjs", ".sh", ".js")
SKIP_DIRS = {"_archive", ".cache", "node_modules", "__pycache__", "v1_backup", "models"}
ONEOFF = re.compile(r"probe|test|tmp|sizetest|measure|mirror|fix_|trim_|dewm|wm_|lama|"
                    r"adaptive|_v\d|_kd|_xmas|_rain|xmasbag|_s\d|s6v", re.I)


def read(p):
    return io.open(p, encoding="utf-8").read()


def ledger_text():
    return read(LEDGER) if LEDGER.is_file() else ""


def task_dirs():
    return sorted(p for p in ROOT.glob("20*-*")
                  if p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}_", p.name))


def project_state(td, ledger):
    summ = td / "任务总结.md"
    in_ledger = td.name in ledger
    if not summ.is_file():
        return {"project": td.name, "summary": False, "retro": False,
                "in_ledger": in_ledger, "sections": []}
    heads = [h.strip() for h in re.findall(r"^#{2,3}\s+(.+)$", read(summ), re.M)]
    return {
        "project": td.name,
        "summary": True,
        "retro": any(any(m in h for m in RETRO_MARKERS) for h in heads),
        "in_ledger": in_ledger,
        "sections": heads,
    }


def shared_assets():
    out = []
    for f in sorted(SHARED.rglob("*")):
        if not f.is_file() or f.suffix not in ASSET_EXT:
            continue
        rel = f.relative_to(SHARED)
        if any(part in SKIP_DIRS or part.startswith(("_", ".")) for part in rel.parts):
            continue
        out.append("_shared/" + rel.as_posix())
    return out


def scattered_candidates(tasks):
    shared_names = {p.name for p in (SHARED / "scripts").glob("*") if p.is_file()}
    out = []
    for td in tasks:
        d = td / "scripts"
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.suffix not in SCRIPT_EXT:
                continue
            if f.name.startswith(("_", ".")) or f.name in shared_names:
                continue
            bucket = "一次性/实验" if ONEOFF.search(f.name) else "通用候选"
            out.append({"project": td.name, "path": f.relative_to(ROOT).as_posix(),
                        "type": f.suffix.lstrip("."), "bucket": bucket})
    return out


def md_table(headers, rows):
    head = "| " + " | ".join(headers) + " |\n| " + " | ".join(["---"] * len(headers)) + " |\n"
    return head + "".join("| " + " | ".join(str(c) for c in r) + " |\n" for r in rows)


def build_auto(states, assets, candidates):
    generic = [c for c in candidates if c["bucket"] == "通用候选"]
    oneoff = len(candidates) - len(generic)
    s1 = md_table(
        ["项目", "总结", "复盘章节", "台账已登记", "结论"],
        [[s["project"], "有" if s["summary"] else "缺", "有" if s["retro"] else "缺",
          "有" if s["in_ledger"] else "缺",
          "OK" if (s["retro"] and s["in_ledger"]) else "待复盘"] for s in states],
    )
    s2 = md_table(["已独立资产"], [[f"`{a}`"] for a in assets])
    s3 = (md_table(["来源项目", "通用候选（待判定）", "类型", "建议"],
                   [[c["project"], f"`{c['path']}`", c["type"], "见规范 07 §2 判定是否抽到 `_shared/scripts/`"]
                    for c in generic]) if generic else "（无）\n")
    return (
        f"\n_最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}；"
        f"由 `python _shared/scripts/project_retro.py --apply` 自动生成，勿手改本区块。_\n\n"
        "### A · 各项目复盘状态\n\n" + s1 +
        "\n### B · 已独立到 `_shared/` 的资产\n\n" + s2 +
        f"\n### C · 项目内散落的可复用候选（另有 {oneoff} 个一次性/实验脚本已按文件名过滤）\n\n" + s3
    )


def main():
    apply = "--apply" in sys.argv
    as_json = "--json" in sys.argv
    ledger = ledger_text()
    tasks = task_dirs()
    states = [project_state(td, ledger) for td in tasks]
    assets = shared_assets()
    candidates = scattered_candidates(tasks)
    need = [s["project"] for s in states if not (s["retro"] and s["in_ledger"])]
    payload = {
        "root": str(ROOT), "projects": len(tasks),
        "retro_done": sum(1 for s in states if s["retro"] and s["in_ledger"]),
        "shared_assets": len(assets), "scattered_candidates": len(candidates),
        "generic_candidates": sum(1 for c in candidates if c["bucket"] == "通用候选"),
        "need_retro": need, "states": states, "assets": assets, "candidates": candidates,
    }

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        print("PROJECT_RETRO", payload["projects"], "projects /",
              payload["retro_done"], "registered /", payload["generic_candidates"], "generic candidates")
        print("SHARED_ASSETS", payload["shared_assets"],
              "SCATTERED", payload["scattered_candidates"])
        for p in need:
            print("NEED_RETRO", p)
        print(build_auto(states, assets, candidates))

    if not apply:
        return 0
    if not LEDGER.is_file():
        print("ABORT: ledger missing", LEDGER, file=sys.stderr)
        return 2
    text = ledger
    block = AUTO_S + build_auto(states, assets, candidates) + AUTO_E
    # 只认「单独成行」的标记；人工区若在说明文字里引用标记字面量，不会被误当成区块起点。
    m_s = re.search(r"(?m)^" + re.escape(AUTO_S) + r"[ \t]*$", text)
    m_e = re.search(r"(?m)^" + re.escape(AUTO_E) + r"[ \t]*$", text)
    if m_s and m_e:
        text = text[:m_s.start()] + block + text[m_e.end():]
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    io.open(LEDGER, "w", encoding="utf-8", newline="\n").write(text)
    print("APPLIED", LEDGER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
