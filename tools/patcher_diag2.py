"""补丁器完整诊断：status 事件 + stderr 日志全量实时打印。

用法：python -m tools.patcher_diag2 <overlay目录> [--elevate] [--seconds N]
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PATCHER_HOST = PROJECT_ROOT / "vendor" / "ltk_patcher_host.exe"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("用法: python -m tools.patcher_diag2 <overlay目录> [--elevate] [--seconds N]")
        return 2
    overlay = Path(args[0])
    elevate = "--elevate" in sys.argv
    seconds = 180
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])

    cmd = [str(PATCHER_HOST)]
    if elevate:
        cmd.append("--elevate")
    cmd += ["runoverlay", str(overlay)]
    print(f"[diag] {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace")

    def read_stream(stream, tag):
        for line in stream:
            print(f"[{tag}] {line.rstrip()}", flush=True)

    threading.Thread(target=read_stream, args=(proc.stdout, "status"), daemon=True).start()
    threading.Thread(target=read_stream, args=(proc.stderr, "log"), daemon=True).start()

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and proc.poll() is None:
        time.sleep(1)
    if proc.poll() is None:
        print(f"[diag] {seconds}s 到，发送 EOF 停止", flush=True)
        try:
            proc.stdin.close()
        except OSError:
            pass
    proc.wait(timeout=10)
    print(f"[diag] 结束 returncode={proc.returncode}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
