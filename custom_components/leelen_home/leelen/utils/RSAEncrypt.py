import base64
import logging

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding


class RSAEncrypt:
    CHARSET = "UTF-8"
    TAG = "RSAEncrypt"

    @staticmethod
    def decrypt(encrypted_data: str, private_key_str: str) -> str:
        try:
            # Decode base64 encrypted data
            encrypted_bytes = base64.b64decode(encrypted_data.encode(RSAEncrypt.CHARSET))

            # Load private key
            private_key = serialization.load_pem_private_key(
                base64.b64decode(private_key_str),
                password=None,
                backend=default_backend()
            )

            # Decrypt
            decrypted = private_key.decrypt(
                encrypted_bytes,
                padding.PKCS1v15()
            )
            return decrypted.decode(RSAEncrypt.CHARSET)
        except Exception as e:
            logging.error(f"{RSAEncrypt.TAG} decrypt Exception: {str(e)}")
            return ""

    @staticmethod
    def rsa_encrypt(data: str, public_key_b64: str) -> str:
        """
        RSA 加密 (对应 Java 的 RSA/ECB/PKCS1Padding 模式)

        参数:
            data: 要加密的原始字符串
            public_key_b64: Base64 编码的 X.509 DER 格式公钥

        返回:
            Base64 编码的加密结果字符串
        """
        try:
            # 1. Base64 解码公钥
            der_bytes = base64.b64decode(public_key_b64)

            # 2. 加载 DER 格式公钥
            public_key = serialization.load_der_public_key(
                der_bytes,
                backend=default_backend()
            )

            # 3. 使用 PKCS1v15 填充进行加密
            encrypted_bytes = public_key.encrypt(
                data.encode('utf-8'),
                padding.PKCS1v15()
            )

            # 4. 将加密结果转为 Base64 字符串
            return base64.b64encode(encrypted_bytes).decode('utf-8')

        except Exception as e:
            logging.error(f"[RSAEncrypt] encrypt Exception: {str(e)}", exc_info=True)
            return ""

    @staticmethod
    def encrypt(data: str, public_key_str: str) -> str:
        try:
            # Load public key
            public_key = serialization.load_pem_public_key(
                base64.b64decode(public_key_str),
                backend=default_backend()
            )

            # Encrypt
            encrypted = public_key.encrypt(
                data.encode(RSAEncrypt.CHARSET),
                padding.PKCS1v15()
            )
            return base64.b64encode(encrypted).decode(RSAEncrypt.CHARSET)
        except Exception as e:
            logging.error(f"{RSAEncrypt.TAG} encrypt Exception: {str(e)}")
            return ""

    @staticmethod
    def gen_key_pair() -> dict:
        try:
            # Generate key pair
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            # Get public key
            public_key = private_key.public_key()

            # Serialize keys
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )

            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            # Base64 encode
            return {
                "publicKey": base64.b64encode(public_pem).decode(RSAEncrypt.CHARSET),
                "privateKey": base64.b64encode(private_pem).decode(RSAEncrypt.CHARSET)
            }
        except Exception as e:
            logging.error(f"{RSAEncrypt.TAG} gen_key_pair Exception: {str(e)}")
            return {"publicKey": "", "privateKey": ""}
