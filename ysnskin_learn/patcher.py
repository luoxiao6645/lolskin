"""ltk_patcher_host 驱动（官方补丁器，LTK Patcher License）。

协议实测见 docs/04-patcher-protocol.md：
- ``runoverlay <overlay目录>`` 自动执行 start scan，stdin EOF 即退出
- stdout 输出 ``status <t> <state> <detail>`` 行
- stderr 输出日志（不解析）
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

PATCHER_HOST = Path(__file__).resolve().parent.parent / "vendor" / "ltk_patcher_host.exe"

# 状态机（来自二进制字符串 + 实测）
STATES = ("injecting", "injected", "waiting", "exited", "failed")


@dataclass
class PatcherEvent:
    state: str
    detail: str
    elapsed_s: float


class PatcherError(RuntimeError):
    pass


class PatcherHost:
    """驱动 ltk_patcher_host.exe 的 runoverlay 模式。"""

    def __init__(self, overlay_dir: str | Path, patcher_host: str | Path = PATCHER_HOST,
                 elevate: bool = False):
        self.overlay_dir = Path(overlay_dir)
        self.patcher_host = Path(patcher_host)
        self.elevate = elevate
        self.proc: subprocess.Popen | None = None
        self._events: list[PatcherEvent] = []
        self._lock = threading.Lock()
        self._reader: threading.Thread | None = None

    # ---- 生命周期 ----

    def start(self) -> None:
        if not self.patcher_host.is_file():
            raise PatcherError(f"补丁器不存在: {self.patcher_host}")
        if not self.overlay_dir.is_dir():
            raise PatcherError(f"覆盖目录不存在: {self.overlay_dir}")
        args = [str(self.patcher_host)]
        if self.elevate:
            args.append("--elevate")
        args += ["runoverlay", str(self.overlay_dir)]
        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def stop(self) -> None:
        """优雅退出：关闭 stdin 触发 EOF（实测协议）。"""
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def wait(self, timeout: float = 30.0) -> None:
        if self.proc is None:
            raise PatcherError("补丁器未启动")
        self.proc.wait(timeout=timeout)

    # ---- 事件 ----

    def _read_loop(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line.startswith("status "):
                continue
            parts = line.split(" ", 3)
            if len(parts) < 3:
                continue
            elapsed = float(parts[1]) if len(parts) > 1 else 0.0
            state = parts[2]
            detail = parts[3] if len(parts) > 3 else ""
            with self._lock:
                self._events.append(PatcherEvent(state, detail, elapsed))

    @property
    def events(self) -> list[PatcherEvent]:
        with self._lock:
            return list(self._events)

    @property
    def last_state(self) -> str | None:
        with self._lock:
            return self._events[-1].state if self._events else None

    def wait_for_state(self, state: str, timeout: float = 60.0) -> PatcherEvent:
        """等待指定状态出现（如 injected）。超时抛 PatcherError。"""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                for event in self._events:
                    if event.state == state:
                        return event
            if self.proc is not None and self.proc.poll() is not None:
                raise PatcherError(f"补丁器提前退出（code={self.proc.returncode}），"
                                   f"最后事件: {self.events[-1] if self.events else '无'}")
            time.sleep(0.05)
        raise PatcherError(f"等待状态 {state} 超时；事件列表: {self.events[-5:]}")

    def __enter__(self) -> "PatcherHost":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
