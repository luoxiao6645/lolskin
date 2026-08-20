# 02 · LCU（League Client Update）API 学习笔记

> 来源：`lcu-bridge.js`（YsnSkin 包内可读脚本）+ 社区文档 + 实测。

## 1. 连接凭据：lockfile

客户端运行时在**客户端根目录**写一个 `lockfile` 文件（无扩展名），格式为 5 个冒号分隔字段：

```
LeagueClient:<PID>:<端口>:<口令>:https
```

HTTPS 请求用 Basic Auth，用户名固定 `riot`，密码为口令，忽略证书校验：

```python
auth = base64("riot:" + token)
GET https://127.0.0.1:<port>/lol-gameflow/v1/gameflow-phase
```

**回退**：lockfile 缺失时，扫描 `LeagueClientUx*.log` 日志中的 `--app-port=` 与
`--remoting-auth-token=` 参数（lcu-bridge.js 的实现，最多查最近 40 个日志文件）。

## 2. 关键端点

| 端点 | 用途 |
|---|---|
| `GET /lol-gameflow/v1/gameflow-phase` | 当前阶段：`None`/`Lobby`/`ChampSelect`/`InProgress`/`GameStart`... |
| `GET /lol-champ-select/v1/session` | 选人会话：`myTeam[].cellId`、`localPlayerCellId`、`championId`、`selectedSkinId` |
| `PATCH /lol-champ-select/v1/session` | 修改自己的选择：`{"localPlayerCellId": N, "selectedSkinId": M}` |
| `GET /lol-game-data/assets/v1/skins.json` | 全量皮肤目录（本项目用发布包内的 `data/skins.json` 样本） |
| `GET /lol-game-data/assets/<path>` | 从运行中的客户端拉取任何游戏资源（皮肤预览图等） |

## 3. 选人阶段换肤的状态机（对应 champion-select.js 的协议消息）

```
用户点击皮肤卡 → skin.switch.request {skinNumber, chromaId}
  → 服务端构建覆盖 WAD（Queued→Building→Applying）
  → 进度 skin.switch.progress 推回界面
  → 完成 Ready → LCU PATCH 选中该皮肤（让客户端 UI/语音/加载框同步）
```

关键细节（champion-select.js 注释中写明）：

- 快速连点时**以最后一次选择为准**，旧请求通过"代数"（generation/switchToken）作废；
- 炫彩的 selectionId = `championKey * 1000 + skinNumber`（如 Varus 的 110057），
  普通皮肤 = 轮播父皮肤编号；后端进度消息用 selectionId 匹配在途目标；
- 进入游戏后（阶段 gamestart/inprogress/reconnect）不再构建，选人阶段尽早构建；
- 客户端 UI 每次重建（DOM 重建）都要重挂界面与重查状态。

## 4. 皮肤 ID 编码（本项目 catalog.py 的依据）

```
skinId = championId * 1000 + skinNum        （例：安妮基础皮肤 1*1000+0 = 1000）
championId = skinId // 1000
skinNum    = skinId % 1000
```

`data/skins.json` 以 skinId 为键（本包 2103 条），`data/champion-summary.json`
以英雄为记录（174 个）。两者通过上面的编码关联。
