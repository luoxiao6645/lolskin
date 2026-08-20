"""实时探测 gameflow 阶段（带 flush，用于后台管道场景）。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.lcu import LcuError, RiotClient, discover

CLIENT_ROOT = Path(r"E:\Program Files (x86)\英雄联盟(26)")


def main() -> int:
    import os
    os.environ["PYTHONUNBUFFERED"] = "1"
    try:
        lockfile = discover(CLIENT_ROOT)
        client = RiotClient(lockfile)
    except LcuError as exc:
        print(f"[客户端未上线] {exc}", flush=True)
        return 1
    print(f"[客户端在线] port={lockfile.port}", flush=True)
    deadline = time.monotonic() + 20 * 60
    last = None
    while time.monotonic() < deadline:
        try:
            status, raw = client.request("GET", "/lol-gameflow/v1/gameflow-phase")
            phase = raw.decode().strip('"')
            if phase != last:
                print(f"[阶段] {phase}", flush=True)
                last = phase
            if phase == "ChampSelect":
                status2, raw2 = client.request("GET", "/lol-champ-select/v1/session")
                if status2 == 200:
                    import json
                    session = json.loads(raw2)
                    cell = session.get("localPlayerCellId")
                    for m in session.get("myTeam") or []:
                        if m.get("cellId") == cell:
                            print(f"[选人] championId={m.get('championId')} "
                                  f"skinId={m.get('selectedSkinId')}", flush=True)
                            return 0
        except LcuError:
            pass
        time.sleep(2)
    print("[超时]", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
