# 08 · YsnSkin 完整实现走读（对照修正依据）

> 来源：`YsnSkin-V0.1.50` 发布包内可读代码（pengu-plugin/*.js、lcu-bridge.js、
> pengu-loader README）+ 二进制字符串分析。本文档回答"YsnSkin 到底怎么实现的"，
> 并给出与我们实现的差异对照。

## 1. 进程与通信架构

```
┌─ 游戏客户端进程（LeagueClientUx，Electron/CEF）───────────┐
│  Pengu 插件（version.dll 注入）                              │
│   ├─ index.js          入口：模块装配/卸载                   │
│   ├─ bridge-core.js    WebSocket 桥（连 C# 侧）              │
│   ├─ champion-select.js 选人界面改造（核心，4714 行）         │
│   ├─ settings-flyout.js 设置浮层                             │
│   ├─ nav-icon.js        导航图标                             │
│   └─ beautify/social    生涯美化（可选）                     │
└───────────────┬─────────────────────────────────────────────┘
                │ WebSocket ws://127.0.0.1:50123/ysnskin-bridge/
┌───────────────▼─────────────────────────────────────────────┐
│ C# 客户端（YsnSkin.dll，WPF）                                │
│  ├─ LCU 通信（lockfile + HTTPS，同 lcu-bridge.js 逻辑）      │
│  ├─ 皮肤目录（skins.json 等游戏数据，2103 皮肤）             │
│  ├─ 换肤状态机（Queued→Building→Applying→Ready）            │
│  ├─ 授权（RSA 票据 + 设备绑定，商用护城河）                  │
│  └─ 子进程编排：rift-overlay.exe 构建 → ltk_patcher_host 注入 │
└───────────────┬─────────────────────────────────────────────┘
                │ 命令行 + 命名管道
    ┌───────────▼───────────┐      ┌──────────────────────────┐
    │ rift-overlay.exe      │      │ ltk_patcher_host.exe     │
    │ （构建覆盖 WAD，闭源）  │      │  → ltk_patcher_dll.dll   │
    └───────────────────────┘      │    （注入游戏进程）        │
                                   └──────────────────────────┘
```

**关键认知（修正我们之前的偏差）**：
- **游戏内换肤 = 注入（覆盖 WAD 重定向）**，PATCH LCU 只是让客户端 UI/语音/加载框同步；
- 训练营里 PATCH 无效（选人机制不完整）不影响换肤——**注入链路才是核心**；
- 皮肤列表数据源 = 游戏目录数据（我们已有 catalog，数据源相同）。

## 2. 模式二（内嵌）完整数据流

### 2.1 目录与皮肤列表
```
进入选人阶段 → sync('enter') → 发 champselect.query（WebSocket 桥）
  → C# 侧按 LCU 会话的 championId 过滤目录 → 返回
    { championName, skins: [...], available, classicMode }
  → render() → mountPanel() → fillCards() 渲染皮肤卡片
  兜底：2 秒定时器 + 快速退避 [60,100,160,250,400]ms，任意时刻至多一条查询在途
```

### 2.2 用户点击 → 提交
```
点击皮肤卡 → 事件流（pointerdown/click/transitionend 三重监听）
  → 从 DOM/资源 URL 反推皮肤编号（Skins/Skin0xxx 正则）
  → requestSwitch()：
      selectionId = championKey*1000 + skinNum（炫彩也是这个编码）
      send('skin.switch.request', { skinNumber, chromaId })
  → 本地进入 building 状态（代数 generation 防旧请求）
```

### 2.3 构建与进度（C# 侧状态机）
```
skin.switch.request → C# 侧
  Queued → Building → Applying → Ready（终态还有 Failed/Canceled/Superseded）
  skin.switch.progress 推送（带 operationId + selectionId 身份去重）
  → 构建 Ready 后：启动 ltk_patcher_host runoverlay（rd-runoverlay）
  → 注入游戏进程（SetWindowsHookEx → DLL → CreateFileA 重定向）
```

### 2.4 LCU 同步（客户端 UI）
```
PATCH /lol-champ-select/v1/session/my-selection { selectedSkinId: selectionId }
  → 失败兜底：PATCH /session/actions/{本地pick actionId}
  （"部分客户端状态只接受对本地玩家 pick action 的更新"）
  1.5 秒 abort 超时
```

## 3. 模式一（独立窗口）—— 基于二进制字符串还原

```
WPF 悬浮窗（companionoverlaywindow.xaml + companiontipwindow.xaml）
  → LCU 轮询：gameflow-phase + champ-select session（250ms，锁文件凭据）
  → 选人阶段显示当前英雄 → 玩家选皮肤
  → 同一套构建/注入链路（rd-runoverlay stdout=）
```

## 4. 与我们实现的差异对照（修正清单）

| 环节 | YsnSkin 做法 | 我们当前 | 差异与修正 |
|---|---|---|---|
| 皮肤列表数据源 | C# 目录 + LCU championId | 本地 catalog + LCU 轮询 | ✅ 数据源相同；**我们的 bug 在 tkinter 跨线程更新 UI**（root.after 从后台线程调用不可靠），需改 queue + 主线程轮询 |
| 英雄检测 | C# 侧 LCU 会话（championId/pickIntent） | 同 | ✅ 一致（训练营 championId=0 取 pickIntent 已处理） |
| 皮肤提交 | skin.switch.request（桥）→ C# 构建 | 本地直接构建 | ✅ 语义相同 |
| 构建状态机 | Queued→Building→Applying→Ready + operationId/selectionId 去重 | 同步构建（无状态机） | 简化可接受；但 **Ready 前不启动补丁器**——YsnSkin 构建完才启动注入（我们一致） |
| 注入时机 | 构建 Ready 后启动 ltk_patcher_host | 同 | ✅ 一致；**未验证环节：DLL 重定向表是否建立**（需 DLL 日志确认） |
| LCU PATCH | my-selection 主 + actions 兜底，1.5s 超时 | 已对齐（my-selection + actions 兜底） | ✅ 已按 YsnSkin 修改；**训练营 PATCH 无效是客户端机制问题，不影响换肤** |
| 换肤生效 | 注入重定向（CreateFileA） | 同 | ⚠️ **当前主攻问题**：注入成功（dll attached）但游戏加载读原版 WAD——需 DLL 日志定位重定向表是否建立 |
| 授权 | RSA 票据 + 设备绑定 | 无 | 个人使用不需要 |
| UI | 客户端内 DOM 改造（模式二）/ WPF（模式一） | tkinter 悬浮窗 | 独立窗口方案可行；先修线程问题 |

## 5. 修正行动计划（按此执行）

1. **修复悬浮窗 UI 线程问题**：queue.Queue + 主线程 `root.after` 轮询消费（tkinter 线程安全模式）；
2. **注入链路定位**：ASCII overlay + 补丁器先就位 + patcher_diag2 全日志（DLL 的
   `WAD scan ok / patched CRYPTO_free / redirected wad` 三步日志），确认重定向表建立；
3. **按 YsnSkin 语义验收**：游戏内换肤成功 = 注入生效（PATCH 只是 UI 同步，训练营
   可测注入效果）；
4. 若重定向表建立但仍无效 → 检查 CreateFileA 钩子是否拦截国服客户端的 WAD 打开
   （国服魔改可能用 CreateFileW/NtCreateFile——这是 ltk 系在 Riot 服有效、国服
   可能失效的差异点，届时需验证 DLL 日志的 "redirected wad" 是否出现）。
