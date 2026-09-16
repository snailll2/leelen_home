"""leelen.common — 集中导出协议常量,替代原来的星号导入。

只显式导出调用方通过 ``from ..common import X`` 实际用到的名字,
避免 `import *` 把 LeelenType 的 ~50 个常量类全倾倒进包命名空间。
"""
from .DefaultThreadPool import DefaultThreadPool
from .LeelenConst import LeelenConst
from .LeelenType import (
    DeviceType,
    FunctionType,
    FunctionValue,
    GatewayTable,
    LanProtocolCmd,
    PropertyId,
    ProtocolDefault,
    TableOperateType,
    WanProtocolCmd,
)

__all__ = [
    "DefaultThreadPool",
    "LeelenConst",
    "DeviceType",
    "FunctionType",
    "FunctionValue",
    "GatewayTable",
    "LanProtocolCmd",
    "PropertyId",
    "ProtocolDefault",
    "TableOperateType",
    "WanProtocolCmd",
]
