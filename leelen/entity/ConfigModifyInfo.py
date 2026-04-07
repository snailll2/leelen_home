class ConfigModifyInfo:

    def __init__(self, config_version: int, T2: int):
        self.config_version = config_version
        self.T2 = T2

    @staticmethod
    def from_dict(d: dict):
        return ConfigModifyInfo(
            config_version=d.get("config_version"),
            T2=d.get("T2")
        )
