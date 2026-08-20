"""检查 Vex skin10 粒子资源在 WAD 中的存在性。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ysnskin_learn.hashing import chunk_path_hash
from ysnskin_learn.lhdb import Lhdb
from ysnskin_learn.wad import Wad

db = Lhdb.open(r"data\hashes\game-2026-08-14.lhdb")
w = Wad(r"E:\Program Files (x86)\英雄联盟(26)\Game\DATA\FINAL\Champions\Vex.wad.client")
hashes = {c.path_hash for c in w.chunks()}

paths = [
    "assets/characters/vex/skins/skin10/particles/vex_skin10_1q_explosion_smoke_mult.tex",
    "assets/characters/vex/skins/skin10/particles/skin10_smokeerode.tex",
    "assets/characters/vex/skins/skin10/particles/3161glow.tex",
    "assets/characters/vex/skins/skin10/particles/vex_skin10_1q_explosion_smoke_mult.scb",
]
for p in paths:
    h = chunk_path_hash(p)
    print(("存在" if h in hashes else "缺失"), p)

# 统计 WAD 中 skin10 与 base 的 assets 条目数（通过哈希表解析路径）
skin10 = 0
skin0_or_base = 0
resolved = 0
for c in w.chunks():
    name = db.get(c.path_hash)
    if not name:
        continue
    resolved += 1
    if "skins/skin10" in name:
        skin10 += 1
    if "skins/base" in name or "skins/skin0" in name:
        skin0_or_base += 1
print(f"解析条目 {resolved}/{len(w)}，skin10 相关 {skin10}，base/skin0 相关 {skin0_or_base}")
w.close()
