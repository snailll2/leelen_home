"""网关 `msg_storage_common_tbl` 电能行缓存与官方 App 一致的 kWh 算法。

数据来源是网关配置同步(FetchModConfigLanProtocol 全表/增量)推送的
``msg_storage_common_tbl`` 行。每行由累计计数(rec_cont)与时间戳(rec_time)
标识,插入顺序即累计读数的时间序。

官方 App(`SmartSocketModel.java` + `CommonMsgDao.java`)的语义,逐一复刻:
- 累计计数 = 6 字节小端无符号整数(高位补 2 个 0 后按 long 读);
- 电耗 = 区间内「末行累计 − 首行累计」/ 10000 → kWh(负差钳 0);
- 今日(rec_type 22556,小时读数):今日 00:00 之后的所有行,首尾计数差,3 位小数;
- 本月(rec_type 22557,日读数):本月 1 日之后的行按天分组,每组取相邻计数差的
  最后一对(官方循环是覆盖式),当日桶用「今日值」覆盖,求和,1 位小数。
- `rec_time` 为 `"yyyy-MM-dd HH:mm:ss"`,过滤为字符串单边比较;
  `link_target_code == 插座的逻辑地址(did)`(link_target_type 不参与)。

纯数据 + 纯算法(无 hass/无 IO),可直接单测;`now` 参数便于注入固定时间。
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from ..common.SingletonMixin import SingletonMixin

#: 需要缓存的 rec_type(与 FunctionType.FUNCTION_SMART_SOCKET_*_POWER 对齐)。
_ENERGY_REC_TYPES = (22556, 22557, 22558)
#: 累计计数与 kWh 之间的比例:1 kWh = 10000。
_KWH_SCALE = 10000


class MsgStorageModel(SingletonMixin):
    """电能行缓存:``(link_target_code, rec_type) -> {rec_time: 累计计数}``。"""

    def __init__(self):
        self._rows: dict[tuple[int, int], dict[str, int]] = {}

    def upsert(self, code, rec_type, rec_time: str, cont: bytes) -> None:
        """合并一行(重复 rec_time 视为同一行,后报到者覆盖)。

        ``cont`` 为 base64 解码后的 rec_cont 原始字节(BLOB)。
        """
        rec_type = int(rec_type)
        if rec_type not in _ENERGY_REC_TYPES:
            return
        self._rows.setdefault((int(code), rec_type), {})[rec_time] = self.six_byte_to_long(cont)

    @staticmethod
    def six_byte_to_long(cont: bytes) -> int:
        """6 字节小端累计计数 → int(官方 ``sixByteToLong`` 高位补 0 的语义)。"""
        if not cont:
            return 0
        return int.from_bytes(cont[:6].ljust(6, b"\x00"), "little")

    # ---- 对外查询 ----

    def codes_with_data(self) -> list[int]:
        """出现过任意电能行的 link_target_code(升序,用于按插座派发事件)。"""
        return sorted({code for code, _ in self._rows})

    def has_type(self, code, rec_type: int) -> bool:
        """该插座是否已缓存指定 rec_type 的行。"""
        return (int(code), int(rec_type)) in self._rows

    def today_energy(self, code, now: datetime | None = None) -> float:
        """今日电耗(kWh,3 位小数)。

        复刻 ``SmartSocketModel.getTodayElectricityData``:取 rec_type 22556
        且 rec_time 严格晚于今日 00:00:00 的行,首尾累计计数差 /10000;
        不足 2 行 → 0(官方 ``size()==1`` 也返回 0)。
        """
        now = now or datetime.now()
        boundary = now.strftime("%Y-%m-%d 00:00:00")
        rows = [
            (t, c) for t, c in self._rows.get((int(code), 22556), {}).items()
            if t > boundary
        ]
        if len(rows) < 2:
            return 0.0
        return self._real_val(rows[-1][1] - rows[0][1], 3)

    def month_energy(self, code, now: datetime | None = None) -> float:
        """本月电耗(kWh,1 位小数)。

        复刻 ``SmartSocketModel.getMonthElectricityData``:取 rec_type 22557
        且 rec_time 严格晚于本月 1 日 00:00:00 的行,按天分组(桶 d = 相邻行对
        ``(row_d, row_{d+1})`` 的计数差,每组取最后一对),「当日桶」用今日值
        (来自 22556)覆盖,各桶求和。负差在桶内已钳 0。
        """
        now = now or datetime.now()
        boundary = now.strftime("%Y-%m-01 00:00:00")
        rows = sorted(
            (t, c) for t, c in self._rows.get((int(code), 22557), {}).items()
            if t > boundary
        )

        buckets: dict[int, Decimal] = {}
        for i in range(len(rows) - 1):
            day = int(rows[i][0][8:10])  # rec_time 的「日」
            buckets[day] = self._kwh_decimal(rows[i + 1][1] - rows[i][1], 1)

        # 今日桶用今日值覆盖。注意:今日值是 scale-3 的 float,须经 str 转成精确
        # Decimal 再参与求和 —— 直接 Decimal(float) 会把浮点尾数(如 40.05 实际是
        # 40.0499...)带进来,最终舍入结果会跟着错。
        buckets[now.day] = Decimal(str(self.today_energy(code, now)))
        total = sum(buckets.values(), Decimal(0))
        # 官方求和后仍走 getRealVal(..., 1) 的 ROUND_HALF_UP;Python round 是
        # 银行家舍入(round(40.05, 1) == 40.0),这里必须用 Decimal 舍入。
        return float(total.quantize(Decimal(10) ** (-1), rounding=ROUND_HALF_UP))

    # ---- 内部工具 ----

    @classmethod
    def _kwh_decimal(cls, delta: int, scale: int) -> Decimal:
        """累计差 → kWh(Decimal,scale 位 ROUND_HALF_UP)。负差(计数回拨)钳 0。"""
        if delta < 0:
            return Decimal(0)
        q = Decimal(10) ** (-scale)
        return (Decimal(delta) / Decimal(_KWH_SCALE)).quantize(q, rounding=ROUND_HALF_UP)

    @classmethod
    def _real_val(cls, delta: int, scale: int) -> float:
        """累计差 → kWh(float)。官方 ``getRealVal``:负值钳 0、``/10000``、
        按 scale 位 ``ROUND_HALF_UP``(Python ``round`` 是银行家舍入,不能用)。"""
        return float(cls._kwh_decimal(delta, scale))