"""验证 bin-alias-map 的粒子对象改名正确性（直接计算期望 hash 对照）。"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ysnskin_learn.lhdb import Lhdb


def fnv(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


db = Lhdb.open(r"data\hashes\binhashes-2026-08-14.lhdb")
out = subprocess.run(
    [r"C:\ltk-target\release\learn-overlay.exe", "bin-list", r"C:\ltk-test\aatrox-aliased.bin"],
    capture_output=True, text=True, encoding="utf-8").stdout
hashes = set(int(ln.split()[1], 16) for ln in out.splitlines() if ln.startswith("object "))
print("对象数:", len(hashes))

# 根对象期望：binhashes 表里 Skin0 路径对应的 hash（每英雄不同，不能硬编码）
want_root = next((h for h, p in
                  [(h, db.get(h)) for h in hashes] if p == "Characters/Aatrox/Skins/Skin0"), None)
print("根对象 Characters/Aatrox/Skins/Skin0 存在:", want_root is not None, want_root and f"{want_root:08x}")

old_objs = [(h, db.get(h)) for h in hashes if db.get(h)]
print("binhashes 可解析对象（改名前路径）:", len(old_objs))
ok = 0
fail = 0
for h, p in old_objs:
    if "Skins/Skin33" not in p:
        continue
    newp = p.replace("Skins/Skin33", "Skins/Skin0")
    want = fnv(newp.lower().encode())
    present = want in hashes
    ok += present
    fail += not present
    print(f"  {'OK ' if present else 'MISS'} {newp} -> {want:08x}")
print(f"改名校验: 成功 {ok} 失败 {fail}")
