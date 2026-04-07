from typing import Generic, TypeVar, Optional

T = TypeVar('T')


class BaseRequest(Generic[T]):
    def __init__(self) -> None:
        self._params: Optional[T] = None
        self._seq: int = 0
        self._version: str = "V1.0"

    @property
    def params(self) -> Optional[T]:
        """获取请求参数"""
        return self._params

    @params.setter
    def params(self, value: T) -> None:
        """设置请求参数"""
        self._params = value

    @property
    def seq(self) -> int:
        """获取序列号"""
        return self._seq

    @seq.setter
    def seq(self, value: int) -> None:
        """设置序列号"""
        self._seq = value

    @property
    def version(self) -> str:
        """获取协议版本"""
        return self._version

    @version.setter
    def version(self, value: str) -> None:
        """设置协议版本"""
        self._version = value

    def to_dict(self) -> dict:
        """将对象转换为可序列化的字典"""
        return {
            "params": self._params,
            "seq": self._seq,
            "version": self._version
        }
