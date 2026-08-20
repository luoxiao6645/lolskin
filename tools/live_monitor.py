"""实机验证监视器：等待客户端上线 → 检测选人阶段 → 打印当前英雄。

用法：python -m tools.live_monitor [--hero ahri] [--skin 7]
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
    hero = args[0] if len(args) > 0 else None
    skin_num = int(args[1]) if len(args) > 1 else None
    catalog = SkinCatalog()
    gameflow = None
    last_phase = None
    deadline = time.monotonic() + 30 * 60  # 最多等 30 分钟
    while time.monotonic() < deadline:
        if gameflow is None:
            try:
                lockfile = discover(CLIENT_ROOT)
                gameflow = Gameflow(RiotClient(lockfile))
                print(f"[客户端在线] pid={lockfile.pid} port={lockfile.port}")
            except LcuError:
                print("[等待客户端…] 请启动英雄联盟客户端并登录")
                time.sleep(5)
                continue
        try:
            phase = gameflow.phase()
            if phase != last_phase:
                print(f"[阶段] {phase}")
                last_phase = phase
            if phase == "ChampSelect":
                state = gameflow.champ_select_state()
                champion = catalog.champion(state.champion_id)
                print(f"[选人] 英雄={champion.name if champion else state.champion_id} "
                      f"当前皮肤={state.selected_skin_id}")
                if hero and champion and champion.alias.lower() == hero.lower():
                    return 0  # 目标英雄已就位
        except LcuError:
            pass
        time.sleep(2)
    print("[超时] 30 分钟内未检测到客户端/选人阶段")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
