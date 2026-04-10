"""
单例模式工具模块

提供线程安全的单例模式实现，支持多种单例创建方式。
"""

import threading
from functools import wraps
from typing import TypeVar, Type, Callable, Optional

T = TypeVar('T')


def singleton(cls: Type[T]) -> Type[T]:
    """
    单例模式装饰器

    使用双重检查锁定实现线程安全的单例模式。

    Args:
        cls: 需要转换为单例的类

    Returns:
        单例类

    Example:
        @singleton
        class MyClass:
            def __init__(self):
                self.value = 42
    """
    _instance: Optional[T] = None
    _lock = threading.Lock()

    @wraps(cls)
    def wrapper(*args, **kwargs) -> T:
        nonlocal _instance
        if _instance is None:
            with _lock:
                if _instance is None:
                    _instance = cls(*args, **kwargs)
        return _instance

    wrapper._instance = property(lambda self: _instance)
    wrapper._lock = _lock
    return wrapper


class SingletonMeta(type):
    """
    单例元类

    通过元类实现单例模式，所有使用该元类的类都会自动成为单例。

    Example:
        class MyClass(metaclass=SingletonMeta):
            def __init__(self):
                self.value = 42
    """
    _instances: dict[Type, object] = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def reset_instance(cls, target_cls: Type) -> None:
        """
        重置指定类的单例实例

        主要用于测试场景，允许重新创建实例。

        Args:
            target_cls: 需要重置的类
        """
        with cls._lock:
            cls._instances.pop(target_cls, None)


class SingletonBase:
    """
    单例基类

    继承此类即可获得单例能力，子类需要实现 _init_instance 方法。

    Example:
        class MyClass(SingletonBase):
            def _init_instance(self):
                self.value = 42
    """
    _instance: Optional['SingletonBase'] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 避免重复初始化
        if self._initialized:
            return
        with self._lock:
            if not self._initialized:
                self._init_instance()
                self._initialized = True

    def _init_instance(self) -> None:
        """
        子类重写此方法进行初始化

        此方法只会被调用一次，确保单例的正确初始化。
        """
        pass

    @classmethod
    def get_instance(cls: Type[T]) -> T:
        """
        获取单例实例

        Returns:
            单例实例
        """
        if cls._instance is None:
            cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """
        重置单例实例

        主要用于测试场景。
        """
        with cls._lock:
            cls._instance = None
            cls._initialized = False


def thread_safe_lazy_init(lock_attr: str = '_lock', instance_attr: str = '_instance'):
    """
    线程安全延迟初始化装饰器

    用于需要延迟初始化的属性。

    Args:
        lock_attr: 锁属性名
        instance_attr: 实例属性名

    Returns:
        装饰器函数
    """
    def decorator(init_func: Callable) -> Callable:
        @wraps(init_func)
        def wrapper(self, *args, **kwargs):
            instance = getattr(self, instance_attr, None)
            if instance is None:
                lock = getattr(self, lock_attr)
                with lock:
                    instance = getattr(self, instance_attr, None)
                    if instance is None:
                        instance = init_func(self, *args, **kwargs)
                        setattr(self, instance_attr, instance)
            return instance
        return wrapper
    return decorator
