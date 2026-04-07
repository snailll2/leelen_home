from .BaseAck import BaseAck


class FetchConfigModAck(BaseAck):
    def __init__(self, T1=0, T2=0, T3=0, cont="", cont_type="", num_left=0, tbl="", type="", ack=""):
        super().__init__()
        self.T1 = T1
        self.T2 = T2
        self.T3 = T3
        self.cont = cont
        self.cont_type = cont_type
        self.num_left = num_left
        self.tbl = tbl
        self.type = type

    @classmethod
    def from_dict(cls, data):
        return cls(
            T1=data.get("T1", 0),
            T2=data.get("T2", 0),
            T3=data.get("T3", 0),
            cont=data.get("cont", ""),
            cont_type=data.get("cont_type", ""),
            num_left=data.get("num_left", 0),
            tbl=data.get("tbl", ""),
            type_=data.get("type", "")
        )

    def to_dict(self):
        return {
            "T1": self.T1,
            "T2": self.T2,
            "T3": self.T3,
            "cont": self.cont,
            "cont_type": self.cont_type,
            "num_left": self.num_left,
            "tbl": self.tbl,
            "type": self.type
        }
