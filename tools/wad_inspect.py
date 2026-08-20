"""WAD v3 文件检查工具（学习用）：头信息 + TOC 摘要 + 路径哈希自检。

用法：
    python -m tools.wad_inspect <wad文件> [--verify-hash "data/final/..."]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.hashing import chunk_path_hash

TOC_ENTRY_V34 = "<QIII"  # path_hash u64, data_offset u32, comp_size u32, uncomp_size u32
TOC_ENTRY_SIZE = 32


def read_toc(path: Path):
    """返回 (major, minor, checksum, [(path_hash, data_offset, comp, uncomp, type_frame)])。"""
    with open(path, "rb") as f:
        magic, major, minor = struct.unpack("<HBB", f.read(4))
        assert magic == 0x5752, f"不是 WAD（magic=0x{magic:04X}）"
        if major == 2:
            f.seek(84, 1)
        else:
            f.seek(256, 1)
        checksum = struct.unpack("<Q", f.read(8))[0]
        count = struct.unpack("<i", f.read(4))[0]
        if major == 1 or major == 2:
            f.seek(4, 1)
        toc = f.read(TOC_ENTRY_SIZE * count)
    entries = []
    for i in range(count):
        off = i * TOC_ENTRY_SIZE
        path_hash, data_offset, comp, uncomp = struct.unpack_from(TOC_ENTRY_V34, toc, off)
        type_frame = toc[off + 20]
        entries.append((path_hash, data_offset, comp, uncomp, type_frame))
    return major, minor, checksum, entries


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"文件不存在: {path}")
        return 2

    major, minor, checksum, entries = read_toc(path)
    sorted_ok = all(entries[i][0] < entries[i + 1][0] for i in range(len(entries) - 1))
    types: dict[int, int] = {}
    for _, _, _, _, tf in entries:
        types[tf & 0xF] = types.get(tf & 0xF, 0) + 1
    print(f"{path.name}: v{major}.{minor} chunks={len(entries)} checksum={checksum:016X}")
    print(f"TOC 按 path_hash 升序: {'是' if sorted_ok else '否（异常）'}")
    print(f"压缩类型分布: { {k: v for k, v in sorted(types.items())} }  (0=None 1=GZip 2=Sat 3=Zstd 4=ZstdMulti)")

    # 可选：验证我们的 xxh64 与真实 TOC 中的条目吻合（可传多个）
    targets = [a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--verify-hash=")]
    for name in targets:
        want = chunk_path_hash(name)
        found = any(ph == want for ph, *_ in entries)
        print(f"哈希自检: xxh64(\"{name}\") = {want:016X} 在 TOC 中{'存在 [OK]' if found else '不存在'}")

    # 可选：用 mimir 哈希表把整个 TOC 解析成路径（--hashtable <lhdb> [--list <前缀>]）
    ht = next((a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--hashtable=")), None)
    if ht:
        from ysnskin_learn.lhdb import Lhdb
        db = Lhdb.open(ht)
        resolved = 0
        filter_prefix = next((a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--list=")), "")
        for ph, data_offset, comp, uncomp, _ in entries:
            name = db.get(ph)
            if name is None:
                continue
            resolved += 1
            if filter_prefix and not name.startswith(filter_prefix):
                continue
            print(f"  {name}  (offset={data_offset} comp={comp} uncomp={uncomp})")
        print(f"--hashtable: 解析 {resolved}/{len(entries)} 个条目"
              + (f"，前缀过滤 \"{filter_prefix}\"" if filter_prefix else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
