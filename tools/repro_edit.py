"""手动复现 bin-edit 的字符串替换 bug。"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ysnskin_learn.lhdb import Lhdb
from ysnskin_learn.modgen import build_alias_map, fnv1a32

LEARN = r"C:\ltk-target\release\learn-overlay.exe"
RAW = r"C:\ltk-test\voli-s20.bin"
CHAMP = "volibear"
SKIN = 20

# 提取原始 bin
from ysnskin_learn.wad import Wad
w = Wad(r"E:\Program Files (x86)\英雄联盟(26)\Game\DATA\FINAL\Champions\Volibear.wad.client")
Path(RAW).write_bytes(w.read_path(f"data/characters/{CHAMP}/skins/skin{SKIN}.bin"))
w.close()

# 生成映射
out = subprocess.run([LEARN, "bin-list", RAW], capture_output=True, text=True,
                     encoding="utf-8").stdout
hashes = [int(ln.split()[1], 16) for ln in out.splitlines() if ln.startswith("object ")]
db = Lhdb.open(r"data\hashes\binhashes-2026-08-14.lhdb")
mapping = build_alias_map(hashes, f"characters/{CHAMP}/skins/skin{SKIN}",
                          f"characters/{CHAMP}/skins/skin0", db)
print(f"映射 {len(mapping)} 条")

map_file = Path(r"C:\ltk-test\map.txt")
map_file.write_text("\n".join(f"{o:08x} {n:08x}" for o, n in mapping), encoding="utf-8")

cap = CHAMP.capitalize()
cmd = [LEARN, "bin-edit", RAW, r"C:\ltk-test\voli-edited.bin", str(map_file),
       "--string-prefix", f"Characters/{cap}/Skins/Skin{SKIN}",
       f"Characters/{cap}/Skins/Skin0"]
proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
print("stdout:", proc.stdout.strip())
print("stderr:", proc.stderr.strip()[:300])
print("rc:", proc.returncode)
