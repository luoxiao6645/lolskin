"""选人阶段皮肤切换测试（对齐 YsnSkin performNativeSelectionPatch）。

用法（选人阶段内）：
    python -m tools.patch_skin ahri 7      # PATCH 阿狸 → 电玩女神(103007)
    python -m tools.patch_skin 103 7       # 或直接给 championId
    python -m tools.patch_skin --list      # 只显示当前选人状态与可用皮肤

观察点：PATCH 成功后客户端 UI（头像/皮肤卡/语音）应切换为目标皮肤。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.catalog import SkinCatalog
from ysnskin_learn.endpoints import Gameflow
from ysnskin_learn.lcu import LcuError, RiotClient, discover

CLIENT_ROOT = Path(r"E:\Program Files (x86)\英雄联盟(26)")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    try:
        gameflow = Gameflow(RiotClient(discover(CLIENT_ROOT)))
    except LcuError as exc:
        print(f"[失败] {exc}")
        return 1
    state = gameflow.champ_select_state()
    print(f"阶段: {state.phase}")
    if not state.in_champ_select:
        print("[提示] 当前不在选人阶段（训练模式选人界面停留时间短，请先进选人界面）")
        return 1
    catalog = SkinCatalog()
    champion = catalog.champion(state.champion_id)
    print(f"英雄: {champion.name if champion else state.champion_id} "
          f"当前皮肤: {state.selected_skin_id}")

    if "--list" in sys.argv:
        if champion:
            for skin in catalog.skins_of(champion.id):
                print(f"  skin{skin.skin_num:>3} {skin.name} (id={skin.id})")
        return 0

    if len(args) < 2:
        print("用法: python -m tools.patch_skin <英雄> <皮肤号> 或 --list")
        return 2
    hero = args[0]
    skin_num = int(args[1])
    if hero.isdigit():
        champion_id = int(hero)
    else:
        champion_id = next((cid for cid, c in catalog.champions.items()
                            if c.alias.lower() == hero.lower()), None)
        if champion_id is None:
            print(f"未找到英雄: {hero}")
            return 2
    target_id = champion_id * 1000 + skin_num
    target = catalog.skin(target_id)
    print(f"目标: {target.name if target else target_id} (id={target_id})")
    ok = gameflow.select_skin(target_id)
    print(f"[{'成功' if ok else '失败'}] PATCH selectedSkinId={target_id}")
    print("请观察客户端：皮肤头像/卡片/语音是否切换")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
