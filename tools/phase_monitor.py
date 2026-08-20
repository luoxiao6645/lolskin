"""选人阶段状态监视器（含预选 pickIntent，每 0.5 秒，600 秒超时）。

用法：python -m tools.phase_monitor
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.lcu import discover, RiotClient


def main() -> int:
    client = RiotClient(discover(Path(r"E:\Program Files (x86)\英雄联盟(26)")))
    last = None
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            st, raw = client.request("GET", "/lol-gameflow/v1/gameflow-phase")
            phase = raw.decode().strip('"')
            cid = sid = intent = 0
            if phase == "ChampSelect":
                st2, raw2 = client.request("GET", "/lol-champ-select/v1/session")
                if st2 == 200:
                    s = json.loads(raw2)
                    cell = s.get("localPlayerCellId")
                    for m in s.get("myTeam") or []:
                        if m.get("cellId") == cell:
                            cid = m.get("championId") or 0
                            intent = m.get("championPickIntent") or 0
                            sid = m.get("selectedSkinId") or 0
            key = (phase, cid, intent, sid)
            if key != last:
                last = key
                print(f"[状态] phase={phase} championId={cid} pickIntent={intent} skin={sid}",
                      flush=True)
        except Exception as e:
            print(f"[异常] {e}", flush=True)
            time.sleep(2)
        time.sleep(0.5)
    print("[超时]", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
