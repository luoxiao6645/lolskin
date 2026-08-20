"""皮肤交换 mod 生成器：把目标皮肤 SkinN 的对象图别名到 Skin0 的覆盖。

原理（对齐 YsnSkin 的 entry-alias）：
  游戏加载英雄时读取 data/characters/<英雄>/skins/skin0.bin 及其链接的 bin。
  把 skinN.bin 的**全部对象**（根对象 + Particles 等子对象）路径别名到 skin0
  （PROP 只存 path_hash；对象引用为 Hash 值，字节级替换）：
    - 模型/贴图等资源路径保持指向 skinN（原版 WAD 中全部存在）
    - 粒子特效对象（SkinN/Particles/*）改名 Skin0/Particles/* 使游戏能按
      skin0 命名空间查到特效
  动画图 bin（Animations/SkinN.bin）同样别名到 Animations/skin0.bin。

产物：ltk 生态的 mod 目录（ltk_overlay::content::FsModContent 兼容）：
  mod.config.json
  content/base/<英雄>.wad.client/data/characters/<x>/skins/skin0.bin
  content/base/<英雄>.wad.client/data/characters/<x>/animations/skin0.bin
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .wad import Wad

DEFAULT_GAME_DIR = Path(r"E:\Program Files (x86)\英雄联盟(26)\Game")
DEFAULT_BINHASHES = Path(__file__).resolve().parent.parent / "data" / "hashes" / "binhashes-2026-08-14.lhdb"


def fnv1a32(data: bytes) -> int:
    """ltk BinHash：FNV-1a 32（小写路径）。与 binhashes 表验证一致。"""
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def build_alias_map(object_hashes: list[int], old_prefix: str, new_prefix: str,
                    binhashes_db) -> list[tuple[int, int]]:
    """对象路径含 old_prefix 的 → 前缀替换为 new_prefix 的映射。"""
    mapping = []
    for h in object_hashes:
        path = binhashes_db.get(h)
        if path and path.lower().startswith(old_prefix):
            new_path = new_prefix + path[len(old_prefix):]
            mapping.append((h, fnv1a32(new_path.lower().encode("utf-8"))))
    return mapping


def alias_bin_file(learn_overlay: str | Path, data: bytes, champion: str,
                   skin_num: int, kind: str) -> tuple[bytes, list[tuple[int, int]]]:
    """对一个 bin 字节流执行全对象别名（skins 或 animations）。

    返回 (改后字节, 映射)。kind: 'skins'|'animations'。
    流程：bin-list 拿对象 hash → binhashes 反查路径 → 生成映射 → bin-alias-map。
    """
    from .lhdb import Lhdb

    old_prefix = f"characters/{champion}/{kind}/skin{skin_num}"
    new_prefix = f"characters/{champion}/{kind}/skin0"
    # 字符串引用前缀（bin 内对象引用是 "Characters/X/Skins/SkinN..." 形式；
    # 等长替换为 Skin0；ASSETS 资源路径不受影响）
    cap = champion.capitalize()
    kind_cap = "Skins" if kind == "skins" else "Animations"
    str_prefixes = [f"Characters/{cap}/{kind_cap}/Skin{skin_num}",
                    f"Characters/{cap}/{kind_cap}/Skin0"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        raw = tmp / "raw.bin"
        raw.write_bytes(data)
        # 1) 对象 hash 列表
        proc = subprocess.run([str(learn_overlay), "bin-list", str(raw)],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(f"bin-list 失败: {proc.stdout} {proc.stderr}")
        hashes = [int(ln.split()[1], 16) for ln in proc.stdout.splitlines()
                  if ln.startswith("object ")]
        if not hashes:
            return b"", []
        # 2) binhashes 反查
        db = Lhdb.open(DEFAULT_BINHASHES)
        mapping = build_alias_map(hashes, old_prefix, new_prefix, db)
        if not mapping:
            raise RuntimeError(
                f"未找到含 {old_prefix} 的对象（binhashes 表可能过期）")
        return run_bin_alias_map(learn_overlay, raw, data, mapping, str_prefixes), mapping


def alias_champion_bin(learn_overlay: str | Path, data: bytes, champion: str,
                       skin_num: int, particle_map: list[tuple[int, int]]) -> bytes:
    """角色 bin：{Champion}Skin{N}_Manager → {Champion}Skin0_Manager + 引用替换。

    游戏按皮肤编号在角色 bin 查 {Champion}Skin{N}_Manager（技能特效管理器）；
    训练营 selectedSkinId=base 时找不到 Skin0_Manager → 无特效。
    别名后 base 编号也能拿到皮肤 N 的特效；Manager 属性引用的皮肤粒子对象
    哈希一并替换（指向已别名的 Skin0/Particles/*）。
    """
    old_mgr = f"characters/{champion}/spells/{champion}skin{skin_num}_manager"
    new_mgr = f"characters/{champion}/spells/{champion}skin0_manager"
    mapping = [(fnv1a32(old_mgr.lower().encode("utf-8")),
                fnv1a32(new_mgr.lower().encode("utf-8")))]
    # 合并粒子映射（Manager 属性引用皮肤粒子对象），去重保序
    seen = set(mapping)
    for pair in particle_map:
        if pair not in seen:
            seen.add(pair)
            mapping.append(pair)
    # 字符串引用前缀（Manager 属性可能字符串引用皮肤粒子对象）
    cap = champion.capitalize()
    str_prefixes = [f"Characters/{cap}/Skins/Skin{skin_num}",
                    f"Characters/{cap}/Skins/Skin0"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        raw = tmp / "raw.bin"
        raw.write_bytes(data)
        return run_bin_alias_map(learn_overlay, raw, data, mapping, str_prefixes)


def run_bin_alias_map(learn_overlay: str | Path, raw: Path, data: bytes,
                      mapping: list[tuple[int, int]],
                      string_prefixes: list[str] | None = None) -> bytes:
    """执行 bin-edit（serde JSON 中转，精确无字节误伤）并返回输出字节。"""
    with tempfile.TemporaryDirectory() as tmp2:
        tmp2 = Path(tmp2)
        map_file = tmp2 / "map.txt"
        map_file.write_text(
            "\n".join(f"{o:08x} {n:08x}" for o, n in mapping), encoding="utf-8")
        out = tmp2 / "out.bin"
        cmd = [str(learn_overlay), "bin-edit", str(raw), str(out), str(map_file)]
        prefixes = string_prefixes or []
        for i in range(0, len(prefixes) - 1, 2):
            cmd += ["--string-prefix", prefixes[i], prefixes[i + 1]]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"bin-edit 失败: {proc.stdout} {proc.stderr}")
        return out.read_bytes()


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

    if learn_overlay is None or not Path(learn_overlay).is_file():
        raise RuntimeError("bin-alias 需要 learn-overlay（先 cargo build --release）")

    # 全对象别名：skins/skinN.bin（根对象 + Particles 子对象）→ skin0
    data, skin_mapping = alias_bin_file(learn_overlay, data, champion, skin_num, "skins")

    mod_root = Path(out_mod_dir)
    wad_name = f"{champion.capitalize()}.wad.client"

    # 覆盖目标路径：skin0.bin（游戏加载的入口）
    dst_rel = Path("data") / "characters" / champion / "skins" / "skin0.bin"
    target = mod_root / "content" / "base" / wad_name / dst_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    # 角色 bin：{Champion}Skin{N}_Manager → Skin0_Manager（特效管理器，
    # 游戏按皮肤编号查它——训练营 selectedSkinId=base 时找不到 Skin0_Manager
    # 导致无特效；别名后 base 编号也能拿到皮肤 N 的特效）
    champ_bin_path = f"data/characters/{champion}/{champion}.bin"
    champ_data = wad.read_path(champ_bin_path)
    if champ_data is not None:
        try:
            champ_data = alias_champion_bin(learn_overlay, champ_data, champion,
                                            skin_num, skin_mapping)
            champ_target = (mod_root / "content" / "base" / wad_name /
                            "data" / "characters" / champion / f"{champion}.bin")
            champ_target.parent.mkdir(parents=True, exist_ok=True)
            champ_target.write_bytes(champ_data)
        except RuntimeError as exc:
            print(f"[modgen][警告] 角色 bin 别名失败（特效可能缺失）: {exc}", flush=True)

    # 动画图 bin：Animations/skinN.bin → Animations/skin0.bin（存在时）
    anim_src = f"data/characters/{champion}/animations/skin{skin_num}.bin"
    anim_data = wad.read_path(anim_src)
    if anim_data is not None:
        try:
            anim_data, _ = alias_bin_file(learn_overlay, anim_data, champion,
                                          skin_num, "animations")
            anim_target = (mod_root / "content" / "base" / wad_name /
                           "data" / "characters" / champion / "animations" / "skin0.bin")
            anim_target.parent.mkdir(parents=True, exist_ok=True)
            anim_target.write_bytes(anim_data)
        except RuntimeError as exc:
            # 动画别名失败不阻塞皮肤（动画回退 base）
            print(f"[modgen][警告] 动画 bin 别名失败（回退 base 动画）: {exc}", flush=True)

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
