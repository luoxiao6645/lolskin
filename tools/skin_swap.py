"""命令行换肤工具（端到端：构建 + 注入 + LCU 同步）。

用法：
    python -m tools.skin_swap                    # 自动检测选人阶段当前英雄，交互选皮肤
    python -m tools.skin_swap ahri 7             # 指定英雄(小写别名)与皮肤编号
    python -m tools.skin_swap ahri 7 --build-only   # 只构建覆盖 WAD（无需游戏进程）
    python -m tools.skin_swap ahri 7 --no-patch    # 不 PATCH LCU（只换游戏内模型）

流程（仿照 YsnSkin 模式一）：
    选人阶段尽早构建覆盖 WAD → 游戏进程出现时补丁器自动注入
    → LCU PATCH 选中目标皮肤（客户端 UI/语音同步）
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
from ysnskin_learn.overlay import SkinSwapper


def resolve_champion(catalog: SkinCatalog, spec: str) -> int:
    """按别名（小写/大小写不敏感）或中文名解析英雄 id。"""
    lower = spec.strip().lower()
    for cid, champ in catalog.champions.items():
        if champ.alias.lower() == lower or champ.name == spec.strip():
            return cid
    raise SystemExit(f"未找到英雄: {spec}（可用别名如 ahri / leesin）")


def pick_skin(catalog: SkinCatalog, champion_id: int, current_skin: int = 0) -> int:
    champion = catalog.champion(champion_id)
    skins = catalog.skins_of(champion_id)
    print(f"=== {champion.name}（{champion.alias}）===")
    for i, skin in enumerate(skins):
        mark = " ◀当前" if skin.id == current_skin else ""
        print(f"  [{i:>2}] skin{skin.skin_num:>3} {skin.name}{mark}")
    while True:
        choice = input("选择皮肤序号（Enter 取消）: ").strip()
        if not choice:
            raise SystemExit("已取消")
        try:
            return skins[int(choice)].id
        except (ValueError, IndexError):
            print("无效序号")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    build_only = "--build-only" in sys.argv
    no_patch = "--no-patch" in sys.argv

    catalog = SkinCatalog()
    swapper = SkinSwapper()

    champion_id = 0
    skin_id = 0
    client = None

    # 连接 LCU（构建不需要，PATCH 需要；客户端离线时降级）
    try:
        lockfile = discover(Path(r"E:\Program Files (x86)\英雄联盟(26)"))
        client = RiotClient(lockfile)
    except LcuError:
        if not build_only and not no_patch:
            pass  # 继续；构建不依赖客户端
    if client is not None:
        try:
            state = Gameflow(client).champ_select_state()
            if state.in_champ_select:
                champion_id = state.champion_id
                skin_id = state.selected_skin_id
        except LcuError:
            pass

    if len(args) >= 1:
        champion_id = resolve_champion(catalog, args[0])
    if len(args) >= 2:
        skin_id = champion_id * 1000 + int(args[1])

    if champion_id <= 0:
        raise SystemExit("无法确定英雄：请传入英雄（如 ahri）或进入选人阶段后运行")
    if skin_id <= 0:
        skin_id = pick_skin(catalog, champion_id)

    champion = catalog.champion(champion_id)
    skin = catalog.skin(skin_id)
    if skin is None:
        raise SystemExit(f"皮肤不存在: {skin_id}")
    print(f"目标: {champion.name} → {skin.name}（skin{skin.skin_num}）")

    # 1) 构建覆盖 WAD（选人阶段尽早完成）
    print("[1/3] 生成 mod + 构建覆盖 WAD ...")
    result = swapper.build_overlay(champion.alias.lower(), skin.skin_num)
    for line in result.overlay_built:
        print("     ", line)
    print(f"      覆盖目录: {result.overlay_root}")

    if build_only:
        print("[构建完成] 未注入（--build-only）。启动游戏后可用 --apply 注入。")
        return 0

    # 2) 注入（等待游戏进程出现；补丁器自动扫描）
    print("[2/3] 启动补丁器（等待游戏进程，进入对局时自动注入）...")
    from ysnskin_learn.patcher import PatcherHost
    with PatcherHost(result.overlay_root) as host:
        print("      补丁器运行中（游戏进程出现后自动注入）")
        print("      Ctrl+C 停止")
        if not no_patch and client is not None:
            # 3) LCU 同步选择（客户端 UI/语音/加载框）
            try:
                print("[3/3] LCU 同步选择皮肤 ...")
                Gameflow(client).select_skin(skin_id)
                print("      LCU 已选择", skin.name)
            except (LcuError, RuntimeError) as exc:
                print(f"      LCU 同步失败（不影响游戏内换肤）: {exc}")
        try:
            while host.proc is not None and host.proc.poll() is None:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        host.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
