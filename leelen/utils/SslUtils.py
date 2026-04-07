import binascii
import logging
import ssl
import tempfile
import traceback
from ssl import SSLContext

# import jks  # 用于解析 BKS 文件
from OpenSSL import crypto
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import pkcs12

from .ConvertUtils import ConvertUtils
from .LogUtils import LogUtils


#
# def load_bks_ca(bks_path: str, password: str) -> str:
#     ks = jks.bks.BksKeyStore.load(bks_path, password)
#
#     with tempfile.NamedTemporaryFile(mode="w", delete=False) as ca_file:
#         for alias, entry in ks.entries.items():
#             if isinstance(entry, jks.TrustedCertEntry):
#                 cert = load_der_x509_certificate(entry.cert)
#                 # 确保使用 PEM 编码并添加换行符
#                 pem = cert.public_bytes(Encoding.PEM).decode("utf-8")
#                 ca_file.write(pem + "\n")  # 多个证书用换行分隔
#                 LogUtils.d(pem)
#         ca_path = ca_file.name
#     return ca_path

#
# def load_pkcs12(p12_data: bytes, password: str):
#     """加载 PKCS12 证书并返回私钥和证书链"""
#     private_key, cert, additional_certs = pkcs12.load_key_and_certificates(
#         p12_data,
#         password.encode('utf-8'),
#         # backend=serialization.
#     )
#     return private_key, additional_certs

#
# def configure_ssl_context(p12_path: str, password: str):
#     """配置 SSL 上下文"""
#     # 读取 PKCS12 文件
#     with open(p12_path, "rb") as f:
#         p12_data = f.read()
#
#     # 解析 PKCS12
#     private_key, cert_chain = load_pkcs12(p12_data, password)
#
#     # 创建临时文件
#     with tempfile.NamedTemporaryFile(delete=False) as keyfile, \
#             tempfile.NamedTemporaryFile(delete=False) as certfile:
#         # 写入私钥（PEM 格式）
#         # keyfile.write(private_key.private_bytes(
#         #     encoding=serialization.Encoding.PEM,
#         #     format=serialization.PrivateFormat.PKCS8,
#         #     encryption_algorithm=serialization.NoEncryption()
#         # ))
#
#         # 写入证书链（PEM 格式）
#         for cert in cert_chain:
#             certfile.write(cert.public_bytes(
#                 encoding=serialization.Encoding.PEM
#             ))
#
#     # 创建 SSL 上下文
#     # context = SSL.Context(SSL.TLSv1_2_METHOD)
#     #
#     # # 加载证书链和私钥
#     # context.use_certificate_chain_file(certfile.name)
#     # context.use_privatekey_file(keyfile.name)
#     #
#     # # 加载信任链（可选）
#     # context.load_verify_locations(cafile=certfile.name)  # 使用相同的证书链
#
#     # 清理临时文件
#     # os.unlink(keyfile.name)
#     # os.unlink(certfile.name)
#
#     # return context
#

class SslUtils:
    CLIENT_AGREEMENT = "TLSv1.2"
    CLIENT_KEY_MANAGER = "X509"
    CLIENT_KEY_P12 = "PKCS12"
    CLIENT_TRUST_KEYSTORE = "BKS"  # Note: BKS is Java-specific, we'll use PEM in Python
    TAG = "SslUtils"

    #
    # @staticmethod
    # def get_lan_socket_ssl_context3(
    #         client_p12_hex: str,  # 客户端 PKCS12 证书的 HEX 字符串
    #         client_p12_password: str,  # 客户端 PKCS12 的密码
    #         bks_truststore_hex: str,  # BKS 信任库的 HEX 字符串
    #         bks_truststore_password: str  # BKS 信任库的密码
    # ) -> ssl.SSLContext:
    #     try:
    #         # 1. 加载客户端 PKCS12 证书（HEX 转换）
    #         client_p12_bytes = bytes.fromhex(client_p12_hex)
    #         (
    #             private_key,
    #             client_cert,
    #             additional_certs
    #         ) = pkcs12.load_key_and_certificates(
    #             client_p12_bytes,
    #             client_p12_password.encode(),
    #             backend=default_backend()
    #         )
    #
    #         # 2. 加载 BKS 信任库（HEX 转换）
    #         bks_bytes = bytes.fromhex(bks_truststore_hex)
    #         bks_truststore = jks.KeyStore.loads(
    #             bks_bytes,
    #             bks_truststore_password,
    #             # "BKS"
    #         )
    #
    #         # 3. 提取 BKS 中的 CA 证书为 PEM 格式
    #         trusted_certs = []
    #         for alias, cert in bks_truststore.certs.items():
    #             pem_cert = f"-----BEGIN CERTIFICATE-----\n{cert.cert}\n-----END CERTIFICATE-----"
    #             trusted_certs.append(pem_cert.encode())
    #
    #         # 4. 创建 SSL 上下文
    #         context = SSLContext(PROTOCOL_TLS_CLIENT)
    #         context.check_hostname = False  # 根据需求调整
    #         context.verify_mode = ssl.CERT_REQUIRED
    #
    #         # 5. 加载客户端证书和私钥
    #         context.load_cert_chain(
    #             certfile=client_cert.public_bytes(serialization.Encoding.PEM),
    #             keyfile=private_key.private_bytes(
    #                 encoding=serialization.Encoding.PEM,
    #                 format=serialization.PrivateFormat.PKCS8,
    #                 encryption_algorithm=serialization.NoEncryption()
    #             )
    #         )
    #
    #         # 6. 加载信任的 CA 证书
    #         for cert_pem in trusted_certs:
    #             context.load_verify_locations(cadata=cert_pem)
    #
    #         return context
    #
    #     except Exception as e:
    #         logging.exception("SSL Context creation failed")
    #         raise RuntimeError("Failed to create SSL context") from e

    @staticmethod
    def get_lan_socket_ssl_context(p12_hex: str, p12_password: str, bks_hex: str, bks_password: str) -> ssl.SSLContext:
        try:
            # 1. 解析 P12 数据
            p12_data = binascii.unhexlify(p12_hex)
            private_key, cert, additional_certs = pkcs12.load_key_and_certificates(
                data=p12_data,
                password=p12_password.encode()
            )

            # 2. 创建临时 PEM 文件保存 key + cert
            key_pem = crypto.dump_privatekey(crypto.FILETYPE_PEM, crypto.PKey.from_cryptography_key(private_key))
            cert_pem = crypto.dump_certificate(crypto.FILETYPE_PEM, crypto.X509.from_cryptography(cert))
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as key_file, tempfile.NamedTemporaryFile(mode="w",
                                                                                                              delete=False) as cert_file, tempfile.NamedTemporaryFile(
                mode="w", delete=False) as ca_cert_temp:
                key_file.write(key_pem.decode("utf-8"))
                key_file.flush()
                cert_file.write(cert_pem.decode("utf-8"))
                cert_file.flush()

                bks_data = ConvertUtils.hex_to_bytes2(bks_hex)
                # with open("/Users/snail/Desktop/立林智慧生活项目/leelen_python/test/my.p12", "rb") as fff:
                #     ddd = fff.read()
                #     print(ddd.hex())
                # p12 = crypto.load_pkcs12(p12_data, bks_password.encode())
                private_key, cert, additional_certs = pkcs12.load_key_and_certificates(
                    bks_data,
                    bks_password.encode() if bks_password else None,
                    backend=default_backend()
                )
                if not additional_certs:
                    LogUtils.e("❌ P12 中没有 CA 证书链")
                    raise ValueError("❌ P12 中没有 CA 证书链")

                # 写入临时 PEM 文件
                # ca_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")
                for ca_cert in additional_certs:
                    ca_cert_temp.write(ca_cert.public_bytes(encoding=Encoding.PEM).decode("utf-8") + "\n")
                ca_cert_temp.flush()

                # bks_truststore = jks.bks.BksKeyStore.loads(bks_data, bks_password)
                # #
                # #
                # #
                # for alias, entry in bks_truststore.entries.items():
                #     if isinstance(entry, jks.TrustedCertEntry):
                #         cert = load_der_x509_certificate(entry.cert)
                #         # 确保使用 PEM 编码并添加换行符
                #         pem = cert.public_bytes(Encoding.PEM).decode("utf-8")
                #         ca_cert_temp.write(pem + "\n")  # 多个证书用换行分隔
                #         # LogUtils.d(pem)
                #         ca_cert_temp.flush()

                # 4. 创建 SSLContext
                # LogUtils.d(key_file.name)
                # LogUtils.d(cert_file.name)
                # LogUtils.d(ca_cert_temp.name)

                context = SSLContext(ssl.PROTOCOL_TLSv1_2)
                # context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_REQUIRED
                # context.minimum_version = ssl.TLSVersion.TLSv1_2
                # context.maximum_version = ssl.TLSVersion.TLSv1_3
                # context.set_ciphers('ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256')
                context.options |= ssl.OP_NO_COMPRESSION
                context.set_ciphers("AES256-GCM-SHA384")
                context.load_cert_chain(certfile=cert_file.name, keyfile=key_file.name)
                context.load_verify_locations(cafile=ca_cert_temp.name)

                return context
        except Exception as e:
            traceback.print_exc()
            LogUtils.d(f"[{SslUtils.TAG}] get_lan_socket_ssl_context() exception: {e}")
            raise

    @staticmethod
    def get_no_verifier_https_socket_factory() -> ssl.SSLContext:
        """Creates an SSL context that doesn't verify certificates (INSECURE - for testing only)"""
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        except Exception as e:
            logging.error(f"{SslUtils.TAG}: Error creating no-verifier SSL context: {str(e)}")
            raise RuntimeError("Failed to create no-verifier SSL context") from e


class SslParams:
    def __init__(self):
        self.ssl_socket_factory = None
        self.trust_manager = None
