# lol换肤学习项目

一个**学习项目**：基于对项目https://github.com/LeagueToolkit/ltk-manager和项目YsnSkin.用 **Python 3.11（零第三方依赖起步）** 从零实现一个《英雄联盟》换肤工具的原型。

> ⚠️ **声明**：本项目仅用于个人学习与技术研究，**不用于商业用途**。
> 使用第三方工具修改游戏违反 Riot Games / 腾讯的服务条款，存在封号风险，请自行承担后果。
> 本项目与 Riot Games、腾讯、无任何关联。

---

## 为什么做这个项目

学习项目架构（逆向结论，详见 [docs/01-architecture.md](docs/01-architecture.md)）由四层组成：

```
选择层（悬浮窗 / Pengu 插件） → 编排层（C# 客户端 + WebSocket 桥）
     → 构建层（rift-overlay.exe：覆盖 WAD 构建）
     → 注入层（ltk_patcher_host.exe + ltk_patcher_dll.dll：游戏内 WAD 重定向）
```

本项目复刻这条链路，**每一层都自己实现并用文档记录原理**：

|  本项目的实现 | 状态 |
|---|---|---|---|
| 选择层（模式一） | WPF 悬浮窗 + LCU 轮询 | `ui/float_window.py` tkinter 悬浮窗 + `tools/floater.py` | ✅ |
| LCU 集成 | C# HttpClient + lockfile | `ysnskin_learn/lcu.py` + `endpoints.py` | ✅ |
| 皮肤目录 | data/skins.json（游戏目录数据） | `ysnskin_learn/catalog.py` + `data/` | ✅ |
| WAD 解析/哈希表 | rift-overlay.exe（Rust，闭源） | `ysnskin_learn/hashing.py` + `lhdb.py` + `wad.py` + `tools/wad_inspect.py` | ✅（真实游戏文件验证） |
| 覆盖 WAD 构建 | rift-overlay.exe（Rust，闭源） | `learn-overlay/`（Rust CLI，复用 crates.io 的 ltk_overlay，与 ltk-manager 同款引擎） | ✅ |
| 补丁器驱动 | 子进程 + 行协议 | `ysnskin_learn/patcher.py`（驱动官方补丁器） | ✅ |
| mod 生成（skinN→skin0） | entry-alias（闭源） | `ysnskin_learn/modgen.py`（skinN.bin 整体替换） | ✅ |
| 编排层 | C# 状态机 | `ysnskin_learn/overlay.py` + `tools/skin_swap.py` | ✅ |
| 特殊皮肤适配 | 52 项能力（闭源） | 不做全量适配（简单皮肤先行） | 记录 |

关键技术细节全部来自官方开源项目（ltk-manager / league-mod / wadtools）的逆向与阅读)。

## 快速开始

```bash
# 0. 环境：Python 3.11+；可选依赖 zstandard（读压缩 WAD/哈希表）、xxhash（校验）
pip install zstandard xxhash
cd E:\下载\YsnSkin-Learn

# 1. 探测正在运行的英雄联盟客户端（未运行时优雅提示）
python -m tools.lcu_probe

# 2. 检查真实游戏 WAD（本机游戏目录已内置为默认路径）
python -m tools.wad_inspect "E:\Program Files (x86)\英雄联盟(26)\Game\DATA\FINAL\Champions\Ahri.wad.client"

# 3. 用 mimir 哈希表把 WAD 条目解析成路径（需先下载哈希表，见 docs/05）
python -m tools.wad_inspect <wad文件> --hashtable=data\hashes\game-2026-08-14.lhdb --list=data/characters/ahri

# 4. 运行测试
python -m unittest discover -s tests -v
```

## 目录结构

```
YsnSkin-Learn/
├── README.md                     # 本文件
├── docs/                         # 学习笔记（每篇对应一个逆向结论）
│   ├── 01-architecture.md        #   总架构与组件对应
│   ├── 02-lcu-protocol.md        #   LCU API 学习笔记
│   ├── 03-wad-format.md          #   WAD v3.4 格式笔记（来自 ltk_wad 源码）
│   └── 04-patcher-protocol.md    #   补丁器行协议实测笔记
├── ysnskin_learn/                # 核心库
│   ├── hashing.py                #   chunk 路径规范化 + XXH64（纯 Python 实现）
│   ├── lhdb.py                   #   mimir .lhdb 哈希表读取器（哈希→路径）
│   ├── lcu.py                    #   lockfile 发现 + HTTPS 客户端
│   ├── endpoints.py              #   gameflow / champ-select 端点封装
│   ├── catalog.py                #   皮肤目录加载与映射
│   ├── wad.py                    #   WAD v3.4 读取/写入（下一步）
│   ├── prop.py                   #   PROP bin 解析/序列化（下一步）
│   ├── overlay.py                #   skin0→skinN 覆盖构建（下一步）
│   ├── patcher.py                #   ltk_patcher_host 驱动（下一步）
│   └── ui/                       #   tkinter 悬浮窗（规划中）
├── tools/                        # 命令行学习工具
│   ├── lcu_probe.py              #   探测客户端连接与选人状态
│   └── wad_inspect.py            #   WAD 头/TOC/哈希自检/条目路径解析
├── data/                         # 样本数据（来自 YsnSkin 发布包，仅学习用）
│   ├── skins.json                #   2103 条皮肤记录（游戏目录数据）
│   ├── champion-summary.json     #   174 个英雄摘要
│   └── hashes/                   #   mimir 哈希表（可再下载，不入 git）
├── vendor/                       # 官方补丁器二进制（LTK Patcher License，个人使用）
│   ├── ltk_patcher_host.exe
│   ├── ltk_patcher_dll.dll
│   └── LTK-PATCHER-LICENSE.md
├── reference/                    # 开源参考仓库（浅克隆，学习用）
│   ├── wadtools/  lol-meta-wiki/  league-mod/
└── tests/                        # unittest 测试
```

## 路线图

- [x] 逆向分析完成（架构、协议、格式）
- [x] LCU 集成：lockfile + HTTPS + gameflow/champ-select
- [x] 皮肤目录加载
- [x] XXH64 + 路径哈希（2000+ 随机向量对照验证）
- [x] WAD v3.4 TOC 解析（真实 Ahri.wad.client 6070 条目验证）
- [x] mimir 哈希表读取（WAD 哈希 → 真实路径）
- [ ] WAD chunk 解压读取（zstd 可选）与写入
- [ ] PROP bin 解析/序列化
- [ ] 覆盖 WAD 构建（skin0 → skinN 改写，简单皮肤先行）
- [ ] 补丁器驱动（runoverlay + status 解析）
- [ ] tkinter 悬浮窗（模式一）与端到端流程
- [ ] 有游戏环境的实机验证手册

## 许可与归属

- 本项目的代码部分：MIT（学习用途）。
- `vendor/` 下的补丁器二进制：归 [League Toolkit](https://github.com/LeagueToolkit) 所有，受 [LTK Patcher License](vendor/LTK-PATCHER-LICENSE.md) 约束（个人学习使用，不对外分发）。
- `data/` 下的皮肤数据：英雄联盟游戏数据，仅作学习样本。
- 格式与算法参考：ltk_wad、ltk_overlay、wadtools、lol-meta-wiki（均在 `reference/` 可查证）。
