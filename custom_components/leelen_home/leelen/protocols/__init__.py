"""
协议模块

提供局域网(LAN)和广域网(WAN)通信协议实现。

Modules:
    BaseLanProtocol: 局域网协议基类
    BaseWanProtocol: 广域网协议基类
    ProtocolBuilder: 协议构建器
    BindGatewayLanProtocol: 网关绑定协议
    DeviceControlLanProtocol: 设备控制协议
    DeviceStatusLanProtocol: 设备状态协议
    FetchModConfigLanProtocol: 获取模块配置协议
    GetDeviceStatusLanProtocol: 获取设备状态协议
    GetServerCodeWanProtocol: 获取服务器代码协议
    HeartLanProtocol: 局域网心跳协议
    HeartWanProtocol: 广域网心跳协议
    LoginLanProtocol: 局域网登录协议
    LoginWanProtocol: 广域网登录协议
    PassThroughWanProtocol: WAN透传协议
    QueryModConfigLanProtocol: 查询模块配置协议
    RandomLanProtocol: 随机数协议
"""

from .BaseLanProtocol import BaseLanProtocol
from .BaseWanProtocol import BaseWanProtocol
from .ProtocolBuilder import (
    ProtocolBuilder,
    ProtocolField,
    FixedLengthProtocolBuilder,
    VariableLengthProtocolBuilder,
    ChecksumProtocolBuilder,
)
from .BindGatewayLanProtocol import BindGatewayLanProtocol
from .DeviceControlLanProtocol import DeviceControlLanProtocol
from .DeviceStatusLanProtocol import DeviceStatusLanProtocol
from .FetchModConfigLanProtocol import FetchModConfigLanProtocol
from .GetDeviceStatusLanProtocol import GetDeviceStatusLanProtocol
from .GetServerCodeWanProtocol import GetServerCodeWanProtocol
from .HeartLanProtocol import HeartLanProtocol
from .HeartWanProtocol import HeartWanProtocol
from .LoginLanProtocol import LoginLanProtocol
from .LoginWanProtocol import LoginWanProtocol
from .PassThroughWanProtocol import PassThroughWanProtocol
from .QueryModConfigLanProtocol import QueryModConfigLanProtocol
from .RandomLanProtocol import RandomLanProtocol

__all__ = [
    # 基类
    'BaseLanProtocol',
    'BaseWanProtocol',
    # 构建器
    'ProtocolBuilder',
    'ProtocolField',
    'FixedLengthProtocolBuilder',
    'VariableLengthProtocolBuilder',
    'ChecksumProtocolBuilder',
    # LAN协议
    'BindGatewayLanProtocol',
    'DeviceControlLanProtocol',
    'DeviceStatusLanProtocol',
    'FetchModConfigLanProtocol',
    'GetDeviceStatusLanProtocol',
    'HeartLanProtocol',
    'LoginLanProtocol',
    'QueryModConfigLanProtocol',
    'RandomLanProtocol',
    # WAN协议
    'GetServerCodeWanProtocol',
    'HeartWanProtocol',
    'LoginWanProtocol',
    'PassThroughWanProtocol',
]
