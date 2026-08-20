"""mimir .lhdb 哈希表读取器（纯 Python）。

格式来自 LeagueToolkit/mimir 的 ltk_hashdb crate（docs 见
``reference/mimir/crates/ltk_hashdb/src/header.rs``）：

- 80 字节头：magic "HASHDB\\0\\0"、version、hash_kind、flags、key_width、
  offset_width、entry_count、keys/offsets/arena 偏移与大小、xxh3 checksum
- keys：entry_count × key_width（u64，升序）→ 二分查找
- offsets：entry_count × offset_width
- lengths：entry_count × u16（紧跟 offsets 之后）
- arena：路径字符串池，可能为 zeekstd 压缩（zstd 帧序列）；本实现用
  zstandard 的流式解压器整段解压（牺牲懒加载换简单正确）。

用法（resolve 单个哈希）：
    db = Lhdb.open("data/hashes/game-2026-08-14.lhdb")
    path = db.get(0x49E643F9C8A74BC7)   # -> "data/characters/ahri/skins/skin0.bin"
"""

from __future__ import annotations

import bisect
import struct
from pathlib import Path

MAGIC = b"HASHDB\0\0"
HEADER_SIZE = 80


class LhdbError(RuntimeError):
    pass


class Lhdb:
    def __init__(self, data: bytes):
        if data[:8] != MAGIC:
            raise LhdbError("不是 HASHDB 文件")
        version = struct.unpack_from("<H", data, 8)[0]
        if version != 1:
            raise LhdbError(f"不支持的版本: {version}")
        self.hash_kind = data[10]
        self.flags = data[11]
        self.key_width = data[12]
        self.offset_width = data[13]
        self.entry_count, = struct.unpack_from("<Q", data, 16)
        self.keys_offset, = struct.unpack_from("<Q", data, 24)
        self.offsets_offset, = struct.unpack_from("<Q", data, 32)
        self.arena_offset, = struct.unpack_from("<Q", data, 40)
        self.arena_decompressed_size, = struct.unpack_from("<Q", data, 48)
        self.arena_compressed_size, = struct.unpack_from("<Q", data, 56)
        self.checksum, = struct.unpack_from("<Q", data, 64)
        self._data = data
        self._arena = self._decompress_arena()

    @property
    def arena_compressed(self) -> bool:
        return bool(self.flags & 1)

    def _decompress_arena(self) -> bytes:
        raw = self._data[self.arena_offset:self.arena_offset + self.arena_compressed_size]
        if not self.arena_compressed:
            return raw
        try:
            import io
            import zstandard
        except ImportError:
            raise LhdbError("压缩 arena 需要 zstandard 库（pip install zstandard）") from None
        # zeekstd = 连续 zstd 帧 + 末尾 skippable seek table；stream_reader 可整体解出。
        # （decompressobj 有 16KB write_size 输出上限，不能直接用）
        reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw))
        chunks = []
        while True:
            chunk = reader.read(1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        out = b"".join(chunks)
        if len(out) != self.arena_decompressed_size:
            raise LhdbError(
                f"arena 解压尺寸不符: {len(out)} != {self.arena_decompressed_size}"
            )
        return out

    def _key_at(self, i: int) -> int:
        off = self.keys_offset + i * self.key_width
        return int.from_bytes(self._data[off:off + self.key_width], "little")

    def _offset_at(self, i: int) -> int:
        off = self.offsets_offset + i * self.offset_width
        return int.from_bytes(self._data[off:off + self.offset_width], "little")

    def _length_at(self, i: int) -> int:
        off = self.offsets_offset + self.entry_count * self.offset_width + i * 2
        return int.from_bytes(self._data[off:off + 2], "little")

    def index_of(self, hash_value: int) -> int | None:
        lo, hi = 0, self.entry_count
        while lo < hi:
            mid = (lo + hi) // 2
            if self._key_at(mid) < hash_value:
                lo = mid + 1
            else:
                hi = mid
        if lo < self.entry_count and self._key_at(lo) == hash_value:
            return lo
        return None

    def get(self, hash_value: int) -> str | None:
        i = self.index_of(hash_value)
        if i is None:
            return None
        start = self._offset_at(i)
        end = start + self._length_at(i)
        if end > len(self._arena):
            return None
        return self._arena[start:end].decode("utf-8", errors="replace")

    def contains(self, hash_value: int) -> bool:
        return self.index_of(hash_value) is not None

    def iter_entries(self):
        """按存储顺序产出 (hash, path)。"""
        for i in range(self.entry_count):
            start = self._offset_at(i)
            end = start + self._length_at(i)
            if end > len(self._arena):
                continue
            yield self._key_at(i), self._arena[start:end].decode("utf-8", errors="replace")

    @classmethod
    def open(cls, path: str | Path) -> "Lhdb":
        return cls(Path(path).read_bytes())


def resolve_batch(db: "Lhdb", hashes: list[int]) -> dict[int, str | None]:
    """批量解析（保持输入顺序）。"""
    return {h: db.get(h) for h in hashes}
