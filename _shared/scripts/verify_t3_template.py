# -*- coding: utf-8 -*-
"""T3 美式橄榄球射门盲盒 —— 模板库自检。
用法（工作区根目录执行）：
    python _shared/scripts/verify_t3_template.py

说明：本脚本原为「方案包自检 verify_plan.py」，2026-11-16 方案包归档到
_archive/历史方案/2026-11-15_美式橄榄球射门盲盒/ 后，改为只校验**模板库本身**
是否完整、自洽、可复用（不再依赖已归档的方案包目录，也不再做方案包↔模板的
逐字节比对——那是历史一次性动作）。
"""
import json
import os
import sys

# 本脚本位于 _shared/scripts/，向上两级 = 工作区根
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TPL = os.path.join(ROOT, "_shared", "templates", "T3_美式橄榄球射门盲盒")
SHARED = os.path.join(ROOT, "_shared", "templates")

errors = []


def check(cond, msg):
    if not cond:
        errors.append(msg)
    print(("  OK   " if cond else "  FAIL ") + msg)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


print("== 1. 模板库目录与文件 ==")
check(os.path.isdir(TPL), "T3 模板库目录存在")
tpl_files = [
    "README.md", "storyboard.json", "分镜脚本.md", "关键帧提示词.md",
    "视觉规范.md", "音效方案.md", "复用清单.md", "product_anchor.md",
]
for f in tpl_files:
    check(os.path.isfile(os.path.join(TPL, f)), "T3/" + f)

print("== 2. UTF-8 与替换字符 ==")
for dirpath, dirnames, filenames in os.walk(TPL):
    dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", ".cache")]
    for name in sorted(filenames):
        if not name.endswith((".md", ".json")):
            continue
        p = os.path.join(dirpath, name)
        rel = os.path.relpath(p, TPL)
        n = read(p).count(chr(0xFFFD))
        if n:
            errors.append("%s has %d U+FFFD" % (rel, n))
        print("  %-52s U+FFFD=%d" % (rel, n))
check(not any("U+FFFD" in e for e in errors), "模板库无 U+FFFD")

print("== 3. storyboard.json 校验 ==")
d = json.loads(read(os.path.join(TPL, "storyboard.json")))
a = sum(s["seconds"] for s in d["shots"] if s["shot_id"] in d["tracks"]["A"]["shots"])
b = sum(s["seconds"] for s in d["shots"] if s["shot_id"] in d["tracks"]["B"]["shots"])
total = sum(s["seconds"] for s in d["shots"])
check(len(d["shots"]) == 8, "shots == 8 (got %d)" % len(d["shots"]))
check(a == 25.0, "A track == 25.0s (got %s)" % a)
check(b == 4.0, "B track == 4.0s (got %s)" % b)
check(total == 29.0, "total == 29.0s (got %s)" % total)
check(d["spec"]["target_duration"] == 29.0, "spec.target_duration == 29.0")
check(d["tracks"]["A"]["shots"] == ["S1", "S2", "S3", "S4", "S5", "S6a", "TRANSIT"],
      "A track shot list")
check(d["tracks"]["B"]["shots"] == ["S9"], "B track shot list")

print("== 4. 关键约束落地检查 ==")
kp = read(os.path.join(TPL, "关键帧提示词.md"))
visual = read(os.path.join(TPL, "视觉规范.md"))
check("NO net" in kp or "无网" in kp, "关键帧提示词含无网锁")
check("holder" in kp.lower() or "holder" in visual.lower(), "holder 约束已记录")
# S4 球位：正向锁里球在球员与门柱之间
check("BETWEEN" in kp or "之间" in kp or "ahead of him" in kp.lower(),
      "S4 球位：球在球员与门柱之间（正向锁）")

print("== 5. 索引与交叉引用 ==")
idx = read(os.path.join(SHARED, "README.md"))
check("T3_美式橄榄球射门盲盒/README.md" in idx, "索引链接 T3 README")
check("T3 美式橄榄球射门盲盒（2026-11-15 入库" in idx, "索引已入库条目")
cl_path = os.path.join(SHARED, "模板应用检查清单.md")
if os.path.isfile(cl_path):
    cl = read(cl_path)
    check("T3 专属" in cl, "检查清单含 T3 段")
res_path = os.path.join(ROOT, "_shared", "外部素材资源库.md")
check(os.path.isfile(res_path), "_shared/外部素材资源库.md 存在")
readme = read(os.path.join(TPL, "README.md"))
check("外部素材资源库.md" in readme, "T3 README 引用外部素材库")

print()
if errors:
    print("FAILED (%d):" % len(errors))
    for e in errors:
        print("  - " + e)
    sys.exit(1)
print("ALL CHECKS PASSED")
