"""实机一站式换肤（全环节带标记日志，用于定位各阶段问题）。

用法：
    python -m tools.live_swap <英雄别名> <皮肤号> [--overlay-dir C:\\ltk-overlay-xxx]

阶段标记：
    [A*] LCU/选人      [B*] 构建       [C*] 补丁器启动
    [D*] 注入          [E*] LCU 同步

注意：必须先启动本脚本（停留在选人阶段时），再点"开始"进入游戏。
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

CLIENT_ROOT = Path(r"E:\Program Files (x86)\英雄联盟(26)")


def log(tag: str, msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}][{tag}] {msg}", flush=True)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("用法: python -m tools.live_swap <英雄别名> <皮肤号> [--overlay-dir=路径] [--no-build]")
        return 2
    champion, skin_num = args[0].lower(), int(args[1])
    overlay_override = next((a.split("=", 1)[1] for a in sys.argv[1:]
                             if a.startswith("--overlay-dir=")), None)
    no_build = "--no-build" in sys.argv

    catalog = SkinCatalog()

    # ---- [A] 等待选人阶段 ----
    log("A1", f"等待客户端上线（目标: {champion} skin{skin_num}）...")
    gameflow = None
    while gameflow is None:
        try:
            lockfile = discover(CLIENT_ROOT)
            gameflow = Gameflow(RiotClient(lockfile))
            log("A2", f"客户端在线 pid={lockfile.pid} port={lockfile.port}")
        except LcuError:
            time.sleep(3)
    last_phase = ""
    while True:
        try:
            # 直接探测原始 phase（不依赖复杂会话解析，避免静默卡住）
            status, raw = gameflow.client.request("GET", "/lol-gameflow/v1/gameflow-phase")
            phase = raw.decode().strip('"')
            if phase != last_phase:
                log("A3", f"阶段变化 → {phase}")
                last_phase = phase
            if phase == "ChampSelect":
                # 取当前英雄（championId 或 pickIntent，训练模式用后者）
                st2, raw2 = gameflow.client.request("GET", "/lol-champ-select/v1/session")
                if st2 == 200:
                    import json
                    session = json.loads(raw2)
                    cid = 0
                    for m in session.get("myTeam") or []:
                        if m.get("cellId") == session.get("localPlayerCellId"):
                            cid = int(m.get("championId") or m.get("championPickIntent") or 0)
                            break
                    if cid > 0:
                        champ = catalog.champion(cid)
                        log("A4", f"选人阶段，英雄={champ.name if champ else cid}"
                                  f"（目标={champion}）")
                        state = gameflow.champ_select_state()
                        break
            if phase in ("GameStart", "InProgress", "Reconnect"):
                log("A5", "!! 游戏已开始——本轮错过注入窗口，请退出对局重开")
                return 1
        except LcuError:
            pass
        time.sleep(2)
    if catalog.champion(state.champion_id).alias.lower() != champion:
        log("A6", f"警告: 当前英雄不是 {champion}，继续（结果可能不对应）")

    # ---- [B] 构建覆盖 WAD（选人倒计时前完成；--no-build 跳过）----
    swapper = SkinSwapper()
    if no_build:
        log("B1", "--no-build：使用现有 overlay")
        if overlay_override:
            result = None
            overlay_dir = Path(overlay_override)
        else:
            log("B2", "!! --no-build 需要 --overlay-dir 指定现有覆盖目录")
            return 2
    else:
        log("B1", "构建覆盖 WAD（提取 skinN.bin → mod → ltk_overlay 引擎）...")
        t0 = time.monotonic()
        result = swapper.build_overlay(champion, skin_num)
        log("B2", f"构建完成 {time.monotonic() - t0:.1f}s → {result.overlay_root}")
        for line in result.overlay_built:
            log("B3", f"  {line}")
        overlay_dir = Path(overlay_override) if overlay_override else result.overlay_root
    log("B4", f"补丁器将使用 overlay: {overlay_dir}")
    if not (overlay_dir / "DATA" / "FINAL").is_dir():
        log("B5", f"!! overlay 目录无效（缺 DATA/FINAL）: {overlay_dir}")
        return 2

    # ---- [C] 启动提权补丁器 ----
    log("C1", "启动提权补丁器（UAC 弹窗请点【是】）...")
    from ysnskin_learn.patcher import PatcherHost
    host = PatcherHost(overlay_dir, elevate=True)
    host.start()
    log("C2", "补丁器已启动，等待游戏进程（现在可以点【开始】进入游戏！）")
    log("C3", "=== 请立即在客户端点【开始】进入游戏 ===")

    # ---- [D] 等待注入 ----
    log("D1", "等待游戏进程出现与 DLL 注入（最多 120 秒）...")
    deadline = time.monotonic() + 120
    seen_logs = 0
    seen_events = 0
    injected = False
    while time.monotonic() < deadline:
        for line in host.logs[seen_logs:]:
            log("DLL", line)
        seen_logs = len(host.logs)
        for event in host.events[seen_events:]:
            log("ST", f"{event.state} {event.detail}")
        seen_events = len(host.events)
        if host.last_state == "injected":
            injected = True
            break
        if host.last_state == "failed":
            break
        if host.proc is not None and host.proc.poll() is not None:
            log("D2", f"补丁器退出 code={host.proc.returncode}")
            break
        time.sleep(0.5)
    # 尾部日志
    for line in host.logs[seen_logs:]:
        log("DLL", line)
    for event in host.events[seen_events:]:
        log("ST", f"{event.state} {event.detail}")

    if not injected:
        log("D3", "!! 注入未成功，详见上方 DLL/ST 日志")
        host.stop()
        return 1
    log("D4", "注入成功！DLL 已附加。游戏加载英雄时应重定向 WAD。")

    # ---- [E] LCU 同步 ----
    try:
        skin_id = catalog.champion(state.champion_id).id * 1000 + skin_num
        gameflow.select_skin(skin_id)
        log("E1", f"LCU 已同步选择 skin{skin_num}")
    except Exception as exc:
        log("E2", f"LCU 同步失败（不影响游戏内换肤）: {exc}")

    log("F1", "补丁器保持运行中（游戏退出后自动结束）。观察游戏内效果。")
    try:
        while host.proc is not None and host.proc.poll() is None:
            for line in host.logs[seen_logs:]:
                log("DLL", line)
            seen_logs = len(host.logs)
            for event in host.events[seen_events:]:
                log("ST", f"{event.state} {event.detail}")
            seen_events = len(host.events)
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    host.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
