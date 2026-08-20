"""选人会话结构转储：进入 ChampSelect 后立即把完整 session JSON 写入文件。

用法：python -m tools.session_dump [输出文件]
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
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        PROJECT_ROOT / "session" / "session-dump.json")
    client = RiotClient(discover(Path(r"E:\Program Files (x86)\英雄联盟(26)")))
    print("[等待] 进入选人阶段后自动转储…", flush=True)
    last_phase = ""
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            st, raw = client.request("GET", "/lol-gameflow/v1/gameflow-phase")
            phase = raw.decode().strip('"')
            if phase != last_phase:
                print(f"[阶段] {phase}", flush=True)
                last_phase = phase
            if phase == "ChampSelect":
                st2, raw2 = client.request("GET", "/lol-champ-select/v1/session")
                if st2 == 200:
                    out.write_text(json.dumps(json.loads(raw2), ensure_ascii=False, indent=2),
                                   encoding="utf-8")
                    print(f"[转储完成] {out}", flush=True)
                    # 持续更新（预选→锁定字段会变化）
                    print("[持续监视] 每 2 秒更新转储（观察预选→锁定变化）…", flush=True)
                    while time.monotonic() < deadline:
                        st3, raw3 = client.request("GET", "/lol-champ-select/v1/session")
                        if st3 == 200:
                            s = json.loads(raw3)
                            out.write_text(json.dumps(s, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
                            cell = s.get("localPlayerCellId")
                            for m in s.get("myTeam") or []:
                                if m.get("cellId") == cell:
                                    print(f"[更新] championId={m.get('championId')} "
                                          f"pickIntent={m.get('championPickIntent')} "
                                          f"skin={m.get('selectedSkinId')}", flush=True)
                        time.sleep(2)
                time.sleep(1)
        except Exception as e:
            print(f"[异常] {e}", flush=True)
            time.sleep(2)
        time.sleep(0.5)
    print("[超时]", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
