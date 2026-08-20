# 06 · 个人使用手册（快速换肤）

> 仿照 YsnSkin 架构的快速实现：LCU 选择 + 覆盖 WAD + 官方补丁器注入。
> 只支持"普通皮肤"整体替换（skinN.bin → skin0），特殊皮肤（元素女皇、
> Viego 武器等）不做适配。

## 0. 环境要求

| 项 | 要求 |
|---|---|
| 游戏 | 国服客户端 + 完整游戏文件（本机 `E:\Program Files (x86)\英雄联盟(26)`） |
| Python | 3.11+，`pip install zstandard`（解压 zstd chunk） |
| 构建器 | `learn-overlay/target/release/learn-overlay.exe`（`cd learn-overlay && cargo build --release`，需要 Rust + MinGW，见下） |
| 补丁器 | `vendor/ltk_patcher_host.exe` + `ltk_patcher_dll.dll`（官方 v1.13.3，已随仓库提供） |

Rust 构建环境（一次性）：
```
rustup toolchain install stable-x86_64-pc-windows-gnu
# 需要 mingw-w64 工具链（gcc/ar/dlltool）：本机用 C:\w64devkit（w64devkit\bin 加入 PATH）
```

## 1. 快速开始

```bash
# 命令行换肤（推荐先验证）
python -m tools.skin_swap ahri 7                # 阿狸 → 皮肤7
python -m tools.skin_swap --build-only ahri 7   # 只构建（不注入，先验证构建链）

# 悬浮窗模式（选人阶段自动跟随英雄）
python -m tools.floater

# 端到端构建验证（无需游戏运行）
python -m tools.verify_build ahri 1
```

## 2. 使用流程（实战）

1. 启动英雄联盟客户端，进入**英雄选择阶段**；
2. 运行 `python -m tools.skin_swap`（自动读取当前英雄与皮肤）或悬浮窗；
3. 选择目标皮肤 → 工具**立即构建覆盖 WAD**（选人阶段越早越好）；
4. 构建完成后补丁器启动，**等待游戏进程**（进入对局读秒时游戏进程出现，
   补丁器自动注入）；
5. 进游戏后英雄即显示目标皮肤；工具同时 PATCH LCU 让客户端 UI/语音同步。

## 3. 原理（一分钟版）

```
选皮肤 → 提取 skinN.bin（游戏 WAD 中所有皮肤都存在，含未拥有的）
       → 生成 mod：把 skinN.bin 作为 data/.../skins/skin0.bin 的覆盖
       → learn-overlay（ltk_overlay 引擎）构建覆盖 WAD
       → ltk_patcher_host 注入游戏：CreateFileA 重定向
       → 游戏加载 skin0 时实际读到 skinN 的完整配置（模型/纹理/粒子/音效）
```

## 4. 已知限制

- **特殊皮肤**（多形态/专属机制）：可能显示异常，不做适配；
- **首次进游戏前必须完成构建**（进游戏后构建无意义）；
- 换肤在**训练模式/自定义**验证最安全；
- 反作弊（ACE）风险：注入类工具可能被判定异常，**自担风险**；
- 覆盖 WAD 与 LCU 选择的皮肤不一致时（如只 PATCH 不注入），客户端预览
  与游戏内可能不一致——正常使用时两者同步执行。

## 5. 排错

| 现象 | 处理 |
|---|---|
| `LCU 请求失败` | 客户端未启动或 lockfile 过期；先启动客户端 |
| `overlay 构建失败` | 查看 learn-overlay 输出；确认游戏文件完整 |
| 补丁器停在 `scanning for game` | 正常——等游戏进程出现；游戏需与补丁器同权限（管理员） |
| 游戏内没有换肤 | 确认注入时游戏已启动；确认覆盖 WAD 存在（verify_build） |
