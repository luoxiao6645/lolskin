"""皮肤目录加载与映射。

数据：``data/skins.json``（skinId → 皮肤记录，2103 条）与
``data/champion-summary.json``（英雄摘要，174 个）——来自 YsnSkin 发布包，
本质是游戏目录数据（LCU ``/lol-game-data/assets/v1/skins.json`` 的快照）。

映射规则（docs/02-lcu-protocol.md）：``skinId = championId * 1000 + skinNum``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SKINS_JSON = Path(__file__).resolve().parent.parent / "data" / "skins.json"
DEFAULT_CHAMPIONS_JSON = (
    Path(__file__).resolve().parent.parent / "data" / "champion-summary.json"
)


@dataclass(frozen=True)
class Champion:
    id: int
    name: str
    alias: str


@dataclass(frozen=True)
class Skin:
    id: int
    champion_id: int
    skin_num: int
    name: str
    is_base: bool
    raw: dict


def champion_id_of_skin(skin_id: int) -> int:
    """skinId → championId（除法取整）。"""
    return skin_id // 1000


def skin_num_of(skin_id: int) -> int:
    """skinId → skinNum（取余）。"""
    return skin_id % 1000


class SkinCatalog:
    """加载并索引皮肤目录。"""

    def __init__(self, skins_path: str | Path = DEFAULT_SKINS_JSON,
                 champions_path: str | Path = DEFAULT_CHAMPIONS_JSON):
        self.skins_path = Path(skins_path)
        self.champions_path = Path(champions_path)
        self._skins: dict[int, Skin] = {}
        self._champions: dict[int, Champion] = {}
        self._by_champion: dict[int, list[Skin]] = {}
        self._load()

    def _load(self) -> None:
        raw_skins = json.loads(self.skins_path.read_text(encoding="utf-8"))
        raw_champions = json.loads(self.champions_path.read_text(encoding="utf-8"))
        for champ in raw_champions:
            cid = int(champ.get("id") or 0)
            if cid <= 0:
                continue
            self._champions[cid] = Champion(cid, champ.get("name") or "", champ.get("alias") or "")
        for skin_id_str, record in raw_skins.items():
            skin_id = int(skin_id_str)
            cid = champion_id_of_skin(skin_id)
            self._skins[skin_id] = Skin(
                id=skin_id,
                champion_id=cid,
                skin_num=skin_num_of(skin_id),
                name=record.get("name") or "",
                is_base=bool(record.get("isBase")),
                raw=record,
            )
            self._by_champion.setdefault(cid, []).append(self._skins[skin_id])
        for skins in self._by_champion.values():
            skins.sort(key=lambda s: (s.skin_num, s.id))

    def __len__(self) -> int:
        return len(self._skins)

    @property
    def champions(self) -> dict[int, Champion]:
        return dict(self._champions)

    def champion(self, champion_id: int) -> Champion | None:
        return self._champions.get(champion_id)

    def skin(self, skin_id: int) -> Skin | None:
        return self._skins.get(skin_id)

    def skins_of(self, champion_id: int) -> list[Skin]:
        """某英雄的全部皮肤（含基础皮肤，按 skinNum 升序）。"""
        return list(self._by_champion.get(champion_id, []))

    def skin_of(self, champion_id: int, skin_num: int) -> Skin | None:
        return self._skins.get(champion_id * 1000 + skin_num)
