"""模式一 · 独立悬浮窗（仿照 YsnSkin 的 companion overlay 窗口）。

功能：
- 无边框置顶小窗，显示当前英雄与皮肤列表
- 后台轮询 LCU 选人阶段（PhasePoller），自动跟随英雄
- 选择皮肤 → 后台线程执行 构建覆盖 WAD → 注入补丁器 → LCU 同步

用法：
    python -m tools.floater
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from ..catalog import Champion, Skin, SkinCatalog
from ..endpoints import ChampSelectState, Gameflow, PhasePoller
from ..lcu import RiotClient
from ..overlay import SkinSwapper

WINDOW_BG = "#10141c"
ACCENT = "#c8aa6e"
TEXT = "#f0e6d2"
MUTED = "#8a8f98"


class SkinFloater:
    def __init__(self, catalog: SkinCatalog, swapper: SkinSwapper,
                 gameflow: Gameflow | None, client_root: str = ""):
        self.catalog = catalog
        self.swapper = swapper
        self.gameflow = gameflow
        self.champion_id = 0
        self.current_skin_id = 0

        self.root = tk.Tk()
        self.root.title("YsnSkin-Learn")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=WINDOW_BG)
        self._build_ui()
        self._bind_drag()
        self._place_default()

    # ---- UI ----

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        self.title_var = tk.StringVar(value="YsnSkin-Learn（等待客户端…）")
        tk.Label(self.root, textvariable=self.title_var, bg=WINDOW_BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", **pad)

        row = tk.Frame(self.root, bg=WINDOW_BG)
        row.pack(fill="x", **pad)
        self.skin_combo = ttk.Combobox(row, state="readonly", width=34,
                                       font=("Microsoft YaHei UI", 9))
        self.skin_combo.pack(side="left")
        self.skin_combo.bind("<<ComboboxSelected>>", lambda e: self._on_pick())
        self.swap_btn = tk.Button(row, text="换肤", command=self._do_swap,
                                  bg=ACCENT, fg="#10141c", relief="flat",
                                  font=("Microsoft YaHei UI", 9, "bold"),
                                  state="disabled", width=5)
        self.swap_btn.pack(side="left", padx=(6, 0))

        self.status_var = tk.StringVar(value="未连接")
        tk.Label(self.root, textvariable=self.status_var, bg=WINDOW_BG, fg=MUTED,
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", **pad)

        close = tk.Label(self.root, text="×", bg=WINDOW_BG, fg=MUTED,
                         font=("Segoe UI", 11), cursor="hand2")
        close.place(relx=1.0, x=-8, y=4, anchor="ne")
        close.bind("<Button-1>", lambda e: self.root.destroy())

    def _bind_drag(self) -> None:
        self._drag = {"x": 0, "y": 0}

        def down(event):
            self._drag["x"], self._drag["y"] = event.x, event.y

        def move(event):
            x = self.root.winfo_x() + event.x - self._drag["x"]
            y = self.root.winfo_y() + event.y - self._drag["y"]
            self.root.geometry(f"+{x}+{y}")

        for widget in (self.root, self.title_var, *self.root.winfo_children()):
            try:
                widget.bind("<Button-1>", down)
                widget.bind("<B1-Motion>", move)
            except tk.TclError:
                pass

    def _place_default(self) -> None:
        self.root.geometry("300x120+40+400")

    # ---- 状态更新（LCU 轮询线程调用） ----

    def on_state(self, state: ChampSelectState) -> None:
        if not state.in_champ_select or state.champion_id <= 0:
            self.champion_id = 0
            self.root.after(0, self._set_idle)
            return
        self.champion_id = state.champion_id
        self.current_skin_id = state.selected_skin_id
        self.root.after(0, self._set_champion)

    def _set_idle(self) -> None:
        self.title_var.set("未在选人阶段")
        self.skin_combo["values"] = ()
        self.swap_btn["state"] = "disabled"
        self.status_var.set("进入选人阶段后自动就绪")

    def _set_champion(self) -> None:
        champion = self.catalog.champion(self.champion_id)
        if champion is None:
            self._set_idle()
            return
        skins = self.catalog.skins_of(self.champion_id)
        self.title_var.set(f"{champion.name}（{champion.alias}）")
        labels = [f"skin{skin.skin_num:>3}  {skin.name}" for skin in skins]
        self.skin_combo["values"] = labels
        current = next((i for i, s in enumerate(skins) if s.id == self.current_skin_id), 0)
        if skins:
            self.skin_combo.current(current)
            self.swap_btn["state"] = "normal"
        self.status_var.set("选择皮肤后点击 [换肤]")

    # ---- 换肤 ----

    def _on_pick(self) -> None:
        pass  # 选择即就绪，点击换肤按钮执行

    def _do_swap(self) -> None:
        if self.champion_id <= 0:
            return
        idx = self.skin_combo.current()
        skins = self.catalog.skins_of(self.champion_id)
        if idx < 0 or idx >= len(skins):
            return
        skin: Skin = skins[idx]
        champion: Champion | None = self.catalog.champion(self.champion_id)
        if champion is None:
            return
        self.swap_btn["state"] = "disabled"
        self.status_var.set(f"构建 {skin.name} …")
        threading.Thread(target=self._swap_worker, args=(champion, skin), daemon=True).start()

    def _swap_worker(self, champion: Champion, skin: Skin) -> None:
        try:
            result = self.swapper.build_overlay(champion.alias.lower(), skin.skin_num)
            self._status(f"覆盖构建完成（{len(result.overlay_built)} WAD）")
            # 注入（补丁器等待游戏进程；游戏未启动时保持运行直到手动停止）
            from ..patcher import PatcherHost
            self._status("补丁器运行中：游戏进程出现后自动注入…")
            with PatcherHost(result.overlay_root) as host:
                if self.gameflow is not None:
                    try:
                        self.gameflow.select_skin(skin.id)
                        self._status(f"已应用：{skin.name}（LCU 已同步）")
                    except Exception as exc:
                        self._status(f"已应用：{skin.name}（LCU 同步失败: {exc}）")
                else:
                    self._status(f"已应用：{skin.name}")
                # 保持注入直到窗口关闭或游戏退出；阻塞式等待
                while host.proc is not None and host.proc.poll() is None:
                    import time
                    time.sleep(1)
                host.stop()
        except Exception as exc:
            self._status(f"换肤失败: {exc}")
        finally:
            self.root.after(0, lambda: self.swap_btn.configure(state="normal"))

    def _status(self, text: str) -> None:
        self.root.after(0, lambda: self.status_var.set(text))

    # ---- 主循环 ----

    def run(self) -> None:
        poller = None
        if self.gameflow is not None:
            poller = PhasePoller(self.gameflow)
            stop = threading.Event()
            threading.Thread(target=poller.run, args=(self.on_state, stop), daemon=True).start()
            self.root.protocol("WM_DELETE_WINDOW", lambda: (stop.set(), self.root.destroy()))
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            if poller is not None:
                try:
                    stop.set()
                except NameError:
                    pass


def main() -> int:
    import sys
    from pathlib import Path

    from ..catalog import SkinCatalog
    from ..overlay import SkinSwapper

    catalog = SkinCatalog()
    swapper = SkinSwapper()
    gameflow = None
    try:
        from ..lcu import discover
        lockfile = discover(Path(r"E:\Program Files (x86)\英雄联盟(26)"))
        gameflow = Gameflow(RiotClient(lockfile))
    except Exception:
        pass
    SkinFloater(catalog, swapper, gameflow).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
