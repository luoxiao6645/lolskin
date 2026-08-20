# 04 · 补丁器行协议（实测笔记）

> 对象：官方 `ltk_patcher_host.exe` v0.2.1（ltk-manager v1.13.3 发布版，与 YsnSkin
> 内置版同源码自建）。以下全部为实测输出，未运行游戏。

## 1. CLI

```
ltk-patcher injection host: spawned by the UI and driven over a stdin/stdout
line protocol (also accepts the legacy `runoverlay` invocation).

Usage: ltk_patcher_host.exe [OPTIONS] [COMMAND]

Commands:
  runoverlay  Map <overlay> to the config prefix, auto-run `start scan`,
              stop on stdin EOF

Options:
      --elevate      Re-launch elevated (UAC), bridging stdio to the elevated child
      --opts <OPTS>  Injection options blob; only `debugpatcher` is read
      --game <GAME>  Legacy `--game:<path>`; accepted for compatibility, otherwise ignored
```

## 2. runoverlay 模式实测

```
> "start scan" | ltk_patcher_host.exe runoverlay C:\temp\ltk-overlay-test

   0.000032500s  INFO ltk_patcher_host: host starting (runoverlay compat) prefix="C:\\...\\"
   0.001549200s  INFO ltk_patcher_host::worker: session started: scanning for game
status 0.0019711 injecting scanning for game
（stdin EOF → 退出，exit 0）
```

观测结论：

1. **stdout 行协议**：`status <相对秒> <状态> <详情>` —— 状态取值见下；
2. `runoverlay <dir>` 自动执行 `start scan`（把 `<dir>` 作为配置前缀/overlay 目录）；
3. **stdin EOF 即优雅退出**（`stop on stdin EOF`）—— 驱动方只需关闭管道；
4. 未知命令（如 `frobnicate`）**静默忽略**，不报错；
5. 重复 `start scan` 被忽略（会话已启动）；
6. 日志走 stderr，`status` 走 stdout —— 解析协议时应只读 stdout；
7. 未找到游戏时停留在 `scanning for game`，由宿主循环重扫（窗口出现后自动注入）。

## 3. 状态机（来自二进制字符串，映射测试输出）

| 状态 | 详情示例 | 含义 |
|---|---|---|
| `injecting` | `scanning for game` / `game found; hook installed` | 扫描游戏窗口 / 已装钩子 |
| `injected` | `dll attached` | 钩子 DLL 已注入，握手完成 |
| `waiting` | — | 等待游戏退出 |
| `exited` | — | 游戏退出，会话结束 |
| `failed` | `hook install failed` / `dll detached` | 失败 |

内部管道：宿主 ↔ DLL 通过 `\\.\pipe\ltk-patcher-pipe` 通信（`DllMessage::Attach`
协议）；游戏窗口按标题 `League of Legends (TM) Client` 自扫描定位。

## 4. 驱动方式（本项目 patcher.py 的设计）

```python
proc = subprocess.Popen(
    [PATCHER_HOST, "runoverlay", str(overlay_dir)],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
# 逐行读 stdout，解析 "status <t> <state> <detail>"
# 需要停止时 proc.stdin.close() 触发 EOF → 干净退出
# 游戏进程结束时宿主自动退出（可 wait 超时兜底）
```

> 注意：宿主在 `start scan` 后持续运行直到 EOF 或游戏退出；注入需要与游戏同权限
> （管理员游戏需要 `--elevate`，实测无游戏环境未验证）。
