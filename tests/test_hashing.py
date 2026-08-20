"""hashing 模块测试：xxh64 与路径规范化。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ysnskin_learn.hashing import canonicalize_chunk_path, chunk_path_hash, xxh64

# 已知向量：xxh64("", 0) = 0xEF46DB3751D8E999（xxHash 官方文档）
EMPTY_HASH = 0xEF46DB3751D8E999


class TestCanonicalize(unittest.TestCase):
    def test_lowercase_and_separators(self):
        self.assertEqual(
            canonicalize_chunk_path(r"ASSETS\Characters\Aatrox\Skins\Base\Aatrox.dds"),
            "assets/characters/aatrox/skins/base/aatrox.dds",
        )

    def test_idempotent(self):
        once = canonicalize_chunk_path(r"DATA\FINAL\Champions\Ahri.wad.client")
        self.assertEqual(canonicalize_chunk_path(once), once)


class TestXxh64(unittest.TestCase):
    def test_empty_vector(self):
        self.assertEqual(xxh64(b""), EMPTY_HASH)

    def test_short_and_long_consistency(self):
        # 与参考实现（ltk 测试）同源的路径
        path = "data/final/champions/aatrox.wad.subchunktoc"
        self.assertEqual(chunk_path_hash(path), xxh64(path.encode(), 0))

    def test_hash_independent_of_case_and_separator(self):
        # 对应 ltk_modpkg ChunkPath 测试语义
        forward = chunk_path_hash("assets/characters/aatrox/skins/base/aatrox.dds")
        back = chunk_path_hash(r"assets\characters\aatrox\skins\base\aatrox.dds")
        mixed = chunk_path_hash(r"ASSETS\Characters/Aatrox\Skins/Base/Aatrox.dds")
        self.assertEqual(forward, back)
        self.assertEqual(forward, mixed)


if __name__ == "__main__":
    unittest.main()
