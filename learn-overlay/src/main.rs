// learn-overlay: 把 mod 目录构建为覆盖 WAD（复用 ltk_overlay，与 ltk-manager 同款引擎）。
//
// 用法:
//   learn-overlay build --game-dir <Game目录> --mod-dir <mod目录> \
//       --overlay-root <输出> --state-dir <状态目录>
//
// mod 目录布局（FsModContent）:
//   mod.config.json
//   content/base/<WAD名>.wad.client/<相对路径>/<文件>

use std::path::PathBuf;

use clap::{Parser, Subcommand};
use ltk_overlay::builder::{EnabledMod, OverlayBuilder};
use ltk_overlay::content::FsModContent;

#[derive(Parser)]
#[command(name = "learn-overlay", version, about = "mod 目录 -> 覆盖 WAD（复用 ltk_overlay）")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// 构建覆盖 WAD
    Build {
        /// 英雄联盟 Game 目录（含 DATA/FINAL）
        #[arg(long)]
        game_dir: PathBuf,
        /// mod 目录（含 mod.config.json 与 content/）
        #[arg(long)]
        mod_dir: PathBuf,
        /// 覆盖 WAD 输出目录（patched wads）
        #[arg(long)]
        overlay_root: PathBuf,
        /// 状态目录（game_index 缓存、overlay.json）
        #[arg(long)]
        state_dir: PathBuf,
    },
    /// 对象改名：把 bin 里 path_hash 为 old_path 的对象改名为 new_path。
    /// PROP 只存 path_hash 不存路径字符串；用于 skinN 对象别名到 skin0
    /// （对齐 YsnSkin entry-alias，满足 DLL 的 base-skin 验证 78555f28）。
    BinAlias {
        /// 输入 bin 文件
        input: PathBuf,
        /// 输出 bin 文件
        output: PathBuf,
        /// 旧对象路径（如 characters/lissandra/skins/skin34）
        old_path: String,
        /// 新对象路径（如 characters/lissandra/skins/skin0）
        new_path: String,
    },
    /// 列出 bin 的对象（path_hash 十六进制 + class_hash），供 binhashes 表反查
    BinList {
        /// 输入 bin 文件
        input: PathBuf,
    },
    /// 按映射批量改名对象 + 替换属性引用。
    /// 映射文件每行：`<old_hash_hex> <new_hash_hex>`（对象 path_hash 改名）
    /// 同时把属性值里的 Hash 引用（命中 old）替换为新 hash；
    /// String 引用按前缀规则由 --string-prefix 指定替换。
    BinAliasMap {
        /// 输入 bin 文件
        input: PathBuf,
        /// 输出 bin 文件
        output: PathBuf,
        /// 映射文件（每行 old new，hex u32）
        map: PathBuf,
        /// 可选字符串前缀替换：--string-prefix <old> <new>（可多次）
        #[arg(long = "string-prefix", num_args = 2, action = clap::ArgAction::Append)]
        string_prefixes: Vec<String>,
    },
    /// 同 bin-alias-map，但通过 serde JSON 中转（无字节级误伤风险）：
    /// 对象表 key + path_hash + Hash 属性值 + String 属性值统一精确替换。
    BinEdit {
        /// 输入 bin 文件
        input: PathBuf,
        /// 输出 bin 文件
        output: PathBuf,
        /// 映射文件（每行 old new，hex u32）
        map: PathBuf,
        /// 可选字符串前缀替换：--string-prefix <old> <new>（可多次）
        #[arg(long = "string-prefix", num_args = 2, action = clap::ArgAction::Append)]
        string_prefixes: Vec<String>,
    },
}

fn utf8(p: &PathBuf, what: &str) -> Result<String, String> {
    p.to_str()
        .map(str::to_owned)
        .ok_or_else(|| format!("{what} 不是合法 UTF-8 路径: {}", p.display()))
}

fn main() -> Result<(), String> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();
    let cli = Cli::parse();
    match cli.cmd {
        Cmd::Build {
            game_dir,
            mod_dir,
            overlay_root,
            state_dir,
        } => {
            let game_dir = utf8(&game_dir, "game_dir")?;
            let mod_dir = utf8(&mod_dir, "mod_dir")?;
            let overlay_root = utf8(&overlay_root, "overlay_root")?;
            let state_dir = utf8(&state_dir, "state_dir")?;

            let mut builder = OverlayBuilder::new(
                game_dir.clone().into(),
                overlay_root.clone().into(),
                state_dir.into(),
            );
            let content = FsModContent::new(mod_dir.clone().into());
            let enabled = EnabledMod {
                id: "skin-swap".to_string(),
                content: Box::new(content),
                enabled_layers: None,
            };
            builder.set_enabled_mods(vec![enabled]);

            let result = builder
                .build()
                .map_err(|e| format!("overlay 构建失败: {e}"))?;
            println!(
                "OK overlay_root={} wads_built={} wads_reused={} elapsed_ms={}",
                result.overlay_root,
                result.wads_built.len(),
                result.wads_reused.len(),
                result.build_time.as_millis()
            );
            for wad in &result.wads_built {
                println!("built: {}", wad);
            }
            for wad in &result.wads_reused {
                println!("reused: {}", wad);
            }
            Ok(())
        }
        Cmd::BinAlias {
            input,
            output,
            old_path,
            new_path,
        } => bin_alias(&input, &output, &old_path, &new_path),
        Cmd::BinList { input } => bin_list(&input),
        Cmd::BinAliasMap {
            input,
            output,
            map,
            string_prefixes,
        } => bin_alias_map(&input, &output, &map, &string_prefixes),
        Cmd::BinEdit {
            input,
            output,
            map,
            string_prefixes,
        } => bin_edit(&input, &output, &map, &string_prefixes),
    }
}

/// bin-edit：serde JSON 中转的精确别名（对象 key/path_hash/Hash 引用/String 引用）。
fn bin_edit(
    input: &PathBuf,
    output: &PathBuf,
    map: &PathBuf,
    string_prefixes: &[String],
) -> Result<(), String> {
    use std::collections::HashMap;
    use std::fs::File;
    use std::io::BufReader;

    use ltk_meta::property::NoMeta;
    use ltk_meta::Bin;

    // 读取映射
    let map_text = std::fs::read_to_string(map).map_err(|e| format!("读映射失败: {e}"))?;
    let mut hash_map: HashMap<u32, u32> = HashMap::new();
    for (i, line) in map_text.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let mut parts = line.split_whitespace();
        let old = u32::from_str_radix(parts.next().ok_or_else(|| format!("映射第{i}行缺 old"))?, 16)
            .map_err(|e| format!("映射第{i}行 old 非法: {e}"))?;
        let new = u32::from_str_radix(parts.next().ok_or_else(|| format!("映射第{i}行缺 new"))?, 16)
            .map_err(|e| format!("映射第{i}行 new 非法: {e}"))?;
        hash_map.insert(old, new);
    }
    println!("bin-edit: 映射 {} 条", hash_map.len());

    // 解析 → JSON
    let file = File::open(input).map_err(|e| format!("打开输入失败 {input:?}: {e}"))?;
    let bin = Bin::<NoMeta>::from_reader(&mut BufReader::new(file))
        .map_err(|e| format!("解析 bin 失败: {e}"))?;
    let mut json = serde_json::to_value(&bin).map_err(|e| format!("序列化 JSON 失败: {e}"))?;

    // 递归替换
    let mut refs = 0usize;
    let mut renamed = 0usize;
    edit_json_value(&mut json, &hash_map, string_prefixes, &mut refs, &mut renamed);
    println!("bin-edit: 对象改名 {renamed} 个，引用替换 {refs} 处");

    // JSON → Bin → 写出
    let bin2: Bin<NoMeta> =
        serde_json::from_value(json).map_err(|e| format!("JSON 反序列化失败: {e}"))?;
    let mut out = File::create(output).map_err(|e| format!("创建输出失败 {output:?}: {e}"))?;
    bin2.to_writer(&mut out).map_err(|e| format!("写入 bin 失败: {e}"))?;
    println!("OK 已写出 {output:?}");
    Ok(())
}

/// 递归编辑 JSON：
/// - objects map 的 key（BinHash hex 字符串）命中映射 → 换 key
/// - kind=Hash 的属性值（u32 数字）命中 → 替换
/// - kind=String 的属性值按前缀（等长）替换
/// - 其余数字节点若命中映射也替换（path_hash 字段等）
fn edit_json_value(
    v: &mut serde_json::Value,
    hash_map: &std::collections::HashMap<u32, u32>,
    string_prefixes: &[String],
    refs: &mut usize,
    renamed: &mut usize,
) {
    match v {
        serde_json::Value::Object(map) => {
            // PropertyValueEnum 形态: {"kind": "...", "value": ...}
            let is_prop = map.get("kind").and_then(|k| k.as_str()).is_some()
                && map.contains_key("value");
            // 先处理 key（objects 的 BinHash key 是 hex 字符串）
            let keys: Vec<String> = map.keys().cloned().collect();
            for key in keys {
                if let Ok(num) = u32::from_str_radix(&key, 16) {
                    if let Some(&new) = hash_map.get(&num) {
                        let val = map.remove(&key).unwrap();
                        map.insert(format!("{new:08x}"), val);
                        *renamed += 1;
                    }
                }
            }
            if is_prop {
                let kind = map.get("kind").and_then(|k| k.as_str()).unwrap_or("").to_string();
                let value = map.get_mut("value").unwrap();
                if kind == "Hash" {
                    if let Some(num) = value.as_u64() {
                        if let Some(&new) = hash_map.get(&(num as u32)) {
                            *value = serde_json::json!(new);
                            *refs += 1;
                        }
                    }
                }
                // String 及 EmbeddedObjectLink 等含路径字符串的值统一在
                // 下方 String 节点分支处理
            }
            // 递归所有值
            for val in map.values_mut() {
                edit_json_value(val, hash_map, string_prefixes, refs, renamed);
            }
        }
        serde_json::Value::String(s) => {
            // 所有字符串节点（属性值、对象链接路径等）：前缀匹配则替换。
            // 等长替换要求由调用方保证（SkinN→Skin0 均为 5 字符）。
            for pair in string_prefixes.chunks(2) {
                if pair.len() == 2 && s.starts_with(&pair[0]) {
                    *s = format!("{}{}", pair[1], &s[pair[0].len()..]);
                    *refs += 1;
                    break;
                }
            }
        }
        serde_json::Value::Array(arr) => {
            for item in arr.iter_mut() {
                edit_json_value(item, hash_map, string_prefixes, refs, renamed);
            }
        }
        serde_json::Value::Number(n) => {
            if let Some(num) = n.as_u64() {
                if let Some(&new) = hash_map.get(&(num as u32)) {
                    *n = serde_json::Number::from(new);
                    *refs += 1;
                }
            }
        }
        _ => {}
    }
}

/// bin-alias-map：批量对象改名（ltk_meta）+ 属性 Hash 引用字节级替换。
///
/// bin 内对象引用全部是 Hash 值（u32，无字符串引用——已实证），所以：
/// 1) ltk_meta 改名对象表（old→new）
/// 2) 序列化后对字节做 u32 LE 替换（old→new）——对象表里 old 已不存在，
///    替换只命中属性区的引用值，零冲突
fn bin_alias_map(
    input: &PathBuf,
    output: &PathBuf,
    map: &PathBuf,
    string_prefixes: &[String],
) -> Result<(), String> {
    use std::collections::HashMap;
    use std::fs::File;
    use std::io::{BufReader, Write};

    use ltk_hash::BinHash;
    use ltk_meta::property::NoMeta;
    use ltk_meta::Bin;

    // 读取映射
    let map_text = std::fs::read_to_string(map).map_err(|e| format!("读映射失败: {e}"))?;
    let mut hash_map: HashMap<u32, u32> = HashMap::new();
    for (i, line) in map_text.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let mut parts = line.split_whitespace();
        let old = u32::from_str_radix(parts.next().ok_or_else(|| format!("映射第{i}行缺 old"))?, 16)
            .map_err(|e| format!("映射第{i}行 old 非法: {e}"))?;
        let new = u32::from_str_radix(parts.next().ok_or_else(|| format!("映射第{i}行缺 new"))?, 16)
            .map_err(|e| format!("映射第{i}行 new 非法: {e}"))?;
        hash_map.insert(old, new);
    }
    println!("bin-alias-map: 映射 {} 条", hash_map.len());

    // 解析 bin
    let file = File::open(input).map_err(|e| format!("打开输入失败 {input:?}: {e}"))?;
    let mut bin = Bin::<NoMeta>::from_reader(&mut BufReader::new(file))
        .map_err(|e| format!("解析 bin 失败: {e}"))?;

    // 1) 对象改名
    let mut renamed = 0usize;
    let mut objects = std::mem::take(&mut bin.objects);
    let mut new_objects = indexmap::IndexMap::new();
    for (hash, mut obj) in objects {
        if let Some(&new_hash) = hash_map.get(&hash.0) {
            obj.path_hash = BinHash(new_hash);
            new_objects.insert(BinHash(new_hash), obj);
            renamed += 1;
        } else {
            new_objects.insert(hash, obj);
        }
    }
    bin.objects = new_objects;

    // 2) 序列化到内存
    let mut bytes: Vec<u8> = Vec::new();
    {
        let mut cursor = std::io::Cursor::new(&mut bytes);
        bin.to_writer(&mut cursor).map_err(|e| format!("序列化失败: {e}"))?;
    }

    // 3) 字符串前缀替换（PROP String 值 = u16 LE 长度 + UTF-8）。
    //    只替换以 old 开头的字符串（如 Characters/Aatrox/Skins/Skin33 → Skin0，
    //    对象引用）；ASSETS 资源路径不以 Characters/ 开头，不受影响。
    //    要求等长（SkinN→Skin0 均为 5 字符）。
    let mut str_refs = 0usize;
    for pair in string_prefixes.chunks(2) {
        if pair.len() != 2 {
            continue;
        }
        let old = pair[0].as_bytes();
        let new = pair[1].as_bytes();
        if old.is_empty() || old.len() != new.len() {
            continue;
        }
        let mut i = 0usize;
        while i + 2 + old.len() <= bytes.len() {
            let len = u16::from_le_bytes([bytes[i], bytes[i + 1]]) as usize;
            if len >= old.len() && i + 2 + len <= bytes.len()
                && bytes[i + 2..i + 2 + old.len()] == *old
            {
                bytes[i + 2..i + 2 + old.len()].copy_from_slice(new);
                str_refs += 1;
            }
            i += 1;
        }
    }
    println!("bin-alias-map: 字符串引用替换 {str_refs} 处");

    // 4) 字节级 u32 LE 替换（属性区 Hash 引用）
    let mut refs = 0usize;
    for (old, new) in &hash_map {
        let old_bytes = old.to_le_bytes();
        let new_bytes = new.to_le_bytes();
        let mut i = 0;
        while i + 4 <= bytes.len() {
            if bytes[i..i + 4] == old_bytes {
                bytes[i..i + 4].copy_from_slice(&new_bytes);
                refs += 1;
                i += 4;
            } else {
                i += 1;
            }
        }
    }
    println!("bin-alias-map: 对象改名 {renamed} 个，引用替换 {refs} 处");

    // 写出
    let mut out = File::create(output).map_err(|e| format!("创建输出失败 {output:?}: {e}"))?;
    out.write_all(&bytes).map_err(|e| format!("写入失败: {e}"))?;
    println!("OK 已写出 {output:?}");
    Ok(())
}

/// bin-list：列出对象（path_hash, class_hash, 属性数），供 binhashes 表反查路径。
fn bin_list(input: &PathBuf) -> Result<(), String> {
    use std::fs::File;
    use std::io::BufReader;

    use ltk_meta::property::NoMeta;
    use ltk_meta::Bin;

    let file = File::open(input).map_err(|e| format!("打开输入失败 {input:?}: {e}"))?;
    let bin = Bin::<NoMeta>::from_reader(&mut BufReader::new(file))
        .map_err(|e| format!("解析 bin 失败: {e}"))?;
    println!("dependencies: {}", bin.dependencies.len());
    for d in &bin.dependencies {
        println!("  dep: {d}");
    }
    for (hash, obj) in bin.iter() {
        println!("object {:08x} class={:08x} props={}", hash.0, obj.class_hash.0,
                 obj.properties.len());
    }
    Ok(())
}

/// bin-alias：把对象的 path_hash 从 old_path 改为 new_path（内容不变）。
fn bin_alias(input: &PathBuf, output: &PathBuf, old_path: &str, new_path: &str) -> Result<(), String> {
    use std::fs::File;
    use std::io::BufReader;

    use ltk_hash::{BinHash, Hash};
    use ltk_meta::property::NoMeta;
    use ltk_meta::Bin;

    let old_hash = BinHash::hash_str(old_path);
    let new_hash = BinHash::hash_str(new_path);
    println!("bin-alias: {old_path} ({old_hash:x}) -> {new_path} ({new_hash:x})");

    let file = File::open(input).map_err(|e| format!("打开输入失败 {input:?}: {e}"))?;
    let mut bin = Bin::<NoMeta>::from_reader(&mut BufReader::new(file))
        .map_err(|e| format!("解析 bin 失败: {e}"))?;

    let obj = bin
        .remove_object(old_hash)
        .ok_or_else(|| format!("对象 {old_hash:x} ({old_path}) 不存在（共 {} 个对象）", bin.len()))?;
    println!("找到对象: class={:08x} properties={}", obj.class_hash, obj.properties.len());

    let mut renamed = obj;
    renamed.path_hash = new_hash;
    bin.add_object(renamed);

    let mut out = File::create(output).map_err(|e| format!("创建输出失败 {output:?}: {e}"))?;
    bin.to_writer(&mut out).map_err(|e| format!("写入 bin 失败: {e}"))?;
    println!("OK 已写出 {output:?}，对象数={}", bin.len());
    Ok(())
}
