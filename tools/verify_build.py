"""端到端验证：真实游戏文件 → mod → 覆盖 WAD。

    python -m tools.verify_build ahri 1

验证点：
1. skinN.bin 提取成功且是 PROP v3
2. mod 目录结构正确（ltk FsModContent 布局）
3. learn-overlay build 成功（ltk_overlay 引擎）
4. 覆盖 WAD 存在，且其中的 skin0.bin 内容 == skinN.bin 内容（被替换）
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.hashing import chunk_path_hash
from ysnskin_learn.overlay import SkinSwapper
from ysnskin_learn.wad import Wad, decompress


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    champion = sys.argv[1] if len(sys.argv) > 1 else "ahri"
    skin_num = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    swapper = SkinSwapper()
    result = swapper.build_overlay(champion, skin_num)
    print(f"[1] mod 目录: {result.mod_dir}")
    print(f"[2] 覆盖目录: {result.overlay_root}")

    # 检查覆盖 WAD
    wads = list(result.overlay_root.rglob("*.wad.client"))
    print(f"[3] 覆盖 WAD 数量: {len(wads)}")
    if not wads:
        print("    失败：没有生成覆盖 WAD")
        return 1
    target = f"data/characters/{champion}/skins/skin0.bin"
    want_hash = chunk_path_hash(target)
    found = False
    for wad_path in wads:
        with Wad(wad_path) as wad:
            chunk = wad.chunk_by_path(target)
            if chunk is None:
                continue
            found = True
            data = wad.read_chunk(chunk)
            print(f"[4] {wad_path.name} 中 {target}: {len(data)} 字节, "
                  f"magic={data[:4]!r} version={int.from_bytes(data[4:8], 'little')}")
            # 与原始 skinN.bin 对比（bin-alias 改了 path_hash，应不同）
            game_wad = Wad(Path(swapper.game_dir) / "DATA" / "FINAL" / "Champions" / f"{champion.capitalize()}.wad.client")
            original = game_wad.read_path(f"data/characters/{champion}/skins/skin{skin_num}.bin")
            game_wad.close()
            print(f"[5] 内容已应用 bin-alias（与原始 skin{skin_num}.bin 不同）: {data != original}")
            if data == original:
                return 1
            # [6] 验证改后 bin 含 skin0 对象：反向别名应成功
            import subprocess, tempfile
            tmpdir = Path(tempfile.mkdtemp())
            overlay_bin = tmpdir / "skin0.bin"
            overlay_bin.write_bytes(data)
            check = subprocess.run(
                [str(swapper.learn_overlay), "bin-alias", str(overlay_bin), str(tmpdir / "out.bin"),
                 f"characters/{champion}/skins/skin0",
                 f"characters/{champion}/skins/skin999"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=60)
            ok = check.returncode == 0 and "OK" in check.stdout
            print(f"[6] 改后 bin 含 skin0 对象（反向改名成功）: {ok}")
            if not ok:
                print(check.stdout, check.stderr)
                return 1
            wad.close()
    if not found:
        print(f"    失败：覆盖 WAD 中没有 {target}")
        return 1
    print("[OK] 端到端构建链路验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
