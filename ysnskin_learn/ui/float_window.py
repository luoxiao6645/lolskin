"""模式一 · 皮肤选择悬浮窗（仿照 YsnSkin 的 companion overlay）。

界面：
- 无边框置顶小窗，仿 YsnSkin 深色 + 金色主题
- 顶部：英雄名 + 当前皮肤
- 中部：皮肤列表（滚动，中文名 + skin 编号），点击选中
- 底部：状态栏 + [换肤] 按钮

流程（选人阶段操作）：
    选皮肤 → 构建覆盖 WAD（增量缓存）→ 提权补丁器就位 → 游戏启动时注入
    → 游戏内生效；真实对局同时 PATCH LCU 同步客户端 UI

用法：
    python -m tools.floater
"""

from __future__ import annotations

import threading
import time
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
DANGER = "#e06c5f"
OK = "#7ec8a0"

WINDOW_W = 340
WINDOW_H = 460


class SkinFloater:
    def __init__(self, catalog: SkinCatalog, swapper: SkinSwapper,
                 gameflow: Gameflow | None):
        self.catalog = catalog
        self.swapper = swapper
        self.gameflow = gameflow
        self.champion_id = 0
        self.current_skin_id = 0
        self._busy = False

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
        pad = {"padx": 10, "pady": 4}

        # 顶栏：标题 + 关闭
        bar = tk.Frame(self.root, bg=WINDOW_BG)
        bar.pack(fill="x", padx=10, pady=(8, 0))
        self.title_var = tk.StringVar(value="YsnSkin-Learn · 等待客户端…")
        tk.Label(bar, textvariable=self.title_var, bg=WINDOW_BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        close = tk.Label(bar, text="×", bg=WINDOW_BG, fg=MUTED,
                         font=("Segoe UI", 12), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.root.destroy())

        # 当前皮肤信息
        self.skin_info_var = tk.StringVar(value="未进入选人阶段")
        tk.Label(self.root, textvariable=self.skin_info_var, bg=WINDOW_BG, fg=TEXT,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", **pad)

        # 皮肤列表（滚动）
        list_frame = tk.Frame(self.root, bg=WINDOW_BG)
        list_frame.pack(fill="both", expand=True, **pad)
        self.skin_list = tk.Listbox(
            list_frame, bg="#1a2130", fg=TEXT, selectbackground=ACCENT,
            selectforeground="#10141c", font=("Microsoft YaHei UI", 9),
            highlightthickness=0, borderwidth=0, activestyle="none",
        )
        scroll = ttk.Scrollbar(list_frame, orient="vertical",
                               command=self.skin_list.yview)
        self.skin_list.configure(yscrollcommand=scroll.set)
        self.skin_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.skin_list.bind("<Double-Button-1>", lambda e: self._do_swap())

        # 底部：状态 + 按钮
        bottom = tk.Frame(self.root, bg=WINDOW_BG)
        bottom.pack(fill="x", **pad)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(bottom, textvariable=self.status_var, bg=WINDOW_BG, fg=MUTED,
                 font=("Microsoft YaHei UI", 8), anchor="w").pack(side="left", fill="x", expand=True)
        self.swap_btn = tk.Button(bottom, text="换肤", command=self._do_swap,
                                  bg=ACCENT, fg="#10141c", relief="flat",
                                  font=("Microsoft YaHei UI", 9, "bold"),
                                  state="disabled", width=6)
        self.swap_btn.pack(side="right")

        # 提示
        tk.Label(self.root, text="双击皮肤 或 选中后点[换肤] · 进游戏前完成",
                 bg=WINDOW_BG, fg=MUTED, font=("Microsoft YaHei UI", 7)).pack(anchor="w", **pad)

    def _bind_drag(self) -> None:
        self._drag = {"x": 0, "y": 0}

        def down(event):
            self._drag["x"], self._drag["y"] = event.x, event.y

        def move(event):
            x = self.root.winfo_x() + event.x - self._drag["x"]
            y = self.root.winfo_y() + event.y - self._drag["y"]
            self.root.geometry(f"+{x}+{y}")

        for widget in self.root.winfo_children():
            try:
                widget.bind("<Button-1>", down)
                widget.bind("<B1-Motion>", move)
            except tk.TclError:
                pass

    def _place_default(self) -> None:
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+40+400")

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
        self.title_var.set("YsnSkin-Learn · 未在选人阶段")
        self.skin_info_var.set("进入选人阶段后自动加载皮肤列表")
        self.skin_list.delete(0, tk.END)
        self.swap_btn["state"] = "disabled"

    def _set_champion(self) -> None:
        champion = self.catalog.champion(self.champion_id)
        if champion is None:
            self._set_idle()
            return
        skins = self.catalog.skins_of(self.champion_id)
        current = self.catalog.skin(self.current_skin_id)
        self.title_var.set(f"{champion.name}（{champion.alias}）")
        self.skin_info_var.set(
            f"当前皮肤: {current.name if current else self.current_skin_id}")
        self.skin_list.delete(0, tk.END)
        for skin in skins:
            mark = " ◀" if skin.id == self.current_skin_id else ""
            self.skin_list.insert(tk.END, f"skin{skin.skin_num:>3}  {skin.name}{mark}")
        if skins:
            self.swap_btn["state"] = "normal"

    # ---- 换肤 ----

    def _do_swap(self) -> None:
        if self._busy or self.champion_id <= 0:
            return
        sel = self.skin_list.curselection()
        if not sel:
            self._set_status("请先在列表中选择皮肤", DANGER)
            return
        skins = self.catalog.skins_of(self.champion_id)
        skin: Skin = skins[sel[0]]
        champion: Champion | None = self.catalog.champion(self.champion_id)
        if champion is None:
            return
        self._busy = True
        self.swap_btn["state"] = "disabled"
        self._set_status(f"构建 {skin.name} …")
        threading.Thread(target=self._swap_worker, args=(champion, skin), daemon=True).start()

    def _swap_worker(self, champion: Champion, skin: Skin) -> None:
        try:
            # 1) 构建覆盖 WAD（game_index 缓存后约几秒）
            t0 = time.monotonic()
            self._set_status("构建覆盖 WAD …")
            result = self.swapper.build_overlay(champion.alias.lower(), skin.skin_num)
            self._set_status(f"构建完成 {time.monotonic() - t0:.0f}s，启动补丁器…")
            # 2) 提权补丁器（UAC 弹窗首次需授权；国服游戏以管理员运行）
            from ..patcher import PatcherHost
            host = PatcherHost(result.overlay_root, elevate=True)
            host.start()
            self._set_status("补丁器就位！现在可以点【开始】进入游戏")
            # 3) 真实对局时同步 PATCH LCU（训练营 PATCH 无效，跳过影响）
            if self.gameflow is not None:
                try:
                    if self.gameflow.select_skin(skin.id):
                        self._set_status(f"已选择 {skin.name}，补丁器待命")
                except Exception:
                    pass
            # 4) 保持补丁器运行直到游戏结束，实时显示状态
            last_state = ""
            while host.proc is not None and host.proc.poll() is None:
                state = host.last_state
                if state and state != last_state:
                    last_state = state
                    detail = host.events[-1].detail if host.events else ""
                    if state == "injected":
                        self._set_status(f"注入成功！游戏内应为 {skin.name}", OK)
                    elif state == "failed":
                        self._set_status(f"注入失败: {detail}", DANGER)
                    else:
                        self._set_status(f"补丁器: {state} {detail}")
                # 打印 DLL 日志到控制台（诊断用）
                for line in host.logs:
                    if "ltk_patcher_dll" in line:
                        print(f"[dll] {line}", flush=True)
                time.sleep(1)
            host.stop()
            self._set_status("补丁器已停止（游戏退出）")
        except Exception as exc:
            self._set_status(f"换肤失败: {exc}", DANGER)
        finally:
            self._busy = False
            self.root.after(0, lambda: self.swap_btn.configure(state="normal"))

    def _set_status(self, text: str, color: str | None = None) -> None:
        self.root.after(0, lambda: (self.status_var.set(text),
                                    self.status_label_color(color)))

    def status_label_color(self, color: str | None) -> None:
        for child in self.root.winfo_children():
            for sub in child.winfo_children():
                if isinstance(sub, tk.Label) and sub["textvariable"] is self.status_var:
                    sub.configure(fg=color or MUTED)
                    return

    # ---- 主循环 ----

    def run(self) -> None:
        stop = threading.Event()
        if self.gameflow is not None:
            poller = PhasePoller(self.gameflow)
            threading.Thread(target=poller.run, args=(self.on_state, stop), daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", lambda: (stop.set(), self.root.destroy()))
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()


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
