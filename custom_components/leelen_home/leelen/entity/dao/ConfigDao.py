from ..Config import Config
from ...common.SingletonMixin import SingletonMixin
from ...utils.LogUtils import LogUtils

class ConfigDao(SingletonMixin):
    config = Config()
    config.latest_time = 26800

        # Config.delete().where(
        #     (Config.gateway_address == gateway) |
        #     (Config.gateway_address == DEFAULT_GATEWAY_DESC)
        # ).execute()

    def get_config_by_gateway(self):
        # 原 ORM 版按网关地址查询( gateway = GatewayInfo.get_instance().gateway_desc_string ),
        # 当前为内存实现,不区分网关 —— 多网关场景下会互相覆盖,待补。
        # config = Config.select().where(Config.gateway_address == gateway).first()
        # if config is None:
        #     LogUtils.i("ConfigDao", "getConfigByGateway config == null")
        # else:
        #     LogUtils.i("ConfigDao", f"getConfigByGateway {config.latest_time}")
        return self.config

    def save_or_update_config_by_gateway(self, config: Config):
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
