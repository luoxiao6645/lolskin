"""catalog 与 endpoints 模块测试（使用真实样本数据文件）。"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ysnskin_learn.catalog import SkinCatalog, champion_id_of_skin, skin_num_of
from ysnskin_learn.endpoints import ChampSelectState, Gameflow, PhasePoller


class TestCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = SkinCatalog()

    def test_loads_real_data(self):
        self.assertGreater(len(self.catalog), 2000)  # 2103 条皮肤
        self.assertGreater(len(self.catalog.champions), 100)  # 174 个英雄

    def test_skin_id_encoding(self):
        self.assertEqual(champion_id_of_skin(1000), 1)  # 安妮基础皮肤
        self.assertEqual(skin_num_of(1000), 0)
        self.assertEqual(champion_id_of_skin(110057), 110)
        self.assertEqual(skin_num_of(110057), 57)

    def test_annie_base_skin(self):
        annie = self.catalog.champion(1)
        self.assertIsNotNone(annie)
        self.assertEqual(annie.name, "黑暗之女")
        base = self.catalog.skin_of(1, 0)
        self.assertIsNotNone(base)
        self.assertTrue(base.is_base)
        self.assertEqual(base.name, "黑暗之女")

    def test_skins_of_contains_base_first(self):
        skins = self.catalog.skins_of(1)
        self.assertGreater(len(skins), 10)
        self.assertEqual(skins[0].skin_num, 0)


class TestGameflow(unittest.TestCase):
    def _state(self, phase="ChampSelect", champion_id=1, skin_id=1000, cell=5):
        client = mock.MagicMock()
        session = {
            "localPlayerCellId": cell,
            "myTeam": [{"cellId": cell, "championId": champion_id, "selectedSkinId": skin_id}],
        }
        client.get_json.side_effect = lambda path: (
            phase if path.endswith("gameflow-phase") else session
        )
        return Gameflow(client)

    def test_non_champ_select_returns_empty(self):
        gf = self._state(phase="Lobby")
        state = gf.champ_select_state()
        self.assertFalse(state.in_champ_select)
        self.assertEqual(state.champion_id, 0)

    def test_champ_select_state(self):
        state = self._state().champ_select_state()
        self.assertTrue(state.in_champ_select)
        self.assertEqual(state.champion_id, 1)
        self.assertEqual(state.selected_skin_id, 1000)

    def test_select_skin_patches(self):
        gf = self._state()
        gf.select_skin(1001)
        gf.client.patch_json.assert_called_once()
        path, body = gf.client.patch_json.call_args[0]
        self.assertIn("champ-select/v1/session", path)
        self.assertEqual(body["selectedSkinId"], 1001)
        self.assertEqual(body["localPlayerCellId"], 5)

    def test_select_skin_outside_champ_select_raises(self):
        gf = self._state(phase="Lobby")
        with self.assertRaises(RuntimeError):
            gf.select_skin(1001)

    def test_poller_calls_on_change(self):
        gf = self._state()
        poller = PhasePoller(gf, interval=0.01)
        seen = []
        poller.poll(lambda s: seen.append(s))
        poller.poll(lambda s: seen.append(s))  # 无变化不重复回调
        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0], ChampSelectState)


if __name__ == "__main__":
    unittest.main()
