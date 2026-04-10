"""
基础连接模块

提供TCP连接的基类功能，包括：
- 连接状态管理
- 心跳机制
- 数据收发
- 自动重连

Classes:
    ConnectState: 连接状态枚举
    LogonState: 登录状态枚举
    BaseConnect: 连接基类
"""

import socket
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Callable, Any

from .entity.GatewayInfo import GatewayInfo
from .utils.LogUtils import LogUtils
from .utils.SslUtils import SslUtils
from .utils.Exceptions import (
    safe_execute, retry_on_error, ConnectionException,
    handle_exceptions, ErrorCode
)
from .common.DefaultThreadPool import DefaultThreadPool
from .common import LeelenConst

class ConnectState(Enum):
    """
    连接状态枚举

    Attributes:
        NONE: 未连接
        CONNECTING: 连接中
        CONNECTED: 已连接
    """
    NONE = ("None", 0)
    CONNECTING = ("Connecting", 1)
    CONNECTED = ("Connected", 2)

    def __init__(self, description: str, code: int):
        self.description = description
        self.code = code


class LogonState(Enum):
    """
    登录状态枚举

    Attributes:
        NONE: 未登录
        LOGGING_ON: 登录中
        LOGGED_ON: 已登录
    """
    NONE = ("None", 0)
    LOGGING_ON = ("LoggingOn", 1)
    LOGGED_ON = ("LoggedOn", 2)

    def __init__(self, description: str, code: int):
        self.description = description
        self.code = code


@dataclass
class ConnectionConfig:
    """
    连接配置

    Attributes:
        max_connecting_count: 最大连接尝试次数
        heartbeat_interval: 心跳间隔（秒）
        heartbeat_timeout: 心跳超时时间（秒）
        socket_timeout: Socket超时时间（秒）
        reconnect_delay: 重连延迟（秒）
        recv_buffer_size: 接收缓冲区大小
    """
    max_connecting_count: int = 5
    heartbeat_interval: float = 5.0
    heartbeat_timeout: float = 30.0
    socket_timeout: float = 0.5
    reconnect_delay: float = 1.0
    recv_buffer_size: int = 4096


class BaseConnect(ABC):
    """
    连接基类

    提供TCP连接的基础功能，子类需要实现以下抽象方法：
    - create_heartbeat_data: 创建心跳数据
    - handle_recv_data: 处理接收到的数据
    - on_connect_result: 连接结果回调
    - on_server_host_empty: 服务器地址为空回调
    - send_logon_data: 发送登录数据

    Attributes:
        server_host: 服务器主机地址
        server_port: 服务器端口
        username: 用户名
        password: 密码
    """

    # 消息类型常量
    MSG_TYPE_CONNECT_RESULT = 0
    MSG_TYPE_SERVER_HOST_EMPTY = 1
    MSG_TYPE_LOGON_TIMEOUT = 3

    def __init__(
        self,
        server_host: str,
        server_port: int,
        username: str,
        password: str,
        config: Optional[ConnectionConfig] = None
    ):
        """
        初始化连接基类

        Args:
            server_host: 服务器主机地址
            server_port: 服务器端口
            username: 用户名
            password: 密码
            config: 连接配置，使用默认配置如果为None
        """
        # 连接信息
        self.server_host = server_host
        self.server_port = server_port
        self.username = username
        self.password = password
        self.config = config or ConnectionConfig()

        # 锁对象
        self._socket_lock = threading.Lock()
        self._recv_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()

        # 状态
        self._connect_state = ConnectState.NONE
        self._logon_state = LogonState.NONE
        self._recv_data_running = False
        self._connecting_count = 0
        self._connect_retry_count = 0

        # Socket
        self._socket: Optional[socket.socket] = None
        self._output_stream: Optional[socket.SocketIO] = None

        # 心跳相关
        self._heartbeat_data: bytes = b''
        self._pre_heartbeat_recv = False
        self._pre_heartbeat_recv_time = -1.0
        self._pre_heartbeat_start_time = time.time()
        self._pre_heartbeat_send_time = -1.0

        # 日志
        self._show_log = True
        self._tag = "🍺 BaseConnect"

        # 线程执行器
        self._scheduled_executor: Optional[threading.Thread] = None
        self._connect_executor: Optional[threading.Thread] = None
        self._recv_data_executor: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # region 属性

    @property
    def connect_state(self) -> ConnectState:
        """获取当前连接状态"""
        with self._state_lock:
            return self._connect_state

    @connect_state.setter
    def connect_state(self, state: ConnectState) -> None:
        """设置连接状态"""
        with self._state_lock:
            old_state = self._connect_state
            self._connect_state = state
            if self._show_log:
                LogUtils.d(self._tag, f"State: {old_state.name} -> {state.name}")

    @property
    def logon_state(self) -> LogonState:
        """获取当前登录状态"""
        with self._state_lock:
            return self._logon_state

    @logon_state.setter
    def logon_state(self, state: LogonState) -> None:
        """设置登录状态"""
        with self._state_lock:
            self._logon_state = state
            self._pre_heartbeat_recv = (state == LogonState.LOGGED_ON)
            if self._pre_heartbeat_recv:
                self._pre_heartbeat_recv_time = time.time()

    @property
    def is_logged_on(self) -> bool:
        """检查是否已登录"""
        return self.logon_state == LogonState.LOGGED_ON

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.connect_state == ConnectState.CONNECTED

    # endregion

    # region 抽象方法

    @abstractmethod
    def create_heartbeat_data(self) -> bytes:
        """
        创建心跳数据

        Returns:
            心跳数据字节串
        """
        pass

    @abstractmethod
    def handle_recv_data(self, data: bytes) -> None:
        """
        处理接收到的数据

        Args:
            data: 接收到的数据
        """
        pass

    @abstractmethod
    def on_connect_result(self, success: bool) -> None:
        """
        连接结果回调

        Args:
            success: 是否连接成功
        """
        pass

    @abstractmethod
    def on_server_host_empty(self) -> None:
        """服务器地址为空时的回调"""
        pass

    @abstractmethod
    def send_logon_data(self) -> None:
        """发送登录数据"""
        pass

    # endregion

    # region 连接管理

    def connect(self) -> None:
        """建立连接"""
        try:
            if self._connecting_count >= self.config.max_connecting_count:
                self._stop_connect_executor()
                return

            if self._is_connect_running():
                self._connecting_count += 1
                if self._show_log:
                    LogUtils.d(self._tag, f"Connection attempt {self._connecting_count}")
            else:
                self._connecting_count = 0
                self._start_connect_executor()
        except Exception as e:
            if self._show_log:
                LogUtils.d(self._tag, f"Connect error: {e}")

    def connect_lan(self) -> None:
        """连接到局域网设备"""
        if self.connect_state == ConnectState.NONE:
            self.server_host = GatewayInfo.get_instance().get_lan_address_ip()
            self.connect()

    def close(self) -> None:
        """关闭连接"""
        self._stop_all_executors()
        self._close_socket()

    def reset(self) -> None:
        """
        重置连接状态

        停止所有线程，关闭socket，重置状态，然后自动重连。
        """
        LogUtils.w(self._tag, "Resetting connection...")

        # 1. 停止所有执行器
        self._recv_data_running = False
        self._stop_all_executors()

        # 2. 关闭socket和流
        self._close_socket()

        # 3. 重置状态
        with self._state_lock:
            self._connect_state = ConnectState.NONE
            self._logon_state = LogonState.NONE
        self._connect_retry_count = 0
        self._pre_heartbeat_recv = False
        self._pre_heartbeat_recv_time = -1.0
        self._pre_heartbeat_start_time = time.time()
        self._pre_heartbeat_send_time = -1.0

        LogUtils.d(self._tag, "Reset completed, preparing to reconnect")

        # 4. 自动重新连接
        try:
            self.connect_lan()
        except Exception as e:
            LogUtils.e(self._tag, f"Error during reconnect: {e}")

        # 5. 确保心跳线程重新启动
        try:
            self.start_heartbeat()
        except Exception as e:
            LogUtils.e(self._tag, f"Error starting heartbeat: {e}")

    def _close_socket(self) -> None:
        """关闭socket和相关流"""
        if self._socket:
            try:
                self._socket.close()
                LogUtils.d(self._tag, "Socket closed")
            except Exception as e:
                if self._show_log:
                    LogUtils.d(self._tag, f"Close socket error: {e}")
            finally:
                self._socket = None

        if self._output_stream:
            try:
                self._output_stream.close()
                LogUtils.d(self._tag, "Output stream closed")
            except Exception as e:
                if self._show_log:
                    LogUtils.d(self._tag, f"Close output stream error: {e}")
            finally:
                self._output_stream = None

    # endregion

    # region 线程执行器管理

    def _start_connect_executor(self) -> None:
        """启动连接执行器"""
        self._stop_connect_executor()
        self._connect_executor = threading.Thread(
            target=self._connect_worker,
            name=f"{self._tag}-Connect"
        )
        self._connect_executor.daemon = True
        self._connect_executor.start()

    def _stop_connect_executor(self) -> None:
        """停止连接执行器"""
        if self._connect_executor and self._connect_executor.is_alive():
            self._stop_event.set()
            # 避免当前线程尝试join自己
            if threading.current_thread() is not self._connect_executor:
                self._connect_executor.join(timeout=2.0)
                LogUtils.d(self._tag, "Connect executor stopped")
        self._connect_executor = None

    def _start_recv_data_executor(self) -> None:
        """启动数据接收执行器"""
        self._stop_recv_data_executor()
        self._recv_data_running = True
        self._recv_data_executor = threading.Thread(
            target=self._recv_data_worker,
            name=f"{self._tag}-Recv"
        )
        self._recv_data_executor.daemon = True
        self._recv_data_executor.start()
        LogUtils.d(self._tag, "Recv data executor started")

    def _stop_recv_data_executor(self) -> None:
        """停止数据接收执行器"""
        self._recv_data_running = False

        # 关闭socket以唤醒阻塞的recv()
        if self._socket:
            try:
                self._socket.close()
            except:
                pass

        if self._recv_data_executor and self._recv_data_executor.is_alive():
            # 避免当前线程尝试join自己
            if threading.current_thread() is not self._recv_data_executor:
                self._recv_data_executor.join(timeout=2.0)
                LogUtils.d(self._tag, "Recv data executor stopped")
        self._recv_data_executor = None

    def _start_heartbeat_executor(self) -> None:
        """启动心跳执行器"""
        self._stop_heartbeat_executor()
        self._scheduled_executor = threading.Thread(
            target=self._heartbeat_worker,
            name=f"{self._tag}-Heartbeat"
        )
        self._scheduled_executor.daemon = True
        self._scheduled_executor.start()
        LogUtils.d(self._tag, "Heartbeat executor started")

    def _stop_heartbeat_executor(self) -> None:
        """停止心跳执行器"""
        if self._scheduled_executor and self._scheduled_executor.is_alive():
            self._stop_event.set()
            # 避免当前线程尝试join自己
            if threading.current_thread() is not self._scheduled_executor:
                self._scheduled_executor.join(timeout=2.0)
                LogUtils.d(self._tag, "Heartbeat executor stopped")
        self._scheduled_executor = None
        self._stop_event.clear()

    def _stop_all_executors(self) -> None:
        """停止所有执行器"""
        self._stop_heartbeat_executor()
        self._stop_connect_executor()
        self._stop_recv_data_executor()

    def _is_connect_running(self) -> bool:
        """检查连接是否正在进行"""
        return (
            self._connect_executor is not None
            and self._connect_executor.is_alive()
        )

    # endregion

    # region 工作线程

    def _connect_worker(self) -> None:
        """连接工作线程"""
        self.connect_state = ConnectState.CONNECTING
        self._connect_retry_count += 1

        if not self.server_host:
            if self._show_log:
                LogUtils.w(self._tag, "Server host is empty")
            self.on_server_host_empty()
            return

        try:
            # 创建SSL上下文和socket
            context = SslUtils.get_lan_socket_ssl_context(
                LeelenConst.IOT_ANDROID_P12,
                LeelenConst.P12_KEY_PWD,
                LeelenConst.IOT_ROOT_BKS,
                LeelenConst.HTTPS_KEY_PWD
            )

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket = context.wrap_socket(
                sock,
                server_hostname=self.server_host,
                server_side=False
            )
            self._socket.connect((self.server_host, self.server_port))
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

            if self._socket.fileno() != -1:
                self._output_stream = self._socket.makefile('wb')
                self.connect_state = ConnectState.CONNECTED
                self._start_recv_data_executor()
                self.heartbeat_once()
                self.on_connect_result(True)
            else:
                raise ConnectionException("Socket creation failed")

        except Exception as e:
            if self._show_log:
                LogUtils.d(self._tag, f"Connection error: {e}")
            self.connect_state = ConnectState.NONE
            self.reset()
            self.on_connect_result(False)

    def _recv_data_worker(self) -> None:
        """数据接收工作线程"""
        try:
            if not self._socket:
                return

            with self._socket_lock:
                self._socket.settimeout(self.config.socket_timeout)

            while self._recv_data_running and not self._stop_event.is_set():
                try:
                    data = self._socket.recv(self.config.recv_buffer_size)
                    if data:
                        self.handle_recv_data(data)
                except socket.timeout:
                    continue
                except BlockingIOError:
                    continue
                except OSError:
                    # Socket已关闭
                    break

        except Exception as e:
            LogUtils.e(self._tag, f"Receive data error: {e}")
        finally:
            self._recv_data_running = False
            self.reset()

    def _heartbeat_worker(self) -> None:
        """心跳工作线程"""
        while not self._stop_event.is_set():
            try:
                self._send_heartbeat_internal()
            except Exception as e:
                LogUtils.d(self._tag, f"Heartbeat error: {e}")

            # 等待下一次心跳
            self._stop_event.wait(self.config.heartbeat_interval)

    # endregion

    # region 心跳管理

    def start_heartbeat(self) -> None:
        """启动心跳"""
        self._heartbeat_data = self.create_heartbeat_data()

        # 检查是否已有心跳线程在运行
        if self._scheduled_executor and self._scheduled_executor.is_alive():
            LogUtils.d(self._tag, "Heartbeat already running")
            return

        self._start_heartbeat_executor()

    def stop_heartbeat(self) -> None:
        """停止心跳"""
        self._stop_heartbeat_executor()

    def heartbeat_once(self) -> None:
        """发送一次心跳"""
        LogUtils.d(self._tag, "Heartbeat once")
        self._heartbeat_data = self.create_heartbeat_data()
        threading.Thread(target=self._send_heartbeat_internal).start()

    def _send_heartbeat_internal(self) -> None:
        """内部心跳发送逻辑"""
        if self.connect_state == ConnectState.NONE:
            self.connect()
        elif self.connect_state != ConnectState.CONNECTING:
            if self.logon_state == LogonState.NONE:
                self.logon()
            elif self.logon_state != LogonState.LOGGING_ON:
                # 检查心跳超时
                if time.time() - self._pre_heartbeat_recv_time > self.config.heartbeat_timeout:
                    self._pre_heartbeat_start_time = time.time()
                    LogUtils.e(self._tag, "Heartbeat timeout, resetting connection")
                    self.reset()
                else:
                    self.send_data(self._heartbeat_data)
                    self._pre_heartbeat_recv = False
                    self._pre_heartbeat_send_time = time.time()

    def recv_heartbeat(self) -> None:
        """接收心跳响应"""
        self._pre_heartbeat_recv = True
        self._pre_heartbeat_recv_time = time.time()

    # endregion

    # region 数据发送

    def send_data(self, data: bytes) -> None:
        """
        发送数据

        Args:
            data: 要发送的数据
        """
        if data is None:
            return

        if self._show_log:
            LogUtils.d("📤 Sending data", data.hex())

        if self._socket and self.is_connected:
            def send_task():
                try:
                    with self._send_lock:
                        self._socket.sendall(data)
                except (ConnectionResetError, BrokenPipeError, OSError) as e:
                    LogUtils.w(self._tag, f"Connection error while sending: {e}")
                    self.reset()
                    self.connect_lan()
                except Exception as e:
                    if self._show_log:
                        LogUtils.d(self._tag, f"Send data error: {e}")

            DefaultThreadPool.get_instance().execute(send_task)
        else:
            LogUtils.i(self._tag, "Socket not ready, resetting connection")
            self.reset()
            self.connect_lan()

    def send_heartbeat(self, data: bytes) -> None:
        """
        发送心跳数据

        Args:
            data: 心跳数据
        """
        self.send_data(data)

    # endregion

    # region 登录管理

    def logon(self) -> None:
        """执行登录"""
        if self.is_connected:
            if self.logon_state == LogonState.NONE:
                self.send_logon_data()
            else:
                if self._show_log:
                    LogUtils.d(self._tag, "Already logging in or logged in")
        else:
            self.connect()

    # endregion

    # region 可用性检查

    def is_available(self) -> bool:
        """
        检查连接是否可用

        Returns:
            连接是否可用
        """
        if self._socket and self._socket.fileno() != -1:
            with self._socket_lock:
                try:
                    # 通过发送紧急数据测试连接
                    self._socket.send(b'\xFF', socket.MSG_OOB)
                    return True
                except Exception as e:
                    if self._show_log:
                        LogUtils.d(self._tag, f"Connection test failed: {e}")
                    return False
        return False

    # endregion
