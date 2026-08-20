"""换肤编排层：mod 生成 → 覆盖 WAD 构建 → 补丁器注入（仿照 YsnSkin 三层）。

流程：
    SkinSwapper.swap(champion, skin_num)
      ├─ modgen.build_swap_for_skin()      # skinN.bin → skin0 覆盖 mod
      ├─ learn-overlay build               # ltk_overlay 构建覆盖 WAD
      └─ PatcherHost.runoverlay()          # 注入游戏进程（需游戏已启动）
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .modgen import build_swap_for_skin
from .patcher import PatcherHost

DEFAULT_GAME_DIR = Path(r"E:\Program Files (x86)\英雄联盟(26)\Game")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 优先本地 target；MinGW 中文路径问题时构建产物在 C:\ltk-target
LEARN_OVERLAY = next(
    (p for p in (
        _PROJECT_ROOT / "learn-overlay" / "target" / "release" / "learn-overlay.exe",
        Path(r"C:\ltk-target\release\learn-overlay.exe"),
    ) if p.is_file()),
    _PROJECT_ROOT / "learn-overlay" / "target" / "release" / "learn-overlay.exe",
)


@dataclass
class SwapResult:
    mod_dir: Path
    overlay_root: Path
    state_dir: Path
    overlay_built: list[str]
    patcher_state: str | None = None


class SkinSwapper:
    """完整换肤流程（构建不依赖游戏运行，注入需要游戏进程）。"""

    def __init__(self, game_dir: str | Path = DEFAULT_GAME_DIR,
                 session_dir: str | Path | None = None,
                 learn_overlay: str | Path = LEARN_OVERLAY,
                 patcher_host: str | Path | None = None):
        self.game_dir = Path(game_dir)
        self.learn_overlay = Path(learn_overlay)
        self.session_dir = Path(session_dir) if session_dir else (
            Path(__file__).resolve().parent.parent / "session")
        self.patcher_host = Path(patcher_host) if patcher_host else None

    # ---- 构建（无需游戏运行） ----

    def build_overlay(self, champion: str, skin_num: int,
                      tag: str | None = None) -> SwapResult:
        """生成 mod 并构建覆盖 WAD。champion 为小写别名（'ahri'）。"""
        from .diag import error, log

        tag = tag or f"{champion}-skin{skin_num}"
        mod_dir = self.session_dir / "mods" / tag
        overlay_root = self.session_dir / "overlays" / tag
        state_dir = self.session_dir / "state" / tag

        # 清掉旧产物（mod 内容可能变了）
        for p in (mod_dir, overlay_root, state_dir):
            if p.exists():
                shutil.rmtree(p)

        log("B1", "生成 mod（提取 skinN.bin → skin0 覆盖）",
            champion=champion, skin_num=skin_num)
        mod_dir = build_swap_for_skin(self.game_dir, champion, skin_num, mod_dir)
        log("B2", "mod 生成完成", mod_dir=str(mod_dir))

        if not self.learn_overlay.is_file():
            error("B3", "learn-overlay 未构建", path=str(self.learn_overlay),
                  hint="在 learn-overlay 目录执行 cargo build --release（见 docs/07 §3）")
            raise FileNotFoundError(
                f"learn-overlay 未构建: {self.learn_overlay}（先 cargo build --release）")

        log("B3", "调用 learn-overlay 构建覆盖 WAD",
            game_dir=str(self.game_dir), overlay_root=str(overlay_root))
        try:
            proc = subprocess.run(
                [str(self.learn_overlay), "build",
                 "--game-dir", str(self.game_dir),
                 "--mod-dir", str(mod_dir),
                 "--overlay-root", str(overlay_root),
                 "--state-dir", str(state_dir)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            error("B4", "learn-overlay 构建超时（>600s）",
                  hint="game_index 首次构建较慢，重试通常秒级完成（缓存已落盘）")
            raise
        if proc.returncode != 0:
            error("B4", "learn-overlay 构建失败", returncode=proc.returncode)
            for ln in proc.stdout.splitlines():
                error("B4", f"  stdout: {ln}")
            for ln in proc.stderr.splitlines():
                error("B4", f"  stderr: {ln}")
            raise RuntimeError(f"overlay 构建失败（详见上方日志，或检查 mod.config.json 格式）")
        log("B5", "构建成功", wads=len(proc.stdout.splitlines()))
        built = [ln for ln in proc.stdout.splitlines() if ln.startswith(("built:", "reused:"))]
        return SwapResult(mod_dir=mod_dir, overlay_root=overlay_root,
                          state_dir=state_dir, overlay_built=built)

    # ---- 注入（需要游戏进程运行） ----

    def apply_overlay(self, overlay_root: str | Path, timeout: float = 60.0) -> str:
        """启动补丁器注入覆盖 WAD，等待 injected 状态。"""
        with PatcherHost(overlay_root, patcher_host=self.patcher_host) as host:
            event = host.wait_for_state("injected", timeout=timeout)
            return event.detail

    def swap(self, champion: str, skin_num: int,
             inject: bool = True) -> SwapResult:
        """一键换肤：构建 + 注入（游戏须在运行）。"""
        result = self.build_overlay(champion, skin_num)
        if inject:
            result.patcher_state = self.apply_overlay(result.overlay_root)
        return result
