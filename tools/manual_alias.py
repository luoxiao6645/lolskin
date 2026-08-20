"""手动执行 bin-alias-map 全流程并验证（诊断用）。"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ysnskin_learn.lhdb import Lhdb
from ysnskin_learn.modgen import build_alias_map, fnv1a32

LEARN = r"C:\ltk-target\release\learn-overlay.exe"
RAW = r"C:\ltk-test\aatrox-s33.bin"
CHAMP = "aatrox"
SKIN = 33

# 1) bin-list
out = subprocess.run([LEARN, "bin-list", RAW], capture_output=True, text=True,
                     encoding="utf-8").stdout
hashes = [int(ln.split()[1], 16) for ln in out.splitlines() if ln.startswith("object ")]
print(f"bin-list: {len(hashes)} 对象")

# 2) 映射
db = Lhdb.open(r"data\hashes\binhashes-2026-08-14.lhdb")
mapping = build_alias_map(hashes, f"characters/{CHAMP}/skins/skin{SKIN}",
                          f"characters/{CHAMP}/skins/skin0", db)
print(f"映射: {len(mapping)} 条")
for o, n in mapping[:5]:
    print(f"  {o:08x} -> {n:08x}")

# 3) bin-alias-map
map_file = Path(r"C:\ltk-test\map.txt")
map_file.write_text("\n".join(f"{o:08x} {n:08x}" for o, n in mapping), encoding="utf-8")
out_bin = r"C:\ltk-test\aatrox-aliased2.bin"
proc = subprocess.run([LEARN, "bin-alias-map", RAW, out_bin, str(map_file)],
                      capture_output=True, text=True, encoding="utf-8")
print("bin-alias-map stdout:", proc.stdout.strip())
print("bin-alias-map stderr:", proc.stderr.strip()[:500])
print("returncode:", proc.returncode)

# 4) 验证
if proc.returncode == 0:
    out = subprocess.run([LEARN, "bin-list", out_bin], capture_output=True, text=True,
                         encoding="utf-8").stdout
    objs = set(int(ln.split()[1], 16) for ln in out.splitlines() if ln.startswith("object "))
    print(f"改后对象数: {len(objs)}")
    print("根对象 78555f28 存在:", 0x78555F28 in objs)
    # 抽查一个粒子对象
    sample = next((p for h, p in [(h, db.get(h)) for h in hashes]
                   if p and "Skins/Skin33/Particles" in p), None)
    if sample:
        newp = sample.replace("Skins/Skin33", "Skins/Skin0")
        want = fnv1a32(newp.lower().encode())
        print(f"粒子对象改名检查: {newp} -> {want:08x} 存在={want in objs}")
