# 01 · 总架构与组件对应
> 所有结论都可在包内文件或开源参考仓库中查证。

## 1. 换肤的本质

英雄联盟的皮肤数据（**包括未拥有的皮肤**）完整存放在本机游戏目录的
`DATA/FINAL/Champions/<英雄>.wad.client` 等 WAD 文件中。游戏按皮肤编号
`SkinN` 加载对应条目（bin / 模型 / 动画 / 粒子）。

YsnSkin 的做法（与开源 cslol 系一脉相承）：
**不改游戏文件、不改内存对象，而是让游戏加载"假 Skin0"**：

1. **构建层**：读取目标皮肤 SkinN 的全部资源，生成一个"覆盖 WAD"（overlay WAD），
   其中的 `data/characters/<英雄>/skins/skin0.bin` 等条目被改写为指向 SkinN 的资源；
2. **注入层**：在游戏进程内挂钩 `CreateFileA`（IAT 钩子），把游戏对
   `*.wad.client` 的打开操作重定向到覆盖 WAD；
3. **完整性层**：改写 OpenSSL `CRYPTO_free` 指针，绕过 Riot 对 WAD 的签名校验；
4. **选择层**：LCU（League Client Update API）让客户端"以为自己选了 SkinN"，
   客户端 UI / 语音 / 加载框随之变为目标皮肤。

```
游戏进程读取 Skin0 → CreateFileA 被重定向 → 读到覆盖 WAD 的 Skin0
                   → Skin0.bin 内的引用指向 SkinN 的资源 → 显示目标皮肤
```

## 2. 分层架构

```
┌─ 选择层 ──────────────────────────────────────────────────────┐
│
│ 本项目：tkinter 悬浮窗（模式一）                               │
└──────────────┬────────────────────────────────────────────────┘
               │ LCU HTTPS（lockfile 凭据）
┌──────────────▼────────────────────────────────────────────────┐         │
│ 本项目：patcher.py 驱动 + 简单状态机（无授权）                 │
└──────────────┬────────────────────────────────────────────────┘
               │ 子进程 + 管道
┌──────────────▼────────────────────────────────────────────────┐
 本项目：wad.py + prop.py + overlay.py（自写 Python 实现）      │
└──────────────┬────────────────────────────────────────────────┘
               │ 命令行 + 命名管道
┌──────────────▼────────────────────────────────────────────────┐
│                        │
│ 本项目：直接使用官方补丁器（vendor/，LTK Patcher License）     │
└───────────────────────────────────────────────────────────────┘
```

## 3. 关键逆向结论（证据位置）

| 结论 | 证据 |
|---|---|
| 换肤 = 覆盖 WAD + 文件重定向 | `ltk_patcher_dll.dll` 字符串：`patched CreateFileA` / `redirected wad:` / `overlay-hook-installed` / `champion-wad-redirected` |
| 绕过校验 = CRYPTO_free 钩子 | 同上：`patched CRYPTO_free`（hooks::trust 模块） |
| 注入方式 = SetWindowsHookEx | `ltk_patcher_host.exe` 导入表：SetWindowsHookExW / UnhookWindowsHookEx；日志：`scanning for game` → `game found; hook installed` |
| 宿主协议 = stdin/stdout 行协议 | `runoverlay` 命令实测（见 docs/04）；C# 侧字符串 `rd-runoverlay stdout=` |
| 构建引擎 CLI | `rift-overlay.exe` 字符串：完整 clap 帮助文本（skin-overlay / classic-overlay / delta-pack / authorize / catalog-audit ...） |
| 授权模型 | `authorize` 子命令 + `--entitlement TICKET --device-id DEVICE`；票据 = RSA 签名 + 设备绑定 + 引擎代数 + 时钟校验（>10 分钟拒绝） |
| LCU 集成 | `lcu-bridge.js`（完整可读）：lockfile 解析、`/lol-game-data/assets/` 拉资源、`/lol-gameflow/v1/gameflow-phase`、`/lol-champ-select/v1/session` |
| 特殊皮肤 | VALIDATION.json 的 52 项兼容能力清单；引擎内 Lux/Viego/Gnar/Rumble/Mordekaiser 等特判逻辑 |
| 血统 | 补丁器与官方 ltk-manager v1.13.3 同尺寸（1,237,408 / 1,013,152 字节），哈希不同 → 同一源码自建签名（VALIDATION: nativeSource=source-build） |

## 4. 开源可复用资产

| 资产 | 用途 | 许可 |
|---|---|---|
| [ltk-manager](https://github.com/LeagueToolkit/ltk-manager) | 补丁器二进制 + Rust 驱动源码（patcher/host/protocol.rs） | MIT/Apache-2.0 + LTK Patcher License |
| [league-mod](https://github.com/LeagueToolkit/league-mod) | ltk_overlay（覆盖 WAD 构建）、ltk_modpkg、格式工具 | MIT/Apache-2.0 |
| [wadtools](https://github.com/LeagueToolkit/wadtools) | WAD 高性能工具 + 哈希表 | MIT |
| [lol-meta-wiki](https://github.com/LeagueToolkit/lol-meta-wiki) | PROP bin 结构文档 | MIT |

## 5. 本项目的取舍

- **注入层直接复用官方补丁器**：个人学习不需要重写注入器；驱动它的协议本身就是学习内容；
- **构建层自己实现**：WAD 解析、PROP 解析、skin0 改写是换肤的核心知识，也是本项目的主要学习目标；
- **不做**：授权服务器、设备绑定、反破解、特殊皮肤全量适配（记录原理，不做实现）。
