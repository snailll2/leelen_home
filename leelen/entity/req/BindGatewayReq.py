class BindGatewayReq:
    def __init__(self):
        self.account = ""      # type: str
        self.appID = ""        # type: str
        self.gatewayName = ""  # type: str
        self.groupId = ""      # type: str
        self.password = ""     # type: str

    def __str__(self):
        return (f"BindGatewayReq(account='{self.account}', appID='{self.appID}', "
                f"gatewayName='{self.gatewayName}', groupId='{self.groupId}', "
                f"password='{'*' * len(self.password) if self.password else ''}')")

    def __repr__(self):
        return self.__str__()