from dataclasses import dataclass


@dataclass
class ModInfo:
    tbl: str = ""
    ins_n: int = 0
    upd_n: int = 0
    del_n: int = 0

    @staticmethod
    def from_dict(data: dict) -> "ModInfo":
        return ModInfo(
            tbl=data.get("tbl", ""),
            ins_n=data.get("ins_n", 0),
            upd_n=data.get("upd_n", 0),
            del_n=data.get("del_n", 0),
        )

    def to_dict(self) -> dict:
        return {
            "tbl": self.tbl,
            "ins_n": self.ins_n,
            "upd_n": self.upd_n,
            "del_n": self.del_n,
        }
