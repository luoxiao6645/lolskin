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
        local_cell = session.get("localPlayerCellId")
        champion_id = 0
        selected_skin_id = 0
        # 注意：cellId/localPlayerCellId 可能为 0（训练营/人机对局），
        # 不能用 `or -1` 之类的 falsy 兜底——0 是合法值
        local_cell_int = int(local_cell) if local_cell is not None else -1
        for member in session.get("myTeam") or []:
            if member.get("cellId") is not None and int(member.get("cellId")) == local_cell_int:
                champion_id = int(member.get("championId") or member.get("championPickIntent") or 0)
                selected_skin_id = int(member.get("selectedSkinId") or 0)
                break
        return ChampSelectState(phase, champion_id, selected_skin_id, local_cell_int, True)

    def select_skin(self, skin_id: int) -> bool:
        """PATCH 选人会话，把本地玩家的皮肤改为 skin_id（LCU 假选择）。

        对齐 YsnSkin champion-select.js 的 performNativeSelectionPatch：
        1) 主路径: PATCH /lol-champ-select/v1/session/my-selection {selectedSkinId}
        2) 兜底:   部分客户端状态只接受对本地玩家 pick action 的更新，
                   从 session.actions 找本地 pick action 再 PATCH actions/{id}
        返回是否成功（不抛异常）。
        """
        selection_id = int(skin_id)
        if selection_id <= 0:
            return False
        # 主路径
        status, _ = self.client.request("PATCH", CHAMP_SELECT_MY_SELECTION,
                                        {"selectedSkinId": selection_id})
        if status in (200, 201, 204):
            return True
        # 兜底路径：找本地玩家的 pick action
        try:
            session = self.client.get_json(CHAMP_SELECT_SESSION)
        except Exception:
            return False
        local_cell = session.get("localPlayerCellId")
        local_cell_int = int(local_cell) if local_cell is not None else -1
        actions = session.get("actions") or []
        # actions 可能是嵌套数组（按阶段分组），拍平
        flat: list[dict] = []
        def walk(node):
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                flat.append(node)
        walk(actions)
        candidates = [
            a for a in flat
            if a.get("actorCellId") is not None
            and int(a.get("actorCellId")) == local_cell_int
            and int(a.get("id") or 0) > 0
            and (not a.get("type") or str(a["type"]).lower() == "pick")
        ]
        if not candidates:
            return False
        # 优先进行中的 action，其次未完成，最后按 id 大者
        candidates.sort(key=lambda a: (
            2 if a.get("isInProgress") is True else (1 if a.get("completed") is False else 0),
            int(a.get("id") or 0)))
        action = candidates[-1]
        status, _ = self.client.request(
            "PATCH", f"{CHAMP_SELECT_SESSION}/actions/{int(action['id'])}",
            {"selectedSkinId": selection_id})
        return status in (200, 201, 204)


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
