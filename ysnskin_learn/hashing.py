"""chunk 路径规范化与 XXH64 哈希（纯 Python 实现，零依赖）。

对应关系（见 docs/03-wad-format.md）：
- 游戏 WAD 的 chunk 路径哈希 = XXH64(规范化路径, seed=0)
- 规范化 = 转小写 + 反斜杠统一为斜杠
- 实现参照 ltk_modpkg 的 ``ChunkPath``（league-mod 仓库）与 XXH64 规范
"""

from __future__ import annotations

MASK64 = (1 << 64) - 1

PRIME64_1 = 0x9E3779B185EBCA87
PRIME64_2 = 0xC2B2AE3D27D4EB4F
PRIME64_3 = 0x165667B19E3779F9
PRIME64_4 = 0x85EBCA77C2B2AE63
PRIME64_5 = 0x27D4EB2F165667C5


def canonicalize_chunk_path(path: str) -> str:
    """把任意写法的游戏内路径规范化为 chunk 路径：小写 + 正斜杠。"""
    return path.replace("\\", "/").lower()


def chunk_path_hash(path: str) -> int:
    """chunk 路径哈希：XXH64(规范化路径字节, seed=0)。"""
    return xxh64(canonicalize_chunk_path(path).encode("utf-8"), 0)


def _rotl(x: int, r: int) -> int:
    return ((x << r) | (x >> (64 - r))) & MASK64


def _round(acc: int, lane: int) -> int:
    acc = (acc + lane * PRIME64_2) & MASK64
    acc = _rotl(acc, 31)
    return (acc * PRIME64_1) & MASK64


def _merge_round(acc: int, val: int) -> int:
    val = _round(0, val)
    acc ^= val
    return (acc * PRIME64_1 + PRIME64_4) & MASK64


def xxh64(data: bytes, seed: int = 0) -> int:
    """XXH64（seed=0 与 ltk 系工具一致）。参考 xxHash 规范实现。"""
    length = len(data)

    if length >= 32:
        v1 = (seed + PRIME64_1 + PRIME64_2) & MASK64
        v2 = (seed + PRIME64_2) & MASK64
        v3 = seed & MASK64
        v4 = (seed - PRIME64_1) & MASK64

        i = 0
        limit = length - 32
        while i <= limit:
            v1 = _round(v1, int.from_bytes(data[i:i + 8], "little"))
            v2 = _round(v2, int.from_bytes(data[i + 8:i + 16], "little"))
            v3 = _round(v3, int.from_bytes(data[i + 16:i + 24], "little"))
            v4 = _round(v4, int.from_bytes(data[i + 24:i + 32], "little"))
            i += 32

        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & MASK64
        h = _merge_round(h, v1)
        h = _merge_round(h, v2)
        h = _merge_round(h, v3)
        h = _merge_round(h, v4)
    else:
        # 未进入大块分支时，尾部从缓冲区开头处理
        i = 0
        h = (seed + PRIME64_5) & MASK64

    h = (h + length) & MASK64

    # 尾部循环从大块循环结束处继续（C 参考实现中 p 已越过所有 32 字节块）
    while i + 8 <= length:
        h ^= _round(0, int.from_bytes(data[i:i + 8], "little"))
        h = (_rotl(h, 27) * PRIME64_1 + PRIME64_4) & MASK64
        i += 8

    if i + 4 <= length:
        h ^= (int.from_bytes(data[i:i + 4], "little") * PRIME64_1) & MASK64
        h = (_rotl(h, 23) * PRIME64_2 + PRIME64_3) & MASK64
        i += 4

    while i < length:
        h ^= (data[i] * PRIME64_5) & MASK64
        h = (_rotl(h, 11) * PRIME64_1) & MASK64
        i += 1

    h ^= h >> 33
    h = (h * PRIME64_2) & MASK64
    h ^= h >> 29
    h = (h * PRIME64_3) & MASK64
    h ^= h >> 32
    return h
