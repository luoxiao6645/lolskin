"""WAD v3 文件提取器（读取 TOC + 解压 chunk）。

格式依据 docs/03-wad-format.md（ltk_wad-0.3.0 源码确认）。
"""

from __future__ import annotations

import gzip
import struct
import zlib
from pathlib import Path

from .hashing import chunk_path_hash

TOC_ENTRY_SIZE = 32
COMPRESSION_NONE = 0
COMPRESSION_GZIP = 1
COMPRESSION_SATELLITE = 2
COMPRESSION_ZSTD = 3
COMPRESSION_ZSTD_MULTI = 4


class WadError(RuntimeError):
    pass


class WadChunk:
    __slots__ = ("path_hash", "data_offset", "compressed_size", "uncompressed_size",
                 "compression_type", "frame_count", "start_frame", "checksum")

    def __init__(self, path_hash, data_offset, compressed_size, uncompressed_size,
                 compression_type, frame_count, start_frame, checksum):
        self.path_hash = path_hash
        self.data_offset = data_offset
        self.compressed_size = compressed_size
        self.uncompressed_size = uncompressed_size
        self.compression_type = compression_type
        self.frame_count = frame_count
        self.start_frame = start_frame
        self.checksum = checksum


class Wad:
    """只读 WAD v3 容器：TOC 解析 + 按路径哈希取 chunk。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with open(self.path, "rb") as f:
            magic, major, minor = struct.unpack("<HBB", f.read(4))
            if magic != 0x5752:
                raise WadError(f"不是 WAD 文件: {self.path} (magic=0x{magic:04X})")
            if major == 2:
                f.seek(84, 1)
            else:
                f.seek(256, 1)
            self.checksum, = struct.unpack("<Q", f.read(8))
            count = struct.unpack("<i", f.read(4))[0]
            if major in (1, 2):
                f.seek(4, 1)
            toc = f.read(TOC_ENTRY_SIZE * count)
            self._file = open(self.path, "rb")  # 保持打开以便后续读取
        self.major, self.minor = major, minor
        self._chunks: dict[int, WadChunk] = {}
        for i in range(count):
            off = i * TOC_ENTRY_SIZE
            if (major, minor) >= (3, 4):
                path_hash, data_offset, comp, uncomp = struct.unpack_from("<QIII", toc, off)
                type_frame = toc[off + 20]
                frame_count = type_frame >> 4
                ctype = type_frame & 0xF
                # v3.4 的 start_frame 是 24 位（hi, lo, mi 字节序）
                start_frame = (toc[off + 21] << 16) | (toc[off + 23] << 8) | toc[off + 22]
                checksum, = struct.unpack_from("<Q", toc, off + 24)
                chunk = WadChunk(path_hash, data_offset, comp, uncomp, ctype,
                                 frame_count, start_frame, checksum)
            else:
                path_hash, data_offset, = struct.unpack_from("<QI", toc, off)
                comp, uncomp = struct.unpack_from("<ii", toc, off + 12)
                type_frame = toc[off + 20]
                frame_count = type_frame >> 4
                ctype = type_frame & 0xF
                is_dup = toc[off + 21]
                start_frame, = struct.unpack_from("<H", toc, off + 22)
                checksum, = struct.unpack_from("<Q", toc, off + 24)
                chunk = WadChunk(path_hash, data_offset, comp, uncomp, ctype,
                                 frame_count, start_frame, checksum)
            self._chunks[path_hash] = chunk

    def __len__(self) -> int:
        return len(self._chunks)

    def chunks(self) -> list[WadChunk]:
        return list(self._chunks.values())

    def chunk_by_path(self, path: str) -> WadChunk | None:
        return self._chunks.get(chunk_path_hash(path))

    def read_chunk(self, chunk: WadChunk) -> bytes:
        """读取并解压一个 chunk（None/GZip/Zstd；Zstd 需要 zstandard 库）。"""
        self._file.seek(chunk.data_offset)
        raw = self._file.read(chunk.compressed_size)
        return decompress(raw, chunk.compression_type, chunk.uncompressed_size)

    def read_path(self, path: str) -> bytes | None:
        chunk = self.chunk_by_path(path)
        return self.read_chunk(chunk) if chunk else None

    def close(self) -> None:
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def decompress(raw: bytes, ctype: int, uncompressed_size: int) -> bytes:
    if ctype == COMPRESSION_NONE:
        return raw
    if ctype == COMPRESSION_GZIP:
        return gzip.decompress(raw)
    if ctype in (COMPRESSION_ZSTD, COMPRESSION_ZSTD_MULTI):
        try:
            import zstandard
        except ImportError:
            raise WadError("zstd chunk 需要 zstandard 库（pip install zstandard）") from None
        return zstandard.ZstdDecompressor().decompress(raw, max_output_size=uncompressed_size + 1)
    raise WadError(f"不支持的压缩类型: {ctype}")


def extract_to_file(wad: Wad, path: str, out_path: str | Path) -> None:
    data = wad.read_path(path)
    if data is None:
        raise WadError(f"WAD 中不存在: {path}")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
