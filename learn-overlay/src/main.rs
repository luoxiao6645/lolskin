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
}

fn utf8(p: &PathBuf, what: &str) -> Result<String, String> {
    p.to_str()
        .map(str::to_owned)
        .ok_or_else(|| format!("{what} 不是合法 UTF-8 路径: {}", p.display()))
}

fn main() -> Result<(), String> {
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
                content_fingerprint: None,
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
    }
}
