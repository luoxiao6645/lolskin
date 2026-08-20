"""探测英雄联盟客户端连接与选人状态（学习工具）。

用法：
    python -m tools.lcu_probe [客户端根目录]

默认客户端根目录通过 YSNSKIN_LEARN_CLIENT_DIR 环境变量或内置探测路径确定。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.endpoints import Gameflow
from ysnskin_learn.lcu import LcuError, RiotClient, discover

# 内置探测路径（可被环境变量覆盖）
DEFAULT_CLIENT_ROOTS = [
    Path(r"E:\Program Files (x86)\英雄联盟(26)"),
    Path(r"D:\WeGameApps\lol"),
    Path(r"C:\Riot Games\League of Legends"),
]


def find_client_root() -> Path | None:
    env_dir = os.environ.get("YSNSKIN_LEARN_CLIENT_DIR", "").strip()
    candidates = [Path(env_dir)] if env_dir else []
    candidates += DEFAULT_CLIENT_ROOTS
    for root in candidates:
        if root.is_dir():
            return root
    return None


def main() -> int:
    # GBK 等旧编码控制台无法输出部分 Unicode 符号；做兜底避免崩溃
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else find_client_root()
    if root is None or not root.is_dir():
        print("未找到客户端目录；请传入路径或设置 YSNSKIN_LEARN_CLIENT_DIR")
        return 2
    print(f"客户端根目录: {root}")
    try:
        lockfile = discover(root)
    except LcuError as exc:
        print(f"[失败] {exc}")
        return 1
    print(f"[连接] pid={lockfile.pid} port={lockfile.port} protocol={lockfile.protocol}")
    client = RiotClient(lockfile)
    gameflow = Gameflow(client)
    try:
        phase = gameflow.phase()
    except LcuError as exc:
        print(f"[失败] 客户端未运行或凭据过期: {exc}")
        print("       提示：请先启动英雄联盟客户端（lockfile 生效后重试）")
        return 1
    print(f"游戏阶段: {phase}")
    if phase == "ChampSelect":
        state = gameflow.champ_select_state()
        from ysnskin_learn.catalog import SkinCatalog, champion_id_of_skin

        catalog = SkinCatalog()
        champion = catalog.champion(state.champion_id)
        print(
            f"选人中: 英雄={champion.name if champion else state.champion_id} "
            f"当前皮肤={state.selected_skin_id} cell={state.local_cell_id}"
        )
        if champion:
            for skin in catalog.skins_of(champion.id):
                mark = "◀ 当前" if skin.id == state.selected_skin_id else ""
                print(f"  skin{skin.skin_num:>3}  {skin.name}  {mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
