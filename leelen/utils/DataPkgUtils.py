from ..common import LeelenConst
from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..protocols.BaseWanProtocol import BaseWanProtocol
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils


class DataPkgUtils:
    BYTEBUFFER_SIZE = 5242880
    BYTE_BUF_DOWNLOAD = bytearray(5242880)
    BYTE_BUF_LAN = bytearray(5242880)
    BYTE_BUF_SUB_LAN = bytearray(5120)
    BYTE_BUF_WAN = bytearray(5242880)
    TAG = "DataPkgUtils"
    used_download = 0
    used_lan = 0
    used_sub_lan = 0
    used_wan = 0

    @staticmethod
    def clear_download_data():
        DataPkgUtils.BYTE_BUF_DOWNLOAD[0:] = bytearray(0)
        DataPkgUtils.used_download = 0

    @staticmethod
    def clear_lan_data():
        DataPkgUtils.BYTE_BUF_LAN[0:] = bytearray(0)
        DataPkgUtils.used_lan = 0

    @staticmethod
    def clear_sub_lan_data():
        DataPkgUtils.BYTE_BUF_SUB_LAN[0:] = bytearray(0)
        DataPkgUtils.used_sub_lan = 0

    @staticmethod
    def clear_wan_data():
        DataPkgUtils.BYTE_BUF_WAN[0:] = bytearray(0)
        DataPkgUtils.used_wan = 0

    @staticmethod
    def pull_download():
        result = []
        while True:
            protocol = DataPkgUtils.pull_single_download()
            if protocol is None:
                return result
            result.append(protocol)

    @staticmethod
    def pull_lan():
        result = []
        while True:
            protocol = DataPkgUtils.pull_single_lan()
            if protocol is None:
                return result
            result.append(protocol)

    @staticmethod
    def pull_single_download():
        try:
            size = DataPkgUtils.used_download
            if size == 0:
                return None
            elif size < 0:
                DataPkgUtils.used_download = 0
                return None

            data = bytearray(size)
            data[0:size] = DataPkgUtils.BYTE_BUF_DOWNLOAD[0:size]
            if DataPkgUtils.used_download < 42:
                return None

            header = bytearray(4)
            i = 0
            while True:
                if (header == LeelenConst.LAN_SYNC_HEADER or
                        i > DataPkgUtils.used_download - 4):
                    break
                header[0:4] = DataPkgUtils.BYTE_BUF_DOWNLOAD[i:i + 4]
                i += 1

            if header != LeelenConst.LAN_SYNC_HEADER:
                DataPkgUtils.used_download = 0
                return None

            offset = i - 1
            size = DataPkgUtils.used_download - offset
            temp = bytearray(size)
            temp[0:size] = DataPkgUtils.BYTE_BUF_DOWNLOAD[offset:offset + size]

            if offset > 0:
                DataPkgUtils.BYTE_BUF_DOWNLOAD[0:size] = temp[0:size]
                DataPkgUtils.used_download = size

            if size < 42:
                return None

            length_bytes = bytearray(4)
            length_bytes[0:4] = DataPkgUtils.BYTE_BUF_DOWNLOAD[4:8]
            length = ConvertUtils.to_int(length_bytes)
            if length > len(DataPkgUtils.BYTE_BUF_DOWNLOAD):
                DataPkgUtils.used_download = 0
                return None

            total = length + 8
            if total > DataPkgUtils.used_download:
                return None

            protocol_data = bytearray(total)
            protocol_data[0:total] = DataPkgUtils.BYTE_BUF_DOWNLOAD[0:total]
            protocol = BaseLanProtocol.parse(protocol_data)
            remaining = DataPkgUtils.used_download - total

            if remaining > 0:
                temp = bytearray(remaining)
                temp[0:remaining] = DataPkgUtils.BYTE_BUF_DOWNLOAD[total:total + remaining]
                DataPkgUtils.BYTE_BUF_DOWNLOAD[0:remaining] = temp[0:remaining]
                DataPkgUtils.used_download = remaining
            else:
                DataPkgUtils.used_download = 0

            return protocol

        except Exception as e:
            LogUtils.d(e)
            return None

    @staticmethod
    def pull_single_lan():
        try:
            size = DataPkgUtils.used_lan
            if size == 0:
                return None
            elif size < 0:
                DataPkgUtils.used_lan = 0
                return None

            data = bytearray(size)
            data[0:size] = DataPkgUtils.BYTE_BUF_LAN[0:size]
            if DataPkgUtils.used_lan < 42:
                return None

            header = bytearray(4)
            i = 0
            while True:
                if (header == LeelenConst.LAN_SYNC_HEADER or
                        i > DataPkgUtils.used_lan - 4):
                    break
                header[0:4] = DataPkgUtils.BYTE_BUF_LAN[i:i + 4]
                i += 1

            if header != LeelenConst.LAN_SYNC_HEADER:
                DataPkgUtils.used_lan = 0
                return None

            offset = i - 1
            size = DataPkgUtils.used_lan - offset
            temp = bytearray(size)
            temp[0:size] = DataPkgUtils.BYTE_BUF_LAN[offset:offset + size]

            if offset > 0:
                DataPkgUtils.BYTE_BUF_LAN[0:size] = temp[0:size]
                DataPkgUtils.used_lan = size

            if size < 42:
                return None

            length_bytes = bytearray(4)
            length_bytes[0:4] = DataPkgUtils.BYTE_BUF_LAN[4:8]
            length = ConvertUtils.to_int(length_bytes)
            if length > len(DataPkgUtils.BYTE_BUF_LAN):
                DataPkgUtils.used_lan = 0
                return None

            total = length + 8
            if total > DataPkgUtils.used_lan:
                return None

            protocol_data = bytearray(total)
            protocol_data[0:total] = DataPkgUtils.BYTE_BUF_LAN[0:total]
            protocol = BaseLanProtocol.parse(protocol_data)
            remaining = DataPkgUtils.used_lan - total

            if remaining > 0:
                temp = bytearray(remaining)
                temp[0:remaining] = DataPkgUtils.BYTE_BUF_LAN[total:total + remaining]
                DataPkgUtils.BYTE_BUF_LAN[0:remaining] = temp[0:remaining]
                DataPkgUtils.used_lan = remaining
            else:
                DataPkgUtils.used_lan = 0

            return protocol

        except Exception as e:
            LogUtils.d(e)
            return None

    @staticmethod
    def pull_single_sub_lan():
        try:
            size = DataPkgUtils.used_sub_lan
            if size == 0:
                return None
            elif size < 0:
                DataPkgUtils.used_sub_lan = 0
                return None

            data = bytearray(size)
            data[0:size] = DataPkgUtils.BYTE_BUF_SUB_LAN[0:size]
            if DataPkgUtils.used_sub_lan < 42:
                return None

            header = bytearray(4)
            i = 0
            while True:
                if (header == LeelenConst.LAN_SYNC_HEADER or
                        i > DataPkgUtils.used_sub_lan - 4):
                    break
                header[0:4] = DataPkgUtils.BYTE_BUF_SUB_LAN[i:i + 4]
                i += 1

            if header != LeelenConst.LAN_SYNC_HEADER:
                DataPkgUtils.used_sub_lan = 0
                return None

            offset = i - 1
            size = DataPkgUtils.used_sub_lan - offset
            temp = bytearray(size)
            temp[0:size] = DataPkgUtils.BYTE_BUF_SUB_LAN[offset:offset + size]

            if offset > 0:
                DataPkgUtils.BYTE_BUF_SUB_LAN[0:size] = temp[0:size]
                DataPkgUtils.used_sub_lan = size

            if size < 42:
                return None

            length_bytes = bytearray(4)
            length_bytes[0:4] = DataPkgUtils.BYTE_BUF_SUB_LAN[4:8]
            length = ConvertUtils.to_int(length_bytes)
            if length > len(DataPkgUtils.BYTE_BUF_SUB_LAN):
                DataPkgUtils.used_sub_lan = 0
                return None

            total = length + 8
            if total > DataPkgUtils.used_sub_lan:
                return None

            protocol_data = bytearray(total)
            protocol_data[0:total] = DataPkgUtils.BYTE_BUF_SUB_LAN[0:total]
            protocol = BaseLanProtocol.parse(protocol_data)
            remaining = DataPkgUtils.used_sub_lan - total

            if remaining > 0:
                temp = bytearray(remaining)
                temp[0:remaining] = DataPkgUtils.BYTE_BUF_SUB_LAN[total:total + remaining]
                DataPkgUtils.BYTE_BUF_SUB_LAN[0:remaining] = temp[0:remaining]
                DataPkgUtils.used_sub_lan = remaining
            else:
                DataPkgUtils.used_sub_lan = 0

            return protocol

        except Exception as e:
            LogUtils.d(e)
            return None

    @staticmethod
    def pull_single_wan():
        try:
            size = DataPkgUtils.used_wan
            if size == 0:
                return None
            elif size < 0:
                DataPkgUtils.used_wan = 0
                return None

            data = bytearray(size)
            data[0:size] = DataPkgUtils.BYTE_BUF_WAN[0:size]
            if DataPkgUtils.used_wan < 36:
                return None

            header = bytearray(3)
            i = 0
            while True:
                if (header == LeelenConst.WAN_SYNC_HEADER or
                        i > DataPkgUtils.used_wan - 3):
                    break
                header[0:3] = DataPkgUtils.BYTE_BUF_WAN[i:i + 3]
                i += 1

            if header != LeelenConst.WAN_SYNC_HEADER:
                DataPkgUtils.used_wan = 0
                return None

            offset = i - 1
            size = DataPkgUtils.used_wan - offset
            temp = bytearray(size)
            temp[0:size] = DataPkgUtils.BYTE_BUF_WAN[offset:offset + size]

            if offset > 0:
                DataPkgUtils.BYTE_BUF_WAN[0:size] = temp[0:size]
                DataPkgUtils.used_wan = size

            if size < 36:
                return None

            length_bytes = bytearray(4)
            length_bytes[0:4] = DataPkgUtils.BYTE_BUF_WAN[13:17]
            length = ConvertUtils.to_int(length_bytes)
            if length > len(DataPkgUtils.BYTE_BUF_WAN):
                DataPkgUtils.used_wan = 0
                return None

            if length > DataPkgUtils.used_wan:
                return None

            protocol_data = bytearray(length)
            protocol_data[0:length] = DataPkgUtils.BYTE_BUF_WAN[0:length]
            protocol = BaseWanProtocol.parse(protocol_data)

            if protocol is None:
                length = 36

            remaining = DataPkgUtils.used_wan - length
            if remaining > 0:
                temp = bytearray(remaining)
                temp[0:remaining] = DataPkgUtils.BYTE_BUF_WAN[length:length + remaining]
                DataPkgUtils.BYTE_BUF_WAN[0:remaining] = temp[0:remaining]
                DataPkgUtils.used_wan = remaining
            else:
                DataPkgUtils.used_wan = 0

            return protocol

        except Exception as e:
            LogUtils.d(e)
            return None

    @staticmethod
    def pull_sub_lan():
        result = []
        while True:
            protocol = DataPkgUtils.pull_single_sub_lan()
            if protocol is None:
                return result
            result.append(protocol)

    @staticmethod
    def pull_wan():
        result = []
        while True:
            protocol = DataPkgUtils.pull_single_wan()
            if protocol is None:
                return result
            result.append(protocol)

    @staticmethod
    def push_download(data):
        if data is None:
            LogUtils.w(DataPkgUtils.TAG, "no download data to push.")
            return

        if len(data) <= DataPkgUtils.BYTEBUFFER_SIZE:
            if len(data) > DataPkgUtils.BYTEBUFFER_SIZE - DataPkgUtils.used_download:
                DataPkgUtils.used_download = 0

            DataPkgUtils.BYTE_BUF_DOWNLOAD[DataPkgUtils.used_download:DataPkgUtils.used_download + len(data)] = data
            DataPkgUtils.used_download += len(data)

    @staticmethod
    def push_lan(data):
        if data is None:
            LogUtils.w(DataPkgUtils.TAG, "no data to push.")
            return

        if len(data) <= DataPkgUtils.BYTEBUFFER_SIZE:
            if len(data) > DataPkgUtils.BYTEBUFFER_SIZE - DataPkgUtils.used_lan:
                DataPkgUtils.used_lan = 0

            DataPkgUtils.BYTE_BUF_LAN[DataPkgUtils.used_lan:DataPkgUtils.used_lan + len(data)] = data
            DataPkgUtils.used_lan += len(data)

    @staticmethod
    def push_sub_lan(data):
        if data is None:
            LogUtils.w(DataPkgUtils.TAG, "no data to push.")
            return

        if len(data) <= DataPkgUtils.BYTEBUFFER_SIZE:
            if len(data) > DataPkgUtils.BYTEBUFFER_SIZE - DataPkgUtils.used_sub_lan:
                DataPkgUtils.used_sub_lan = 0

            DataPkgUtils.BYTE_BUF_SUB_LAN[DataPkgUtils.used_sub_lan:DataPkgUtils.used_sub_lan + len(data)] = data
            DataPkgUtils.used_sub_lan += len(data)

    @staticmethod
    def push_wan(data):
        if data is None:
            return

        if len(data) <= DataPkgUtils.BYTEBUFFER_SIZE:
            if len(data) > DataPkgUtils.BYTEBUFFER_SIZE - DataPkgUtils.used_wan:
                DataPkgUtils.used_wan = 0

            DataPkgUtils.BYTE_BUF_WAN[DataPkgUtils.used_wan:DataPkgUtils.used_wan + len(data)] = data
            DataPkgUtils.used_wan += len(data)
