"""LCU（League Client Update）连接层。

对应 YsnSkin 的 ``lcu-bridge.js``：负责发现客户端连接凭据（lockfile，回退
日志扫描），并提供带 Basic Auth 的 HTTPS 客户端。

学习笔记见 docs/02-lcu-protocol.md。
"""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

LOCKFILE_FIELDS = 5
LOG_PORT_RE = re.compile(r"--app-port=(\d+)")
LOG_TOKEN_RE = re.compile(r"--remoting-auth-token=([^\s]+)")
UX_LOG_NAME_RE = re.compile(r"LeagueClientUx.*\.log$", re.IGNORECASE)


class LcuError(RuntimeError):
    """LCU 连接或请求错误。"""


@dataclass(frozen=True)
class Lockfile:
    """lockfile 解析结果（5 个冒号分隔字段）。"""

    process_name: str
    pid: int
    port: int
    token: str
    protocol: str

    @property
    def is_stale(self) -> bool:
        """端口或进程无效时视为过期（客户端重启/退出后的残留文件）。"""
        return self.port <= 0 or not self.token or not _process_alive(self.pid)


def read_lockfile(path: Path) -> Lockfile | None:
    """解析 lockfile；格式不对返回 None（不抛异常）。"""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    fields = text.split(":")
    if len(fields) != LOCKFILE_FIELDS:
        return None
    try:
        return Lockfile(
            process_name=fields[0],
            pid=int(fields[1]),
            port=int(fields[2]),
            token=fields[3],
            protocol=fields[4],
        )
    except ValueError:
        return None


def find_lockfile(client_root: str | Path) -> Path | None:
    """在客户端根目录与 LeagueClient 子目录中查找 lockfile（同 lcu-bridge.js）。"""
    root = Path(client_root)
    for candidate in (root / "lockfile", root / "LeagueClient" / "lockfile"):
        if candidate.is_file():
            return candidate
    return None


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # Windows 上对存在的进程不抛异常
        return True
    except OSError:
        return False


def _scan_ux_logs(client_root: str | Path, limit: int = 40) -> Lockfile | None:
    """回退：从 LeagueClientUx*.log 头部提取 --app-port 与 --remoting-auth-token。

    与 lcu-bridge.js 的 findCredentials 回退路径一致，按 mtime 取最近 limit 个。
    """
    root = Path(client_root)
    roots = [
        (root, False),
        (root / "LeagueClient", True),
        (root / "Logs", True),
    ]
    logs: list[tuple[Path, float]] = []
    for directory, recursive in roots:
        if not directory.is_dir():
            continue
        for entry in directory.rglob("*") if recursive else directory.iterdir():
            if entry.is_file() and UX_LOG_NAME_RE.search(entry.name):
                try:
                    logs.append((entry, entry.stat().st_mtime))
                except OSError:
                    continue
    logs.sort(key=lambda item: item[1], reverse=True)
    for log, _ in logs[:limit]:
        try:
            head = log.read_bytes()[:65536].decode("utf-8", errors="replace")
        except OSError:
            continue
        port_match = LOG_PORT_RE.search(head)
        token_match = LOG_TOKEN_RE.search(head)
        if port_match and token_match:
            return Lockfile(
                process_name="LeagueClient",
                pid=0,
                port=int(port_match.group(1)),
                token=token_match.group(1),
                protocol="https",
            )
    return None


def discover(client_root: str | Path) -> Lockfile:
    """发现客户端凭据：lockfile 优先，日志扫描回退；都失败抛 LcuError。"""
    lockfile_path = find_lockfile(client_root)
    if lockfile_path:
        lockfile = read_lockfile(lockfile_path)
        if lockfile and not lockfile.is_stale:
            return lockfile
    from_log = _scan_ux_logs(client_root)
    if from_log:
        return from_log
    raise LcuError(f"未找到客户端连接凭据（{client_root}）——请先启动英雄联盟客户端")


class RiotClient:
    """对 LCU HTTPS 端点的最小客户端（Basic Auth，忽略证书）。"""

    def __init__(self, lockfile: Lockfile, timeout: float = 6.0):
        self.lockfile = lockfile
        self.timeout = timeout
        self._ssl_ctx = ssl._create_unverified_context()
        self._auth = "Basic " + base64.b64encode(
            f"riot:{lockfile.token}".encode("utf-8")
        ).decode("ascii")

    def request(self, method: str, path: str, body: dict | None = None):
        url = f"https://127.0.0.1:{self.lockfile.port}{path}"
        data = None
        headers = {"Authorization": self._auth}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl_ctx) as resp:
                raw = resp.read()
                return resp.status, raw
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except OSError as exc:
            raise LcuError(f"LCU 请求失败 {method} {path}: {exc}") from exc

    def get_json(self, path: str):
        status, raw = self.request("GET", path)
        if status != 200:
            raise LcuError(f"GET {path}: HTTP {status}")
        return json.loads(raw.decode("utf-8"))

    def patch_json(self, path: str, body: dict):
        status, raw = self.request("PATCH", path, body)
        if status not in (200, 201, 204):
            raise LcuError(f"PATCH {path}: HTTP {status} {raw[:200]!r}")
        return json.loads(raw.decode("utf-8")) if raw else None
