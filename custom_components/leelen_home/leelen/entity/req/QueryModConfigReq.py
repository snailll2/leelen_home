class QueryModConfigReq:
    def __init__(self):
        self.T1: int = 0  # Using int since Python doesn't distinguish between long and int

    def __str__(self) -> str:
        return f"QueryModConfigReq(T1={self.T1})"

    def __repr__(self) -> str:
        return self.__str__()

    def to_dict(self) -> dict:
        """Converts the object to a dictionary for JSON serialization"""
        return {'T1': self.T1}

    @classmethod
    def from_dict(cls, data: dict) -> 'QueryModConfigReq':
        """Creates an instance from a dictionary"""
        req = cls()
        req.T1 = data.get('T1', 0)
        return req