from threading import Lock

from ..Config import Config
from ..GatewayInfo import GatewayInfo
from ...utils.LogUtils import LogUtils


class ConfigDao:
    _instance = None
    _lock = Lock()
    config = Config()
    config.latest_time = 26800


    @staticmethod
    def get_instance():
        if ConfigDao._instance is None:
            with ConfigDao._lock:
                if ConfigDao._instance is None:
                    ConfigDao._instance = ConfigDao()
        return ConfigDao._instance

    def delete_config_table(self):
        LogUtils.i("ConfigDao", "deleteConfigTable")
        Config.delete().execute()

    def delete_configs_by_gateway(self):
        LogUtils.i("ConfigDao", "deleteConfigsByGateway")
        gateway = GatewayInfo.get_instance().get_gateway_desc_string()
        # Config.delete().where(
        #     (Config.gateway_address == gateway) |
        #     (Config.gateway_address == DEFAULT_GATEWAY_DESC)
        # ).execute()

    def get_config_by_gateway(self):
        gateway = GatewayInfo.get_instance().get_gateway_desc_string()
        # config = Config.select().where(Config.gateway_address == gateway).first()
        # if config is None:
        #     LogUtils.i("ConfigDao", "getConfigByGateway config == null")
        # else:
        #     LogUtils.i("ConfigDao", f"getConfigByGateway {config.latest_time}")
        return self.config

    def save_or_update_config_by_gateway(self, config: Config):
        gateway = GatewayInfo.get_instance().get_gateway_desc_string()
        self.config.latest_time = config.latest_time
        # existing = Config.select().where(Config.gateway_address == gateway).first()
        # if existing:
        #     existing.latest_time = config.latest_time
        #     existing.save()
        # else:
        #     config.gateway_address = gateway
        #     config.save()
        # LogUtils.i("ConfigDao", f"config {config.latest_time}")
        # LogUtils.d(DEFAULT_GATEWAY_DESC, f"saveOrUpdateConfigByGateway {config.latest_time}")

    def update_config_time(self, t1: int):
        LogUtils.i("ConfigDao", f"updateConfigTime {t1}")
        self.config.latest_time = t1
        # LogUtils.d(DEFAULT_GATEWAY_DESC, f"updateConfigTime {t1}")
        # config = self.get_config_by_gateway()
        # if config:
        #     config.latest_time = t1
        #     config.save()
