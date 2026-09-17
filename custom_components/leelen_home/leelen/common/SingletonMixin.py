"""线程安全单例基类。

统一各模块里散落的单例样板(CommonModel / ConnectLan / HttpApi / GatewayInfo
等方式各异的 _instance + _lock + get_instance + reset_instance)。

用法::

    class Foo(SingletonMixin):
        pass

    Foo.get_instance()      # 获取唯一实例
    Foo.reset_instance()    # 释放单例(可选)

子类可按需覆写:
- ``_create_instance(*args, **kwargs)``:自定义构造逻辑(如传入宿主参数)。
  默认 ``cls(*args, **kwargs)``。
- ``_on_reset(instance)``:释放单例前的清理(关 socket/线程等)。默认空操作。
"""
from __future__ import annotations

import threading
from typing import Any, Optional


class SingletonMixin:
    _instance: Optional[Any] = None
    _singleton_lock = threading.Lock()

    @classmethod
    def get_instance(cls, *args, **kwargs):
        """获取单例,线程安全(双重检查)。"""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls._create_instance(*args, **kwargs)
        return cls._instance

    @classmethod
    def _create_instance(cls, *args, **kwargs):
        """子类可覆写自定义构造(如 ConnectWan 需要硬编码 server_host)。"""
        return cls(*args, **kwargs)

    @classmethod
    def reset_instance(cls) -> None:
        """释放单例。

        锁内置空,锁外调用 ``_on_reset`` 清理资源——
        close()/shutdown_now() 会 join 线程,若持锁会阻塞其他 get_instance。
        """
        with cls._singleton_lock:
            instance = cls._instance
            cls._instance = None
        if instance is not None:
            cls._on_reset(instance)

    @classmethod
    def _on_reset(cls, instance) -> None:
        """子类可覆写释放单例前的资源清理。"""