"""catalog 与 endpoints 模块测试（使用真实样本数据文件）。"""

import json
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
        client.request.return_value = (200, b"")
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

    def test_select_skin_patches_my_selection(self):
        """主路径：PATCH my-selection，仅传 selectedSkinId（对齐 YsnSkin）。"""
        gf = self._state()
        self.assertTrue(gf.select_skin(1001))
        path, body = gf.client.request.call_args.args[1], gf.client.request.call_args.args[2]
        self.assertIn("my-selection", path)
        self.assertEqual(body, {"selectedSkinId": 1001})

    def test_select_skin_falls_back_to_action(self):
        """兜底路径：my-selection 失败时 PATCH 本地 pick action。"""
        client = mock.MagicMock()
        session = {
            "localPlayerCellId": 5,
            "myTeam": [{"cellId": 5, "championId": 1, "selectedSkinId": 1000}],
            "actions": [[{"id": 42, "actorCellId": 5, "type": "pick", "isInProgress": True}]],
        }
        client.get_json.side_effect = lambda path: session
        # my-selection PATCH -> 404；actions PATCH -> 204
        client.request.side_effect = [(404, b""), (204, b"")]
        gf = Gameflow(client)
        self.assertTrue(gf.select_skin(1001))
        calls = [c.args for c in client.request.call_args_list]
        self.assertEqual(len(calls), 2)
        self.assertIn("my-selection", calls[0][1])
        self.assertIn("actions/42", calls[1][1])
        self.assertEqual(calls[1][2], {"selectedSkinId": 1001})

    def test_select_skin_invalid_id_returns_false(self):
        gf = self._state()
        self.assertFalse(gf.select_skin(0))

    def test_champ_select_state_cell_zero(self):
        """回归：localPlayerCellId=0（训练营/人机）时 cellId=0 必须能匹配。"""
        client = mock.MagicMock()
        session = {
            "localPlayerCellId": 0,
            "myTeam": [{"cellId": 0, "championId": 0, "championPickIntent": 103,
                        "selectedSkinId": 0}],
        }
        client.get_json.side_effect = lambda path: (
            "ChampSelect" if path.endswith("gameflow-phase") else session
        )
        state = Gameflow(client).champ_select_state()
        self.assertTrue(state.in_champ_select)
        self.assertEqual(state.champion_id, 103)
        self.assertEqual(state.local_cell_id, 0)

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
