"""皮肤交换 mod 生成器：把目标皮肤 SkinN 的 bin 替换为 Skin0 的覆盖。

原理（仿照 YsnSkin 的 entry-alias，粗粒度版）：
  游戏加载英雄时读取 data/characters/<英雄>/skins/skin0.bin 及其链接的
  bin（动画图 / Multi_Skins 集合）。把 skinN.bin 原样作为 skin0.bin 的
  覆盖放入 mod，其链接保持指向 SkinN 的资源（原版 WAD 中全部存在），
  游戏便会按 SkinN 的完整对象图加载 —— 模型/纹理/粒子/音效随之切换。

产物：ltk 生态的 mod 目录（ltk_overlay::content::FsModContent 兼容）：
  mod.config.json
  content/base/Champions.wad.client/data/characters/<x>/skins/skin0.bin
"""

from __future__ import annotations

import json
from pathlib import Path

from .wad import Wad

DEFAULT_GAME_DIR = Path(r"E:\Program Files (x86)\英雄联盟(26)\Game")


def champion_key(alias: str) -> str:
    """英雄别名转小写（目录名形式，如 'Ahri' -> 'ahri'）。"""
    return alias.lower()


def build_skin_swap_mod(
    wad: Wad,
    champion: str,
    skin_num: int,
    out_mod_dir: str | Path,
    learn_overlay: str | Path | None = None,
) -> Path:
    """提取 skinN.bin，对象别名到 skin0，生成覆盖 mod。

    关键：DLL 的 base-skin 验证要求覆盖后的 skin0.bin 里存在名为
    characters/<x>/skins/skin0 的对象（hash 78555f28 族）。整体替换会丢失该
    对象导致 overlay 被禁用，因此用 bin-alias 把根对象改名（PROP 只存
    path_hash，改一个 u32 即可；内容/依赖/资源引用全部不变）。
    """
    import shutil
    import subprocess
    import tempfile

    src_path = f"data/characters/{champion}/skins/skin{skin_num}.bin"
    data = wad.read_path(src_path)
    if data is None:
        raise FileNotFoundError(f"WAD 中不存在 {src_path}")

    # bin-alias：根对象 characters/<x>/skins/skinN -> skin0
    old_path = f"characters/{champion}/skins/skin{skin_num}"
    new_path = f"characters/{champion}/skins/skin0"
    if learn_overlay is not None and Path(learn_overlay).is_file():
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.bin"
            aliased = Path(tmp) / "aliased.bin"
            raw.write_bytes(data)
            proc = subprocess.run(
                [str(learn_overlay), "bin-alias", str(raw), str(aliased),
                 old_path, new_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=60,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"bin-alias 失败: {proc.stdout} {proc.stderr}")
            data = aliased.read_bytes()
    else:
        # 无 learn-overlay（纯 Python 环境）：退化提示（构建仍需 learn-overlay）
        raise RuntimeError("bin-alias 需要 learn-overlay（先 cargo build --release）")

    # 覆盖目标路径：skin0.bin（游戏加载的入口）
    dst_rel = Path("data") / "characters" / champion / "skins" / "skin0.bin"
    wad_name = f"{champion.capitalize()}.wad.client"
    mod_root = Path(out_mod_dir)
    target = mod_root / "content" / "base" / wad_name / dst_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    # 最小 mod.config.json（ltk_mod_project::ModProject 必填字段；authors 为字符串数组）
    # 注意：必须显式声明 layers —— ltk_overlay 0.5.2 的收集逻辑直接遍历
    # project.layers，缺省空数组会收集到 0 个覆盖文件（注释里的"默认 base 层"
    # 约定在 0.5.2 中并未实现）。
    config = {
        "name": f"skin-swap-{champion}-{skin_num}",
        "display_name": f"{champion} Skin{skin_num} -> Skin0",
        "version": "1.0.0",
        "description": f"auto-generated skin swap: show skin{skin_num} as skin0 ({champion})",
        "authors": ["YsnSkin-Learn"],
        "layers": [{"name": "base", "priority": 0}],
    }
    (mod_root / "mod.config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return mod_root


def build_swap_for_skin(
    game_dir: str | Path,
    champion: str,
    skin_num: int,
    out_mod_dir: str | Path,
    learn_overlay: str | Path | None = None,
) -> Path:
    """便捷入口：打开英雄 WAD 并生成 mod。champion 为小写别名。"""
    wad_path = Path(game_dir) / "DATA" / "FINAL" / "Champions" / f"{champion.capitalize()}.wad.client"
    if not wad_path.is_file():
        # 尝试大小写不敏感查找
        matches = list((Path(game_dir) / "DATA" / "FINAL" / "Champions").glob(f"{champion}*.wad.client"))
        if not matches:
            raise FileNotFoundError(f"找不到英雄 WAD: {wad_path}")
        wad_path = matches[0]
    with Wad(wad_path) as wad:
        return build_skin_swap_mod(wad, champion, skin_num, out_mod_dir,
                                   learn_overlay=learn_overlay)
