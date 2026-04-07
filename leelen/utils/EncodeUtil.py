import hashlib
import hmac
import string
import random
from typing import Optional, Union

from .LogUtils import LogUtils

HEX_DIGITS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
              'a', 'b', 'c', 'd', 'e', 'f']


class EncodeUtil:

    @staticmethod
    def get_md5(input_data: Union[str, bytes]) -> Union[str, bytes, None]:
        """
        Compute MD5 hash of input string or bytes
        Returns hex string for string input, bytes for bytes input
        """
        try:
            if isinstance(input_data, str):
                md5_hash = hashlib.md5(input_data.strip().encode()).hexdigest()
                return md5_hash
            elif isinstance(input_data, bytes):
                md5_hash = hashlib.md5(input_data).digest()
                return md5_hash
        except Exception as e:
            LogUtils.e(f"MD5 Error: {e}")
            return input_data if isinstance(input_data, str) else None

    @staticmethod
    def get_md5_hmac(message: str, key: str) -> str:
        """
        Compute HMAC-MD5 of message with key
        Returns hex string
        """
        try:
            hmac_md5 = hmac.new(
                key.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.md5
            )
            return hmac_md5.hexdigest()
        except Exception as e:
            LogUtils.e(f"HMAC-MD5 Error: {e}")
            return ""

    @staticmethod
    def int_to_hex(value: int) -> str:
        """Convert integer (0-15) to hex character"""
        if value <= 9:
            return chr(value + 48)
        return chr(value - 10 + 97)

    @staticmethod
    def is_safe(char: str) -> bool:
        """Check if character is safe for URLs"""
        if len(char) != 1:
            return False

        c = char[0]
        if c.isalnum():
            return True
        if c in {'!', '_', '-', '.', '\'', '(', ')', '*'}:
            return True
        return False

    @staticmethod
    def to_hex_string(byte_data: bytes) -> str:
        """Convert bytes to hex string"""
        return ''.join([f"{b:02x}" for b in byte_data])

    @staticmethod
    def url_encode_unicode(s: Optional[str]) -> Optional[str]:
        """
        URL-encode a string with Unicode support
        Similar to JavaScript's encodeURIComponent()
        """
        if s is None:
            return None

        result = []
        for char in s:
            cp = ord(char)
            if cp <= 0x7F:  # ASCII
                if EncodeUtil.is_safe(char):
                    result.append(char)
                elif char == ' ':
                    result.append('+')
                else:
                    result.append('%')
                    result.append(EncodeUtil.int_to_hex((cp >> 4) & 0xF))
                    result.append(EncodeUtil.int_to_hex(cp & 0xF))
            else:  # Unicode
                result.append('%u')
                result.append(EncodeUtil.int_to_hex((cp >> 12) & 0xF))
                result.append(EncodeUtil.int_to_hex((cp >> 8) & 0xF))
                result.append(EncodeUtil.int_to_hex((cp >> 4) & 0xF))
                result.append(EncodeUtil.int_to_hex(cp & 0xF))
        return ''.join(result)

    @staticmethod
    def get_secret(num: int) -> str:
        chars = string.ascii_letters + string.digits  # equivalent to "abcdef...6789"
        return ''.join(random.choice(chars) for _ in range(num))
