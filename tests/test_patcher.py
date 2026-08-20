"""patcher.py 驱动测试（对真实补丁器二进制做黑盒验证）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ysnskin_learn.patcher import PatcherHost, PATCHER_HOST


@unittest.skipUnless(PATCHER_HOST.is_file(), "需要 vendor 补丁器二进制")
class TestPatcherHost(unittest.TestCase):
    def test_runoverlay_scan_then_stop(self):
        """无游戏时停留在 scanning，stdin EOF 后干净退出。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            overlay = Path(tmp)
            (overlay / "fake.wad.client").write_bytes(b"test")
            with PatcherHost(overlay) as host:
                event = host.wait_for_state("injecting", timeout=15)
                self.assertEqual(event.detail, "scanning for game")
                # 主动关闭 stdin → 干净退出
                host.stop()
                self.assertIsNone(host.proc)  # stop 后置空
            self.assertIn("injecting", [e.state for e in host.events])

    def test_missing_overlay_raises(self):
        from ysnskin_learn.patcher import PatcherError

        with self.assertRaises(PatcherError):
            PatcherHost(Path("nonexistent-overlay-dir")).start()


if __name__ == "__main__":
    unittest.main()
