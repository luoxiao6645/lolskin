# 开发交接文档 · YsnSkin-Learn（第一次开发结束）

> 用途：为第二次开发提供完整上下文。本会话结束后上下文会丢失，
> 本文件 + `docs/01~06` 是恢复开发所需的一切。
> 最后更新：第一次开发收尾（2026-08-21）。

---

## 1. 项目目标

仿照 YsnSkin 的架构（LCU 选择层 + 覆盖 WAD 构建层 + 补丁器注入层 + 悬浮窗 UI），
**复用 ltk 开源生态的现成组件**，快速实现个人可用的《英雄联盟》换肤工具（非商业）。

技术路线（已定型）：
```
悬浮窗/CLI 选皮肤 → modgen 提取 skinN.bin 生成 skin0 覆盖 mod
  → learn-overlay（Rust CLI，复用 crates.io ltk_overlay 0.5.2 引擎）
  → ltk_patcher_host 官方补丁器注入（CreateFileA 重定向）
  → LCU PATCH 同步客户端选择
```

核心原理：游戏 WAD 内含全部皮肤资源（含未拥有）。把 `skinN.bin` 原样作为
`skin0.bin` 的覆盖（链接保持指向 SkinN 资源），游戏加载皮肤0时按 SkinN 的
完整对象图加载。**不需要解析/改写 PROP**。

## 2. 完成状态总览

| 模块 | 文件 | 状态 |
|---|---|---|
| LCU 集成 | `ysnskin_learn/lcu.py` `endpoints.py` | ✅ 测试通过，真实日志验证 |
| 皮肤目录 | `ysnskin_learn/catalog.py` `data/` | ✅ 2103 皮肤/174 英雄 |
| 哈希 | `ysnskin_learn/hashing.py` | ✅ xxh64 纯 Python，2000 向量对照 |
| WAD 解析 | `ysnskin_learn/wad.py` | ✅ 真实 Ahri.wad.client（6070 条目）验证 |
| 哈希表 | `ysnskin_learn/lhdb.py` + `data/hashes/` | ✅ 哈希→路径解析 |
| mod 生成 | `ysnskin_learn/modgen.py` | ✅ 真实提取验证（skin1.bin=18484B 正确） |
| 构建引擎 | `learn-overlay/`（Rust） | 🔶 **编译成功；wads_built=0 bug 未修（见 §5）** |
| 补丁器驱动 | `ysnskin_learn/patcher.py` | ✅ 协议黑盒测试；实机注入未验证 |
| 编排层 | `ysnskin_learn/overlay.py` | ✅ |
| CLI 换肤 | `tools/skin_swap.py` | ✅ 代码完成 |
| 悬浮窗 | `ysnskin_learn/ui/float_window.py` `tools/floater.py` | ✅ 代码完成；UI 未实机运行 |
| 验证工具 | `tools/verify_build.py` `tools/wad_inspect.py` `tools/lcu_probe.py` | ✅ |
| 文档 | `docs/01~06` | ✅ |
| 测试 | `tests/`（28 个） | ✅ 全过 |

**整体评估：组件 ~90%，端到端可用 ~65%**。最大风险：注入+游戏内效果未实机验证。

## 3. 环境与工具链（第二次开发必备）

| 项 | 值 |
|---|---|
| 项目根 | `E:\下载\YsnSkin-Learn` |
| 游戏目录 | `E:\Program Files (x86)\英雄联盟(26)`（客户端根，LCU lockfile 在 `LeagueClient\`） |
| 游戏数据 | `E:\Program Files (x86)\英雄联盟(26)\Game\DATA\FINAL\` |
| Python | 3.11，`pip install zstandard xxhash`（已装） |
| Rust | `rustup toolchain stable-x86_64-pc-windows-gnu`（**必须 GNU 链**，MSVC 链无 link.exe） |
| C 工具链 | `C:\w64devkit\w64devkit\bin`（gcc/ar/dlltool；**ld 不支持中文路径**） |
| 构建产物 | **`C:\ltk-target\release\learn-overlay.exe`**（因中文路径问题，target 重定向到 ASCII 盘） |
| zig | `C:\zig\zig-x86_64-windows-0.16.0\zig.exe`（备用，已弃用） |
| 补丁器 | `vendor/ltk_patcher_host.exe` + `ltk_patcher_dll.dll`（官方 v1.13.3，LTK Patcher License） |
| 哈希表 | `data/hashes/game-2026-08-14.lhdb` 等（50MB，gitignore，可再下载） |
| 参考源码 | `reference/`（league-mod、ltk-manager、wadtools、lol-meta-wiki、mimir 浅克隆） |
| cargo registry | `C:\Users\13485\.cargo\registry\src\index.crates.io-1949cf8c6b5b557f\ltk_overlay-0.5.2\`（API 权威来源） |

### 编译命令（learn-overlay）
```powershell
$env:Path = "C:\Users\13485\.cargo\bin;C:\w64devkit\w64devkit\bin;" + $env:Path
$env:CC_x86_64_pc_windows_gnu = "C:\w64devkit\w64devkit\bin\gcc.exe"
$env:AR_x86_64_pc_windows_gnu = "C:\w64devkit\w64devkit\bin\ar.exe"
cd E:\下载\YsnSkin-Learn\learn-overlay
cargo build --release   # 产物在 C:\ltk-target\release\
```

### 踩坑记录（勿重踩）
1. rustup MSVC 链缺 link.exe → 用 GNU 链；
2. WinLibs（winget）安装成功但目录为空 → 弃用；
3. zig 链接报 `msvcrt not found`（0.17-dev）→ 0.16.0 可编译 C 但 Rust 链接仍缺 msvcrt → 弃用；
4. w64devkit 是 dwarf 异常模型，无 libgcc_eh.a → 已在
   `C:\w64devkit\w64devkit\lib\gcc\x86_64-w64-mingw32\16.2.0\libgcc_eh.a` 建空库（ar crs）；
5. **MinGW ld 无法处理含中文的路径** → target-dir 必须 ASCII
   （`learn-overlay\.cargo\config.toml` 已配置 `target-dir = "C:\\ltk-target"`）；
6. clap 需 `features=["derive"]`；`EnabledMod` 0.5.2 无 `content_fingerprint` 字段；
7. mod.config.json：`authors` 是**字符串数组**、字段名 **snake_case**（display_name）；
8. mod 内 WAD 目录名 = 游戏 WAD **文件名**（`Ahri.wad.client`），不是 `Champions.wad.client`。

## 4. ltk_overlay 0.5.2 关键 API（已确认）

```rust
// mod 目录布局（FsModContent）：
//   mod.config.json
//   content/base/<WAD名>.wad.client/<相对路径>/<文件>
let mut builder = OverlayBuilder::new(game_dir.into(), overlay_root.into(), state_dir.into());
builder.set_enabled_mods(vec![EnabledMod {
    id: "skin-swap".into(), content: Box::new(FsModContent::new(mod_dir.into())), enabled_layers: None,
}]);
let result = builder.build()?;   // OverlayBuildResult { overlay_root, wads_built, wads_reused, ... }
```

- build() 全同步（无需 tokio）；game_index 缓存在 state_dir/game_index.bin；
- 覆盖文件按 chunk-hash 路由到真实 WAD（"unknown name matched by chunk-hash"）；
- 内置 linked-bin 依赖检查（collect_linked_bin_offenders）；
- `build()` 在 enabled_mods 为空时返回 OK + 0 WAD（**这正是当前怀疑点之一，见 §5**）。

## 5. 当前卡点：wads_built=0（✅ 已修复）

**现象**：`learn-overlay build` 返回 OK，但 `wads_built=0 wads_reused=0`；
`verify_build ahri 1` 报"覆盖 WAD 数量: 0"。

**根因（已定位并修复）**：ltk_overlay 0.5.2 的 `collect_single_mod_metadata`
直接遍历 `project.layers`（来自 mod.config.json）；缺省 `layers` 字段时
serde 给空数组，**注释中"默认 base 层"的约定在 0.5.2 并未实现** → 收集到
0 个覆盖文件（`override_meta.bin` 仅 93 字节为证）。

**修复**：`modgen.py` 的 mod.config.json 显式声明
`"layers": [{"name": "base", "priority": 0}]`（ModProjectLayer 的
name/priority 均无 serde default）。

**验证（2026-08-21 第二次开发）**：`tools/verify_build.py` 对
ahri skin1/skin7/skin52、lux skin7 全部通过（覆盖 WAD 中 skin0.bin 内容
与原始 skinN.bin 逐字节一致）；`skin_swap --build-only` CLI 全链路正常；
28 个 unittest 全过。提交 `748827f`。

**调试经验**：给 learn-overlay 加 tracing-subscriber（`RUST_LOG=ltk_overlay=debug`
可看到 collect 阶段 "Collected 0 unique override metadata entries"）；状态
目录里的 `overlay.json`/`override_meta.bin` 是判断收集是否成功的快速指标。

## 6. 第二次开发任务清单（按优先级）

- [x] **P0** 修复 wads_built=0 → `verify_build ahri 1` 全绿（2026-08-21 完成）
- [x] **P0** `skin_swap --build-only` 构建链全通
- [ ] **P1** 实机验证（需用户配合：启动游戏 → 训练模式/选人阶段）：
      `python -m tools.skin_swap ahri 7` 或 `python -m tools.floater`
      → 观察补丁器状态（injecting→injected）→ 游戏内确认换肤生效
- [ ] **P1** 若 skinN.bin 整体替换在实机无效（Multi_Skins 分桶问题）：
      备选方案 A：mod 同时覆盖 `Animations/SkinN.bin` 链接的 bin；
      备选方案 B：PROP 字符串级改写（需要 ltk 生态之外的工作，量级跳升）；
      备选方案 C：接受局限（只换模型纹理，不做特效）
- [ ] **P2** 悬浮窗实机调试（`tools/floater.py`）
- [ ] **P2** README/docs 最终更新 + git 提交收尾
- [ ] **P3** 风险验证：ACE 反作弊环境下注入是否触发异常（用户自担风险）

## 7. 命令速查

```powershell
# 测试
python -m unittest discover -s tests
# 端到端构建验证（无需游戏运行）
python -m tools.verify_build ahri 1
# 只构建（不注入）
python -m tools.skin_swap --build-only ahri 7
# 完整换肤（需游戏运行，进选人阶段后）
python -m tools.skin_swap ahri 7
# 悬浮窗
python -m tools.floater
# WAD 检查 + 哈希解析
python -m tools.wad_inspect "E:\Program Files (x86)\英雄联盟(26)\Game\DATA\FINAL\Champions\Ahri.wad.client" --hashtable=data\hashes\game-2026-08-14.lhdb --list=data/characters/ahri
# LCU 探测
python -m tools.lcu_probe
```

## 8. 风险与注意事项

- **ACE 反作弊**：游戏目录含 AntiCheatExpert；注入类工具在国服可能触发异常/封号，个人使用自担风险；建议先用训练模式/自定义验证；
- 首次使用前必须完成构建（选人阶段尽早），进游戏后构建无意义；
- 特殊皮肤（元素女皇、Viego 等）不做适配；
- vendor 补丁器受 LTK Patcher License 约束（个人使用 OK，分发需去签名换签）。
