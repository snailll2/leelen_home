class ConfigLockReq:
    def __init__(self):
        self.T1 = 0  # long in Java becomes int in Python (unlimited precision)
        self.op = 0  # int
        self.time = 100  # int with default value 100

    def __str__(self):
        return f"ConfigLockReq(T1={self.T1}, op={self.op}, time={self.time})"

    def __repr__(self):
        return self.__str__()