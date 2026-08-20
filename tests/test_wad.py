"""wad.py 与 modgen.py 测试（使用真实游戏文件，跳过条件：无游戏目录）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GAME_DIR = Path(r"E:\Program Files (x86)\英雄联盟(26)\Game")
REAL_AHRI_WAD = GAME_DIR / "DATA" / "FINAL" / "Champions" / "Ahri.wad.client"

from ysnskin_learn.hashing import chunk_path_hash
from ysnskin_learn.wad import Wad, extract_to_file


@unittest.skipUnless(REAL_AHRI_WAD.is_file(), "需要英雄联盟游戏文件")
class TestWadRealFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wad = Wad(REAL_AHRI_WAD)

    @classmethod
    def tearDownClass(cls):
        cls.wad.close()

    def test_mount_and_lookup(self):
        self.assertEqual(len(self.wad), 6070)
        chunk = self.wad.chunk_by_path("data/characters/ahri/skins/skin0.bin")
        self.assertIsNotNone(chunk)
        self.assertEqual(chunk.path_hash, chunk_path_hash("data/characters/ahri/skins/skin0.bin"))

    def test_read_skin0_bin(self):
        data = self.wad.read_path("data/characters/ahri/skins/skin0.bin")
        self.assertIsNotNone(data)
        self.assertEqual(data[:4], b"PROP")
        version = int.from_bytes(data[4:8], "little")
        self.assertEqual(version, 3)

    def test_read_missing_path(self):
        self.assertIsNone(self.wad.read_path("data/characters/ahri/skins/skin999.bin"))


class TestWadRoundtrip(unittest.TestCase):
    def test_roundtrip(self):
        """写入合成的 None 压缩 WAD 再读回（不依赖游戏文件）。"""
        import struct
        import tempfile

        from ysnskin_learn.hashing import chunk_path_hash

        paths = {
            "data/test/aaa.bin": b"hello world",
            "data/test/bbb.bin": b"x" * 300,
        }
        chunks = sorted((chunk_path_hash(p), d) for p, d in paths.items())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.wad.client"
            with open(out, "wb") as f:
                f.write(b"RW" + bytes([3, 4]))
                f.write(b"\0" * 256)
                f.write(struct.pack("<Q", 0))
                f.write(struct.pack("<i", len(chunks)))
                toc_off = f.tell()
                f.write(b"\0" * (32 * len(chunks)))
                data_off = f.tell()
                for ph, data in chunks:
                    f.write(data)
                # 回填 TOC（压缩类型 None，start_frame 0，checksum 0）
                f.seek(toc_off)
                for ph, data in chunks:
                    f.write(struct.pack("<QIII", ph, data_off, len(data), len(data)))
                    f.write(bytes([0]))  # type_frame: compression None
                    f.write(b"\0\0\0")   # start_frame 24bit
                    f.write(struct.pack("<Q", 0))
                    data_off += len(data)
            wad = Wad(out)
            for p, d in paths.items():
                self.assertEqual(wad.read_path(p), d)
            wad.close()


if __name__ == "__main__":
    unittest.main()
