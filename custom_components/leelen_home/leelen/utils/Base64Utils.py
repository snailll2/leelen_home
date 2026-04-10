import base64


class Base64Utils:
    @staticmethod
    def decode(encoded_str):
        return base64.b64decode(encoded_str).decode("utf-8")
