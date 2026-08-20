"""选人阶段自动换肤监听：检测到目标英雄后自动 PATCH 到目标皮肤。

用法：
    python -m tools.auto_patch ahri 7
    python -m tools.auto_patch ahri 7 --skin-name 电玩女神
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.catalog import SkinCatalog
from ysnskin_learn.endpoints import Gameflow
from ysnskin_learn.lcu import LcuError, RiotClient, discover

CLIENT_ROOT = Path(r"E:\Program Files (x86)\英雄联盟(26)")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("用法: python -m tools.auto_patch <英雄别名> <皮肤号>")
        return 2
    hero, skin_num = args[0].lower(), int(args[1])
    catalog = SkinCatalog()
    champion_id = next((cid for cid, c in catalog.champions.items()
                        if c.alias.lower() == hero), None)
    if champion_id is None:
        print(f"未找到英雄: {hero}")
        return 2
    target_id = champion_id * 1000 + skin_num
    target = catalog.skin(target_id)
    print(f"[目标] {hero} → skin{skin_num} {target.name if target else ''} (id={target_id})",
          flush=True)

    gameflow = None
    while gameflow is None:
        try:
            gameflow = Gameflow(RiotClient(discover(CLIENT_ROOT)))
            print("[在线] 客户端已连接，等待选人阶段（请选完英雄后停留）", flush=True)
        except LcuError:
            time.sleep(3)

    last_phase = ""
    while True:
        try:
            status, raw = gameflow.client.request("GET", "/lol-gameflow/v1/gameflow-phase")
            phase = raw.decode().strip('"')
            if phase != last_phase:
                print(f"[阶段] {phase}", flush=True)
                last_phase = phase
            if phase == "ChampSelect":
                st2, raw2 = gameflow.client.request("GET", "/lol-champ-select/v1/session")
                if st2 == 200:
                    import json
                    session = json.loads(raw2)
                    cid = 0
                    cell = session.get("localPlayerCellId")
                    for m in session.get("myTeam") or []:
                        if m.get("cellId") == cell:
                            cid = int(m.get("championId") or m.get("championPickIntent") or 0)
                            break
                    if cid == champion_id:
                        print(f"[选人] 检测到 {hero}，立即 PATCH → {target_id}", flush=True)
                        ok = gameflow.select_skin(target_id)
                        print(f"[{'成功' if ok else '失败'}] PATCH selectedSkinId={target_id}",
                              flush=True)
                        if ok:
                            print("[完成] 客户端已切换皮肤，请直接点【开始】进游戏验证！",
                                  flush=True)
                        return 0 if ok else 1
            if phase in ("GameStart", "InProgress", "Reconnect"):
                print("[错过] 游戏已开始，本轮未 PATCH", flush=True)
                return 1
        except LcuError:
            pass
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
