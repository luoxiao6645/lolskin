# 03 · WAD v3.4 文件格式笔记

> 来源：`ltk_wad-0.3.0` crate 源码（crates.io）+ `ltk_overlay` 的 `wad_builder.rs`。
> 本项目 `ysnskin_learn/wad.py` 按本笔记实现。

## 1. 总体布局

```
┌─ 文件头（8 字节）────────────────────────┐
│ magic u16 LE = 0x5752 ("RW")             │
│ major u8 = 3                             │
│ minor u8 = 4                             │
├─ 签名区 ─────────────────────────────────┤
│ signature [u8; 256]（v3 = PKCS#1 RSA 签名）│
│ checksum u64 LE                          │
├─ 块表 ───────────────────────────────────┤
│ chunk_count i32 LE                       │
│ TOC 条目 × chunk_count（每条 32 字节）     │
├─ 数据区 ─────────────────────────────────┤
│ chunk 原始字节（按 TOC 的 data_offset）    │
└──────────────────────────────────────────┘
```

v3.4 的 TOC 紧跟文件头之后（无独立偏移字段）；v1/v2 有 2+2 字节的 toc 偏移/大小字段。

## 2. TOC 条目（32 字节，小端）

| 偏移 | 大小 | 字段 |
|---|---|---|
| 0 | 8 | `path_hash` u64 —— chunk 路径的 XXH64 |
| 8 | 4 | `data_offset` u32 —— chunk 数据在文件中的偏移 |
| 12 | 4 | `compressed_size` u32 |
| 16 | 4 | `uncompressed_size` u32 |
| 20 | 1 | `type_frame_count`：高 4 位 frame_count，低 4 位压缩类型 |
| 21 | 3 | `start_frame` 24 位（字节序特殊：hi, lo, mi） |
| 24 | 8 | `checksum` u64 —— 压缩后数据的 XXH3-64 |

压缩类型：`0=None 1=GZip 2=Satellite 3=Zstd 4=ZstdMulti`。
v3.4 无 `is_duplicated` 字段（恒为 false）。

## 3. 路径哈希

```
canonical(path) = path 转小写 + 反斜杠统一为斜杠（如 "DATA\FINAL\..." → "data/final/..."）
path_hash = XXH64(canonical_bytes, seed=0)
```

- WAD 的 TOC 必须按 path_hash **升序排列**（写入时用二分插入维护）；
- `data/final/champions/<英雄>.wad.subchunktoc` 这类伴随文件同样按此哈希参与（构建时需屏蔽，避免覆盖游戏自己的 subchunktoc）；
- 旧版游戏曾用自定义 u32 哈希，现版本（2026）为 u64 XXH64（league-mod 测试确认）。

## 4. 覆盖 WAD 的构建策略（ltk_overlay wad_builder）

1. 挂载源 WAD（游戏原版，例如 `DATA/FINAL/Champions/Annie.wad.client`）；
2. 确定要覆盖/新增的 chunk 哈希集合（覆盖 = 改写现有条目，新增 = 加入新条目）；
3. 合并排序全部 path_hash，写文件头 + 占位 TOC；
4. 逐 chunk 写出：
   - **覆盖条目**：用新数据（理想压缩：bin→zstd，dds→zstd 等）重压缩，checksum = XXH3-64(压缩后数据)；
   - **透传条目**：直接从源 WAD 复制压缩字节（不解压不重压），保留原 checksum；
5. 回填 TOC。

> 关键点：**签名区原样透传**。签名覆盖的是"原始 TOC"，校验方（ltk_sig 的 WadMod
> 记录）可以从覆盖文件恢复 Riot 签名的原始 TOC 出处 —— 这也是注入层能绕过校验的
> 原理基础：**校验通过 → 我们只是加了文件重定向**。

## 5. 本项目实现范围

- [x] 读取：头 + TOC 解析、chunk 解压（None/GZip 用 stdlib，Zstd 需可选依赖 zstandard）
- [ ] 写入：覆盖 WAD 生成（None/Zstd 压缩，TOC 排序回填）
