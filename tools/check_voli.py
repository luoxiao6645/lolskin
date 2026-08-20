"""分析 Volibear skin20.bin 的粒子引用与资源存在性。"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ysnskin_learn.hashing import chunk_path_hash
from ysnskin_learn.wad import Wad

w = Wad(r"E:\Program Files (x86)\英雄联盟(26)\Game\DATA\FINAL\Champions\Volibear.wad.client")
data = w.read_path("data/characters/volibear/skins/skin20.bin")
print("skin20.bin 大小:", len(data) if data else None)

strs = set()
for s in re.findall(rb"[ -~]{12,}", data):
    t = s.decode(errors="replace")
    if "/particles/" in t.lower() or t.lower().endswith(
            (".scb", ".bin", ".anm", ".skn", ".skl", ".dds", ".tex")):
        strs.add(t)

assets = sorted(t for t in strs if t.upper().startswith("ASSETS"))
chars = sorted(t for t in strs if t.upper().startswith("CHARACTERS") or t.upper().startswith("DATA"))
print("ASSETS 资源引用:", len(assets))
for t in assets[:10]:
    print("  ", t[:130])
print("CHARACTERS/DATA 引用:", len(chars))
for t in chars[:10]:
    print("  ", t[:130])

# 验证粒子资源存在性
hashes = {c.path_hash for c in w.chunks()}
particle_refs = [t for t in assets if "/particles/" in t.lower()]
missing = [t for t in particle_refs if chunk_path_hash(t) not in hashes]
print(f"粒子资源: 引用 {len(particle_refs)}，缺失 {len(missing)}")
for t in missing[:10]:
    print("  缺失:", t[:130])
w.close()
