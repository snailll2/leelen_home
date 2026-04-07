class FetchConfigModReq:
    def __init__(self):
        self.T1 = 0  # long type in Python is just int (unlimited precision)
        self.T2 = 0  # long type in Python is just int (unlimited precision)
        self.num = 0  # int
        self.tbl = ""  # str
        self.type = ""  # str

    def __str__(self):
        return f"FetchConfigModReq(T1={self.T1}, T2={self.T2}, num={self.num}, tbl='{self.tbl}', type='{self.type}')"

    def __repr__(self):
        return self.__str__()

    def to_dict(self):
        return {
            "T1": self.T1,
            "T2": self.T2,
            "num": self.num,
            "tbl": self.tbl,
            "type": self.type
        }
