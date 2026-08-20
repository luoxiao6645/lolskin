"""游戏流程与选人阶段端点封装。

对应 YsnSkin ``lcu-bridge.js`` 的 state 轮询与 ``champion-select.js`` 的
LCU PATCH 选择逻辑（docs/02-lcu-protocol.md）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .lcu import RiotClient

GAMEFLOW_PHASE = "/lol-gameflow/v1/gameflow-phase"
CHAMP_SELECT_SESSION = "/lol-champ-select/v1/session"
CHAMP_SELECT_MY_SELECTION = "/lol-champ-select/v1/session/my-selection"


@dataclass(frozen=True)
class ChampSelectState:
    """选人会话中的本地玩家状态（champion-select.js 关注的字段）。"""

    phase: str
    champion_id: int
    selected_skin_id: int
    local_cell_id: int
    in_champ_select: bool


class Gameflow:
    def __init__(self, client: RiotClient):
        self.client = client

    def phase(self) -> str:
        return str(self.client.get_json(GAMEFLOW_PHASE) or "None")

    def champ_select_state(self) -> ChampSelectState:
        """查询选人会话；非选人阶段返回空状态（不抛异常）。"""
        phase = self.phase()
        if phase != "ChampSelect":
            return ChampSelectState(phase, 0, 0, 0, False)
        try:
            session = self.client.get_json(CHAMP_SELECT_SESSION)
        except Exception:
            # 阶段刚切换时会话可能瞬时不可用，与 lcu-bridge.js 一致：按无会话处理
            return ChampSelectState(phase, 0, 0, 0, False)
        local_cell = int(session.get("localPlayerCellId") or 0)
        champion_id = 0
        selected_skin_id = 0
        for member in session.get("myTeam") or []:
            if int(member.get("cellId") or -1) == local_cell:
                champion_id = int(member.get("championId") or member.get("championPickIntent") or 0)
                selected_skin_id = int(member.get("selectedSkinId") or 0)
                break
        return ChampSelectState(phase, champion_id, selected_skin_id, local_cell, True)

    def select_skin(self, skin_id: int) -> None:
        """PATCH 选人会话，把本地玩家的皮肤改为 skin_id（LCU 假选择）。

        客户端 UI / 语音 / 加载框随之同步为目标皮肤；实际模型由覆盖 WAD 提供。
        """
        state = self.champ_select_state()
        if not state.in_champ_select or state.local_cell_id <= 0:
            raise RuntimeError("当前不在选人阶段，无法选择皮肤")
        body = {"localPlayerCellId": state.local_cell_id, "selectedSkinId": int(skin_id)}
        self.client.patch_json(CHAMP_SELECT_SESSION, body)


class PhasePoller:
    """低频阶段轮询（模式一悬浮窗的驱动方式，对应 lcu-bridge.js 的 state 轮询）。"""

    def __init__(self, gameflow: Gameflow, interval: float = 0.25):
        self.gameflow = gameflow
        self.interval = interval
        self._last = None

    def poll(self, on_change=None):
        """轮询一次；阶段或选人变化时回调 on_change(state)。"""
        state = self.gameflow.champ_select_state()
        key = (state.phase, state.champion_id, state.selected_skin_id)
        if key != self._last:
            self._last = key
            if on_change is not None:
                on_change(state)
        return state

    def run(self, on_change, stop_event=None):
        """阻塞轮询直到 stop_event 置位（供悬浮窗线程使用）。"""
        while stop_event is None or not stop_event.is_set():
            self.poll(on_change)
            time.sleep(self.interval)
