"""补丁器诊断：启动 runoverlay 并实时打印全部 status 事件（无缓冲）。

用法：python -m tools.patcher_diag <overlay目录> [--elevate] [--seconds N]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.patcher import PatcherHost


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("用法: python -m tools.patcher_diag <overlay目录> [--elevate] [--seconds N]")
        return 2
    overlay = Path(args[0])
    elevate = "--elevate" in sys.argv
    seconds = 120
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])

    host = PatcherHost(overlay, elevate=elevate)
    host.start()
    print(f"[diag] 补丁器已启动 overlay={overlay} elevate={elevate}", flush=True)
    deadline = time.monotonic() + seconds
    last_count = 0
    while time.monotonic() < deadline and host.proc is not None and host.proc.poll() is None:
        events = host.events
        for event in events[last_count:]:
            print(f"[status] {event.elapsed_s:.4f}s {event.state} {event.detail}", flush=True)
        last_count = len(events)
        time.sleep(0.5)
    # 尾部输出
    for event in host.events[last_count:]:
        print(f"[status] {event.elapsed_s:.4f}s {event.state} {event.detail}", flush=True)
    rc = host.proc.poll() if host.proc else None
    print(f"[diag] 结束 returncode={rc}", flush=True)
    host.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
