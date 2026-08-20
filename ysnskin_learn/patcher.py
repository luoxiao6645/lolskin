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
                 elevate: bool = False, debug: bool = False):
        self.overlay_dir = Path(overlay_dir)
        self.patcher_host = Path(patcher_host)
        self.elevate = elevate
        self.debug = debug
        self.proc: subprocess.Popen | None = None
        self._events: list[PatcherEvent] = []
        self._logs: list[str] = []          # stderr 日志行（含 DLL 内部 tracing）
        self._lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._log_reader: threading.Thread | None = None

    # ---- 生命周期 ----

    def start(self) -> None:
        from .diag import error, log

        if not self.patcher_host.is_file():
            raise PatcherError(f"补丁器不存在: {self.patcher_host}")
        if not self.overlay_dir.is_dir():
            raise PatcherError(f"覆盖目录不存在: {self.overlay_dir}")
        if not (self.overlay_dir / "DATA" / "FINAL").is_dir():
            raise PatcherError(
                f"覆盖目录缺少 DATA/FINAL（不是有效的 overlay）: {self.overlay_dir}")
        # 正常模式（对齐 ltk-manager 的 host 驱动）：通过 stdin 行协议配置
        # 注意：不用 runoverlay 兼容模式——它不会发送 config loglevel，
        # 导致 DLL 内部日志被默认级别过滤（实测看不到任何 ltk_patcher_dll:: 日志）。
        args = [str(self.patcher_host)]
        if self.elevate:
            args.append("--elevate")
        if self.debug:
            args.append("--opts")
            args.append("debugpatcher")
        log("C1", "启动补丁器（正常模式）", exe=str(self.patcher_host), elevate=self.elevate,
            overlay=str(self.overlay_dir))
        try:
            self.proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise PatcherError(f"补丁器启动失败: {exc}") from exc
        # UAC 拒绝检测：提权子进程若被拒绝会立即退出
        import time as _time

        _time.sleep(1.5)
        if self.proc.poll() is not None:
            rc = self.proc.returncode
            stderr_tail = ""
            if self.proc.stderr:
                try:
                    stderr_tail = self.proc.stderr.read()[:300]
                except OSError:
                    pass
            self.proc = None
            hint = ("UAC 授权被拒绝或提权失败" if self.elevate
                    else "补丁器异常退出")
            error("C2", "补丁器启动后立即退出", returncode=rc,
                  stderr=stderr_tail.strip())
            raise PatcherError(f"补丁器启动失败（{hint}，code={rc}）")
        # 发送配置序列（对齐 ltk-manager protocol.rs：loglevel=32 debug / flags=0 / prefix）
        log_level = 32 if self.debug else 16
        prefix = str(self.overlay_dir).rstrip("\\/") + "\\"
        commands = (
            f"config loglevel {log_level}\n"
            "config flags 0\n"
            f"config prefix {prefix}\n"
            "start scan\n"
        )
        log("C2", "发送配置", commands=commands.replace("\n", " | "))
        try:
            self.proc.stdin.write(commands)
            self.proc.stdin.flush()
        except OSError as exc:
            raise PatcherError(f"补丁器配置发送失败（stdin 已关闭）: {exc}") from exc
        log("C2", "补丁器进程存活", pid=self.proc.pid)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._log_reader = threading.Thread(target=self._read_log_loop, daemon=True)
        self._log_reader.start()

    def stop(self) -> None:
        """优雅退出：先发 stop 命令，再关 stdin 触发 EOF（正常模式协议）。"""
        if self.proc is not None and self.proc.poll() is None:
            try:
                if self.proc.stdin:
                    self.proc.stdin.write("stop\n")
                    self.proc.stdin.flush()
            except OSError:
                pass
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
        """解析宿主 stdout 行协议：
        - `status <t> <state> <detail>` —— 状态事件
        - `dll <ts> <pid> <tid> <level> <msg>` —— DLL 内部日志（ltk-manager protocol.rs 格式）
        - 其余行保留到 logs 供诊断
        """
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            if line.startswith("status "):
                parts = line.split(" ", 3)
                if len(parts) < 3:
                    continue
                elapsed = float(parts[1]) if len(parts) > 1 else 0.0
                state = parts[2]
                detail = parts[3] if len(parts) > 3 else ""
                with self._lock:
                    self._events.append(PatcherEvent(state, detail, elapsed))
            else:
                # dll 日志与其他 stdout 行全部保留（DLL 内部 tracing 走这里）
                with self._lock:
                    self._logs.append(line)

    @property
    def dll_logs(self) -> list[str]:
        """仅 DLL 内部日志（dll <ts> <pid> <tid> <level> <msg>）。"""
        with self._lock:
            return [ln for ln in self._logs if ln.startswith("dll ")]

    def _read_log_loop(self) -> None:
        """读取 stderr 日志（宿主 + DLL tracing 输出）。"""
        assert self.proc is not None and self.proc.stderr is not None
        for line in self.proc.stderr:
            with self._lock:
                self._logs.append(line.rstrip())

    @property
    def logs(self) -> list[str]:
        with self._lock:
            return list(self._logs)

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
