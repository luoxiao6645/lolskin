"""选人阶段 PATCH 诊断：PATCH 前后回读 selectedSkinId，检测回滚/拒绝。

用法：
    python -m tools.patch_diag ahri 7
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.catalog import SkinCatalog
from ysnskin_learn.lcu import LcuError, RiotClient, discover

CLIENT_ROOT = Path(r"E:\Program Files (x86)\英雄联盟(26)")


def get_session(client: RiotClient):
    status, raw = client.request("GET", "/lol-champ-select/v1/session")
    if status != 200:
        return None
    return json.loads(raw)


def local_skin(session) -> int:
    if not session:
        return -1
    cell = session.get("localPlayerCellId")
    for m in session.get("myTeam") or []:
        if m.get("cellId") == cell:
            return int(m.get("selectedSkinId") or 0)
    return -1


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("用法: python -m tools.patch_diag <英雄别名> <皮肤号>")
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

    client = None
    while client is None:
        try:
            client = RiotClient(discover(CLIENT_ROOT))
            print("[在线] 等待选人阶段...", flush=True)
        except LcuError:
            time.sleep(3)

    last_phase = ""
    while True:
        status, raw = client.request("GET", "/lol-gameflow/v1/gameflow-phase")
        phase = raw.decode().strip('"')
        if phase != last_phase:
            print(f"[阶段] {phase}", flush=True)
            last_phase = phase
        if phase == "ChampSelect":
            session = get_session(client)
            if session is None:
                time.sleep(1)
                continue
            cid = 0
            cell = session.get("localPlayerCellId")
            for m in session.get("myTeam") or []:
                if m.get("cellId") == cell:
                    cid = int(m.get("championId") or m.get("championPickIntent") or 0)
            print(f"[选人] 英雄={cid} PATCH前 selectedSkinId={local_skin(session)}", flush=True)
            if cid != champion_id:
                print(f"[等待] 当前英雄 {cid} != 目标 {champion_id}，继续等（请选阿狸）", flush=True)
                time.sleep(2)
                continue

            # 1) my-selection 主路径：完整响应
            st, body = client.request("PATCH", "/lol-champ-select/v1/session/my-selection",
                                      {"selectedSkinId": target_id})
            print(f"[PATCH my-selection] status={st} body={body.decode()[:200]}", flush=True)
            time.sleep(1)
            print(f"[回读 1s] selectedSkinId={local_skin(get_session(client))}", flush=True)
            time.sleep(2)
            print(f"[回读 3s] selectedSkinId={local_skin(get_session(client))}", flush=True)

            # 2) actions 兜底
            session = get_session(client)
            actions = session.get("actions") or []
            flat = []
            def walk(node):
                if isinstance(node, list):
                    for i in node:
                        walk(i)
                elif isinstance(node, dict):
                    flat.append(node)
            walk(actions)
            print(f"[actions] 共 {len(flat)} 个:", flush=True)
            for a in flat:
                print(f"   id={a.get('id')} actorCell={a.get('actorCellId')} "
                      f"type={a.get('type')} inProgress={a.get('isInProgress')} "
                      f"completed={a.get('completed')} championId={a.get('championId')}",
                      flush=True)
            cell = session.get("localPlayerCellId")
            mine = [a for a in flat if int(a.get("actorCellId") or -1) == cell
                    and (not a.get("type") or str(a["type"]).lower() == "pick")]
            if mine:
                aid = int(mine[-1]["id"])
                st, body = client.request(
                    "PATCH", f"/lol-champ-select/v1/session/actions/{aid}",
                    {"selectedSkinId": target_id})
                print(f"[PATCH action {aid}] status={st} body={body.decode()[:200]}", flush=True)
                time.sleep(1)
                print(f"[回读 action 后] selectedSkinId={local_skin(get_session(client))}",
                      flush=True)
            else:
                print("[actions] 无本地 pick action", flush=True)
            print("[完成] 请观察客户端 UI 是否变化，然后点开始进游戏验证", flush=True)
            return 0
        if phase in ("GameStart", "InProgress", "Reconnect"):
            print("[错过] 游戏已开始", flush=True)
            return 1
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
