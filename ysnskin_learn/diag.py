"""统一诊断日志：时间戳 + 环节标记 + 关键值 + 错误提示。

用法：
    from .diag import log, warn, error
    log("B1", "构建开始", champion="ahri", skin=7)   # -> [HH:MM:SS][B1] 构建开始 champion=ahri skin=7

所有输出同时写 session/diag.log（追加），终端与文件双通道排查。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_LOG_FILE: Path | None = None


def _init() -> None:
    global _LOG_FILE
    if _LOG_FILE is not None:
        return
    try:
        path = Path(__file__).resolve().parent.parent / "session" / "diag.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        _LOG_FILE = open(path, "a", encoding="utf-8")
    except OSError:
        _LOG_FILE = None


def _emit(level: str, tag: str, msg: str) -> None:
    _init()
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}][{level}][{tag}] {msg}"
    print(line, flush=True)
    if _LOG_FILE:
        _LOG_FILE.write(line + "\n")
        _LOG_FILE.flush()


def log(tag: str, msg: str, **kv) -> None:
    extra = " ".join(f"{k}={v}" for k, v in kv.items())
    _emit("INFO", tag, f"{msg} {extra}".rstrip())


def warn(tag: str, msg: str, **kv) -> None:
    extra = " ".join(f"{k}={v}" for k, v in kv.items())
    _emit("WARN", tag, f"{msg} {extra}".rstrip())


def error(tag: str, msg: str, hint: str | None = None, **kv) -> None:
    extra = " ".join(f"{k}={v}" for k, v in kv.items())
    _emit("ERROR", tag, f"{msg} {extra}".rstrip())
    if hint:
        _emit("HINT", tag, f"建议: {hint}")


def section(tag: str, title: str) -> None:
    _emit("====", tag, title)
