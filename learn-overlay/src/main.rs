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
    }
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
