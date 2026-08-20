# 05 · mimir .lhdb 哈希表格式笔记

> 来源：`reference/mimir`（LeagueToolkit/mimir 仓库，ltk_hashdb crate）。
> 用途：把 WAD TOC 里的 u64 path_hash 解析回真实路径（wadtools 的哈希表服务）。

## 1. 来源与下载

哈希表由 [LeagueToolkit/mimir](https://github.com/LeagueToolkit/mimir) 定期发布
（如 `hashes-2026-08-14`，game 表 44MB / 229 万条目）：

```
https://github.com/LeagueToolkit/Mimir/releases/download/<tag>/game-<date>.lhdb
```

本项目已下载到 `data/hashes/`（game / lcu / binhashes 三张表，约 50MB，不入 git）。

## 2. 文件布局（80 字节头 + 三个数组 + 字符串池）

```
0..8    magic     b"HASHDB\0\0"
8..10   version   u16 = 1
10      hash_kind u8   1=Xxh64 2=Fnv1a32 3=Xxh3
11      flags     u8   bit0: arena 压缩(zeekstd)  bit1: 哈希前转小写
12      key_width u8   8 = u64 表
13      offset_width u8  4 或 8
16..24  entry_count u64
24..32  keys_offset u64       （升序键数组，二分查找）
32..40  offsets_offset u64
40..48  arena_offset u64      （路径字符串池）
48..56  arena_decompressed_size u64
56..64  arena_compressed_size u64
64..72  checksum u64          （xxh3-64 of keys‖offsets‖lengths‖arena）
```

`lengths` 数组（每条 u16）没有头部字段：紧跟 `offsets` 之后，
位于 `offsets_offset + entry_count × offset_width`。

## 3. 各表算法（hash.rs 确认）

| 表 | hash_kind | 键宽 | 说明 |
|---|---|---|---|
| game / lcu | Xxh64 | u64 | XXH64(小写路径, seed=0)，**与 WAD TOC 的 path_hash 完全一致** |
| binentries / binfields / binhashes / bintypes | Fnv1a32 | u32 | PROP bin 内部哈希（FNV-1a 32，小写），后续 prop.py 要用 |
| rst | Xxh3 / Xxh64 | u64 | RST 字符串表 |

## 4. zeekstd 压缩 arena

- 压缩 = 连续标准 zstd 帧 + 末尾一个 skippable 帧（magic `0x184D2A5E`）承载 seek table；
- 帧头 4 字节是标准 zstd magic `0xFD2FB528`，可整段流式解压（本项目做法）；
- 注意 `zstandard` 的 `decompressobj()` 有 16KB write_size 输出上限，**必须用
  `stream_reader` 循环读取**（实测 12MB 压缩 → 187.8MB 解压，逐字节吻合头部声明）。

## 5. 验证结论（真实数据）

用 `data/hashes/game-2026-08-14.lhdb` 解析 Ahri.wad.client 的 TOC：

- `0x49E643F9C8A74BC7` → `data/characters/ahri/skins/skin0.bin` ✅
- `0xCD6CD409DF1B49B0` → `data/final/champions/ahri.wad.subchunktoc` ✅
- 6070 个条目绝大部分可解析（同目录哈希聚簇，符合注释中的设计假设）

现代皮肤文件布局（Ahri 实测）：

```
data/characters/ahri/skins/skinN.bin          皮肤配置（SkinCharacterDataProperties）
data/characters/ahri/animations/skinN.bin     动画图配置
assets/characters/ahri/skins/skinN/*.tex      皮肤纹理（*_tx_cm.tex）
assets/characters/ahri/skins/skinN/particles/*.tex|*.scb   粒子
assets/characters/ahri/skins/skinN/animations/*.anm        动画片段
```
