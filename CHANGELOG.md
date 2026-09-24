# 更新日志 / Changelog

## V1.2.2 (2026-09-24)

### ✨ New features

- **网关属性实体** — 网关(`dev_addr=0`,名「Zigbee无线网关」)新增传感器实体,每个已上报属性一个:
  `主版本` / `软件版本` / `IP地址` / `MAC地址` / `WiFi名称`。值取自网关 `property_tbl addr=0` 行,
  只有设备库里有的属性才建(老固件属性少 → 实体少),值随「同步设备」刷新。
- **网关在线 binary_sensor** — `Zigbee无线网关 在线`:状态即链路是否已登录(`gateway_link_up()`),
  断链自动翻 `off`,恢复 `on`;与网关的 V设备(VSwitch)归入**同一设备注册条目** —— 这正是修复
  「两台 Zigbee无线网关」的关键:此前网关属性实体把 `dev_addr` 强转成字符串,`("LEELEN_HOME", 0)`
  与 `("LEELEN_HOME", "0")` 被设备注册表当成两台设备,现已与全平台统一为库内 int 类型。
- **设备固件版本 → 设备注册表「固件」字段** — 每台设备的固件版本(`dev_tbl.soft_version` 前 3 字节,
  e.g. `01 07 01…` → `1.7.1`)写入 HA 设备注册表 `sw_version`;网关自身该列未上报(全 `FF`)→ 不显示。
  `HttpApi.query_devices` 的 `dev_tbl` SELECT 补上了此前漏掉的 `soft_version` 列。
- **(推迟)面板「开关指示灯」** —— 协议层(仓库 / dump.db / Java 参考 / 公开资料)均无对应
  function_id / property_id,待抓到真实帧后再实现,不臆造。
- **Button 平台:设备定位 + 窗帘电机方向/重置行程** — 新增 `button.py` 按钮平台:
  - **设备定位**(每台可定位物理设备一个,面板/插座/窗帘都建):按下下发官方
    DEVICE_HINT + 闪烁指令,设备指示灯闪约 30 秒 —— 与官方 App「设备定位」按钮一致,
    按物理地址寻址,不依赖属性 136(`leelen_device_locate_{dev_addr}`)。
  - **窗帘电机「更改方向」**(每条持有可写方向属性 163 的窗帘电机通道一个):按下翻转
    电机方向,写属性 `0x01A3` 值 `1 − 当前方向`(bit0=方向)。
  - **窗帘电机「重置行程」**(同通道):按下重新触发行程学习,写属性 `0x01A3` 值
    `当前方向 + 2`(bit1=触发重置,方向位保留)。
  - 两个窗帘按钮走 **App 设备透传指令**(`cmd [1,6]`,逆向自官方 APK
    `BaseManagerImpl.appDevicePassThrough`,非 DEV_CTRL TLV);目标地址是**逻辑通道地址**
    —— dump.db 实测电机可写属性挂在 logic_addr(dev 224/240 → logic 225/241),不在
    dev_addr 上;与更改方向按钮共享方向状态,先改方向再重置会带上新方向
    (`leelen_curtain_motor_direction_{logic_addr}` / `leelen_curtain_motor_reset_{logic_addr}`)。

### 🐛 Fixes

- **两台「Zigbee无线网关」** — 网关属性/在线实体此前用 `str(dev_addr)` 作 device_id,与
  switch 等平台(`int`)不一致,导致设备注册表把同一网关拆成两个设备条目;统一为 int 类型后合并。

### 🧪 Tests

- 新增 `tests/test_gateway_entity.py`(12 项):`_build_entities` 网关分支(5 属性 + 1 在线、
  unique_id / native_value / name)、缺属性不建实体、在线 `is_on` 随链路翻转、非网关设备不产网关实体、
  `decode_soft_version`(`01 07 01…`→1.7.1 / 全 FF→None / 空→None)、`device_info.sw_version` 注入、
  gateway unique_id 进 config_flow 清理白名单。
- `tests/test_integration.py` 新增 `test_gateway_entities_registered`:真实 HA 下断言 6 个网关实体已注册、
  网关在线实体归 int 标识的网关设备、面板设备注册表 `sw_version == "1.7.1"`、网关无版本。
- 新增 `tests/test_curtain_motor.py`(18 项):App 透传写帧字节钉死(body = `01 05 64 01 A3 01 xx`,
  头部 cmd `[1,6]` 位于 34:36)、`_build_entities` 门控(非窗帘/只读/无属性不建)、初始方向取属性
  163 现值 bit0、方向翻转与重置共享状态(`先翻方向再重置 → 带新方向位`)、经 HeartbeatService 全链路出帧、
  config_flow 清理白名单。
- 全量回归:**175 passed**。

### ✨ New features

- **插座功率与用电量统计** — 智能插座(`Switch`)实体新增三个 HA 标准属性:`current_power_w`(当前功率,W)、`today_energy_kwh`(今日用电)、`month_energy_kwh`(本月用电)。数据源为**实时 fetch 网关电能表**(`msg_storage_common_tbl`,登录即拉基线 + 每 10 分钟轮询),非 dump.db 快照。
  - 功率(`20517`):4 字节小端原始计数值 ×0.1 → 瓦特(官方 App 口径);长度 ≠ 4 的脏帧一律判 0。
  - 今日用电(`22556` 小时行)/ 本月用电(`22557` 日行):按官方 App `SmartSocketModel` 算法复刻 —— `sixByteToLong` 6 字节小端累计计数、首尾差 /10000、负差钳 0、`Decimal` `ROUND_HALF_UP`(非 Python `round` 银行家舍入);新增 `leelen/models/MsgStorageModel.py` 纯算法模块,可单测。
  - 新增 `service._start_energy_poll` 轮询任务(LAN/WAN 双模式覆盖)。旧 `_power_usage` 字段废弃。
  - **插座电参数升级为独立 sensor 实体**(Switch 标准属性保留,向后兼容):每台智能插座额外建 3 个页面可见的传感器 —— `current_power_w`(当前功率,W)、`today_energy_kwh`(今日用电)、`month_energy_kwh`(本月用电,均 kWh)。与 Switch 消费同一批 20517/22556/22557 事件(不另发请求);坚持按 `logic_type` 分派、`unique_id` 带功能后缀(Sensor 先于 Switch 建实体,裸 ID 会被 `_added_unique_ids` 判重),「同步设备」清理按后缀 ID 计数,不会误删新实体。
  - 支撑改动:`state_subscription._handle_state_event` 由 `unique_id` 字符串匹配改为按 `_logic_addr` 语义匹配(e0ae176 起),后缀实体才能收到事件;`config_flow._collect_expected_unique_ids` 把 3 个后缀 ID 计入 `all_entities`。能量设备类不设 `state_class`(周期快照值,避免 HA device_class/state_class 组合告警)。

### 🐛 Fixes

- **插座功率单位错误** — 原实现直接展示 20517 原始计数值,现按官方 App 修正为 ×0.1 瓦特;补 `len==4` 守卫,脏数据不再当功率。

### 🧪 Tests

- 新增 `tests/test_socket_energy.py`(24 项):`MsgStorageModel` 纯算法(首尾差 / 日桶覆盖 / 今日桶覆盖 / 负差钳 0 / 不足 2 行→0)、`AckToDao.trans_msg_storage_data` CSV 解析与事件派发、`CommonModel` 22556/22557 分支、`DeviceStateModel` len==4 守卫、`Switch.update_state` 属性落盘、`fetch_msg_storage_data` 请求参数。
- 新增 `tests/test_socket_sensor.py`(13 项):`_build_entities` 518 展开成 3 个 `SocketSensor`(unique_id 后缀 / device_class / 单位 / state_class)、`SocketSensor.update_state` 按 (kind, service_type) 分支、`_handle_state_event` 按逻辑地址匹配(后缀实体收到事件)、`config_flow._collect_expected_unique_ids` 含后缀 ID。集成测试追加 3 个 sensor 实体注册断言。全套 **102 项通过**。

## V1.2.0 (2026-09-23)

### ✨ New features

- **空调 / 新风 / 地暖三分类适配** — `climate.py` 从单一 `Climate` 类重写为 `AirConditioner` / `FreshAirFan` / `FloorHeatingClimate` 三个专用类。实体按 `logic_srv.logic_type`(逻辑类型)分派,不再按设备名(`dev_name`)写死匹配 —— 不针对任何一套房子设计,任意网关的同类设备都能正确建出专用实体。
  - `AirConditioner`(`146/658/770/773/778/782/242/157`):单帧携带 开关+模式+风速+目标温度,byte0=(风速<<5)|(温度-16)、byte1=(开关<<3)|模式。
  - `FreshAirFan`(`771/774/777/780/783/148/152/664`):level 0/1/2/3/0xFE = 关/低/中/高/自动,单字节载荷。
  - `FloorHeatingClimate`(`772/775/776/779/150/662`):电源位 = 状态字节 **bit4**(0x10,官方 App `subByte(b1,4,6)` 确认);调温只发温度帧、开关帧置位 bit4,互不误伤。
- **兼容更多官方逻辑类型** — `CLIMATE_LOGIC_TYPES` 补全为官方全集(新增 773/778/779/780/782/783/148/150/152/242/157/662/664),此前只在官方 App 出现的设备类型现在也能建出实体。
- **尊重网关 `display` 清单** — `display=0` 的逻辑服务(官方 App 里被隐藏的面板重复通道)不再建实体,与官方 App 展示一致;对普通网关(display 恒为 1)零影响。

### 🐛 Fixes

- **地暖电源位解析错误** — `CommonModel.get_cur_floor_heating_state` 误读 bit0,按官方 App 修正为 bit4(0x10)。
- **空调/地暖控制功能码缺映射** — 658(ZigBee 中心空调)此前落到默认 `FUNCTION_ON_OFF`(51201),现并入 55297 分支;776(地板加热器)并入 51213 分支。773/778→51232、774/780→49185、775/779→51234 均按官方 App 全集确认(移除不存在的 51235 依赖)。
- **`get_cur_state` 路由缺功能码** — 51232(空调执行器)/49156(新风档位)/51213(地暖加热)三个功能码未路由到对应解析器,会退回通用开关状态,现补全。
- **`HVACMode.AUTO` 映射缺失** — `HVAC_MODE_MAP` 补 `AUTO: 4`(此前 `_attr_hvac_modes` 含 AUTO 而映射缺它,AUTO 会悄悄落成 0)。

### 🧪 Tests

- 新增 `tests/test_climate_adaptation.py`(20 项):地暖 bit4 解析、658/776 功能码、空调字节编码(`power=1,COOL,HIGH,24℃` → `0x68/0x0A`)、新风 level→载荷/功能码映射、`_build_entities` 三分类分派与 display 过滤。全套 65 项通过。

## V1.1.1 (2026-09-18)

### 🐛 Fixes

- **All entities became `unavailable` after a restart** — the duplicate-entity guard added to `platform_helper` filtered against the *entity registry*, which is persisted across restarts. At startup that registry already contains every entity from the previous run, so the guard skipped **all** of them and the platforms provided nothing; HA then leaves the registry entries in the restored `unavailable` state. The guard now tracks the unique_ids added **during the current run** in memory (dropped with the entry on unload), which still suppresses the duplicate-`unique_id` ERROR spam when the user re-runs "Sync devices". Regression test: `test_setup_creates_entities_that_registry_already_knows` (fails with `state is None` under the old logic).
- **Gateway "config changed" notifications (LAN protocol 771) never worked** — `handle_config_modify_notify` referenced `ConnectLan` / `ConnectState` / `LogonState`, none of which were imported in that module, so every notification raised `NameError`, which the enclosing `except` swallowed (and logged through a misused `LogUtils.e(tag, msg)` call that printed a literal `%s`, hiding the real error). Combined with `Config.config_version` never being persisted (always `0`, so the version fast-path never matched), configuration changes made in the Leelen app after login were silently ignored until the next reconnect or manual sync. The path now resolves the live connection through `HeartbeatService.connect_lan` and, when the link is up, queries the gateway for config and pulls state; the Java reference's `downloadGatewayDb(true)` branch is documented as intentionally not performed from the receive thread.
- **V devices (VSwitch) could never report "off" from the device** — `CommonModel.get_v_switch_state` documented the payload (`\x01…` = on, `\x02…` = off) but mapped "off" to power_state `0`, while `VSwitch.update_state` only accepts `(1, 2)` as "this report carries a state". The off direction was therefore dropped, so the entity stayed stale unless a linked entity overrode it. "Off" now maps to `2` as the payload semantics require.
- **Same function indexed `state_bytes[0..3]` unconditionally in its debug log** — an empty or short ARM payload raised `IndexError` inside a lock and without a try (f-strings evaluate before the log level is checked). Byte-level logging is now length-guarded.
- **Singleton construction could deadlock permanently** — `SingletonMixin._singleton_lock` was defined on the base class, so *every* singleton shared one non-reentrant lock. `LanDataResponseHandleModel.__init__` calls `LanDataRequestModel.get_instance()` while holding it, which self-deadlocked (and would have frozen `get_instance()` for *all* singletons, not just those two). It only worked in production because instantiation order happened to create `LanDataRequestModel` first. Each subclass now gets its own lock via `__init_subclass__`.
- **LAN client private key was left on disk** — `SslUtils.get_lan_socket_ssl_context` wrote the p12 private key and certificates to `delete=False` temp files and never removed them, leaving a key PEM in `/tmp` per connection attempt. The files are now unlinked in a `finally` after OpenSSL has loaded them, and the TLS setup itself is documented (mutual TLS with a pinned CA; `check_hostname=False` because the gateway certificate's CN is not the LAN IP — not "verification disabled"). The deprecated `ssl.PROTOCOL_TLSv1_2` constant was replaced by explicit TLS 1.2 min/max pinning.
- **`LinCenterAcState.is_break_down` was both a dataclass field and a method** — the method was unreachable (instance lookup finds the field) and would have returned the field rather than a bool if called. Renamed to `get_break_down()`.

### 🔄 Refactor

- **`LanDataResponseHandleModel.py`: 1899 → 444 lines** — 1453 of those lines (85%) were the commented-out Java reference implementation. It moved verbatim to `docs/reference/LanDataResponseHandleModel.java.md` (kept for protocol semantics, now actually navigable) and each block leaves a one-line pointer. Verified line-by-line that the live code is unchanged apart from the 771 fix.
- **`ConnectLan.py`: 687 → 393 lines** — 84 of the 91 dispatch cases were stubs (log + `return`, with the Java call commented out). They are now a `UNHANDLED_RESPONSE_CMDS` table plus a single `case _` fallback; the 7 live cases and their log messages are preserved verbatim, and genuinely unknown command ids now log a WARNING instead of falling through silently.
- **`CommonModel.py`: 66 magic numbers replaced with the named constants that already existed** in `LeelenType` (`FunctionType.FUNCTION_ARM`, `LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER`, …). The handful of values with no name (`2/3/49/154`, AC temperature encoding, `51235`) got local named constants with comments. All 41 name↔value groups were verified equal to the original literals, so behavior is unchanged.
- **pyflakes is now clean across the whole component and test suite** (was 31 findings): removed 4 unreferenced modules (`entity/LogicServer.py`, `entity/ack/ConfigModAck.py`, `entity/req/BindGatewayReq.py`, `utils/Base64Utils.py`), unused imports and dead locals that only the commented-out Java referenced, 20 placeholder-less f-strings, and mis-typed `Optional[threading.Timer]` hints.
- Protocol header field-by-field parses that only needed a couple of fields became layout tables with a comment (`PassThroughWanProtocol`, `BaseLanProtocol`, `BaseWanProtocol`).
- `text.py` is not registered in `SUPPORTED_PLATFORMS` and never loads; its docstring now says so instead of leaving a reader guessing.
- `brand/icon.png` resized 512×512 (185 KB) → 128×128 (21 KB), with `brand/icon@2x.png` (256×256) added.
- New tests: `tests/test_protocol_layer.py` (11 cases) covers the VSwitch mapping, the 771 notify path, singleton lock independence (a hang there means the deadlock is back), and that `SslUtils` builds a working mutual-TLS context without leaving temp files.

### 🐛 Fixes (earlier in this release)

- **Gateway IP source is now decided by whether one is configured** — startup used to query `dump.db` unconditionally and only then let the `gateway_ip` option override the result. So even with an address configured, startup still depended on `dump.db` being readable (a missing/corrupt DB would fail setup — the exact situation the manual override exists to rescue), and the log showed the DB address, making it look like that value was in use. Now: configured → that address is used and `dump.db` is not read at all; not configured → falls back to the auto-detected value. The chosen source and address are logged, and an empty result warns that LAN mode cannot connect. The options page also no longer breaks when `dump.db` is unreadable.
- **`gateway_ip` options page had no title/description** — `options.step.gateway_ip` was missing from both `en.json` and `zh-Hans.json`, so the page rendered bare and its `{auto_ip}` placeholder (the auto-detected address) had nowhere to show. Added, describing the new precedence.
- **"Sync devices" always reported 1 added device** — the count compared *every* `dev_tbl` row against the HA device registry, but a device only gets a registry entry if some platform builds an entity for it. A gateway device can exist in the device DB with all of its logic channels filtered out (`query_devices` drops `srv_type = 0`), so it never gets an entry and was counted as "new" on every single sync. The count now only considers devices that have at least one channel a platform actually handles, and such devices are reported separately as **no controllable channel**.
- **Every sync logged one ERROR per existing entity** — `device_refresh` re-runs `setup_devices_from_db`, which rebuilt entities for *all* devices; the ones already registered hit a duplicate `unique_id` and HA logged `does not generate unique IDs ... already exists - ignoring` for each (tens of lines per sync on a real installation). Already-registered entities are now skipped before being added.
- **Deprecated device registry access** — the sync path iterated `device_registry.devices` as a mapping (deprecated, stops working in HA 2027.9); switched to `async_entries_for_config_entry`.
- **Options flow could not pick V devices reliably** — the "link entities" step listed *every* Leelen entity as a linkable V device (any `leelen_logic_addr_*` unique_id). Candidates are now resolved from the device DB (`LogicDeviceType.ARM`) and filtered by config entry; the light/socket/climate entities no longer show up.
- **VSwitch linked-entity listener was never unregistered** — `VSwitch` reused `_state_unsub`, the same handle name as its parent `StateUpdateSubscriber`, so registering the linked-entity listener silently overwrote the state-update subscription handle. Renamed to `_linked_state_unsub` and released in `async_will_remove_from_hass` (no more stale listeners after reload).
- **Linked-entity state was compared inconsistently** — the reverse path counted `on/open/locked` as "on" while the device-report override only accepted `on`, so a curtain/lock link would be forced to "off". Both paths now use the same `LINKED_ON_STATES` set.
- **Climate mode switch sent two control frames** — `async_set_hvac_mode` used to turn on (power frame) then send a second frame with mode/temperature; a failure in between could leave the unit in a half-applied state. Now a single frame carries power + mode + target temperature.
- **`turn_on` in climate lost the target temperature** — `set_setting_temperature` was called *after* `control()`, so the frame was packed without it.
- **Cloud requests had TLS verification disabled** — every request to `iot.leelen.com` / `rd.iot.leelen.com` passed `verify_ssl=False`, including the login calls that carry the account password. Verification is back on (the certificate validates normally).
- **`dump.db` was read/written via a CWD-relative path** — now always resolved with `hass.config.path()`, and downloaded to a temp file that is atomically renamed over the old copy, so a concurrent `aiosqlite` read can't see a half-written DB.
- **Options errors leaked raw exception text into the UI** — `errors[...]` must be translation keys; mapped to `send_code_failed` / `login_failed` / `refresh_failed` and added the missing keys (including the previously absent `options.error` section) to both `en.json` and `zh-Hans.json`.
- **Multi-entry cleanup could wipe a live entry** — unloading one entry popped the whole `DOMAIN` bucket once the device table emptied, and the gateway IP lived in a DOMAIN-wide key overwritten by each entry. Both are now entry-scoped.
- **SQL string interpolation** — device/property queries now use bound parameters.
- **Config entry data was logged verbatim** — `entry.data` (contains username/password) is no longer dumped to the log at setup.

### 🔄 Refactor

- New `entity_base.LeelenEntity` — the `unique_id` / `name` / `device_info` / `__init__` boilerplate repeated across light/sensor/cover/switch/climate (~150 lines) is now one base class.
- Per-platform logic types now live in one place (`const.CLIMATE_LOGIC_TYPES` / `COVER_` / `LIGHT_` / `SENSOR_` / `SOCKET_LOGIC_TYPES`, union in `ENTITY_LOGIC_TYPES`); the platforms and the sync statistics both reference them, so the "does this device produce an entity" question can't drift from what the platforms actually build. `sensor.py` uses a spec table (`_SENSOR_SPECS`) instead of five near-identical branches. `tests/test_integration.py` asserts the sets stay in sync.
- `config_flow.py` — the "[device name] entity name (entity_id)" formatting duplicated in five steps collapsed into `_describe_entity` / `_linkable_candidates`; `OptionsFlow` no longer takes `config_entry` in its constructor (HA 2024.11+ injects `self.config_entry`).
- `async_track_state_change` (deprecated) → `async_track_state_change_event`.
- Protocol magic numbers named in `const.py` (power state, curtain state, VSwitch arm payloads, linked-on states) and `LeelenType`; `572` is documented as `WIRELESS_DOUBLE_CURTAIN_PANEL` — the device DB shows it under a dual-curtain panel with `srv_type=0`, so it is filtered out and never builds an entity.
- `manifest.json`: dropped unused requirements (`construct`, `paho-mqtt`, `numpy`, `psutil`), `iot_class` set to `local_push`, `loggers` corrected to the Python logger name. `hacs.json`: removed the invalid `iot_class` key.
- Untracked `.claude/settings.local.json`.

### 📝 Notes

- The connection monitor still logs one `no such table: room_tbl` traceback when a fresh `dump.db` is downloaded before the gateway has populated it; harmless, handled by `room_sync`.

## V1.1.0 (2026-09-18)

### ✨ New features

- **Connection mode switch (LAN / WAN)** — new `connect_mode` option (Options → 连接方式). Device control can run directly over LAN (default) or tunneled through the Leelen cloud (WAN) for cross-network use. Saving any option now auto-reloads the integration ("save-now-effective"), no manual reload needed.
- **Room → area auto-sync** — Leelen room structure is pushed into Home Assistant areas automatically at setup, and manually via `Options → Sync Rooms`. Existing manual area assignments are never overwritten.
- **Gateway IP manual override** (`gateway_ip` option) — when the gateway changed IP via DHCP but the cloud `dump.db` still reports a stale address, override it in the options page.
- **VSwitch (V设备) entity linking** — link a VSwitch to any home-assistant entity by `entity_id`; toggling the switch drives the linked entity's state (one master arm switch for the whole house).
- **Bilingual project documentation** — English `README.md` (default) + Chinese `README_CN.md`.

### 🛠 Fixes (WAN chain / connection layer)

- WAN passthrough control frames now actually reach the gateway: fixed recursive `get_request_data`, zero-padded body before CRC (Java parity), slice-assignment truncation, and forwarding via `ConnectLan.handle_recv_data` instead of a non-existent method.
- `GetServerCodeWanProtocol`: use the instance lock (was class-lock → self-deadlock), fixed-length 2-byte little-endian session/seq, and long address packing.
- `BaseWanProtocol` head now always encodes `session_id` / `length` as fixed 4-byte little-endian (short values used to compress the head to 29B and shift all fields).
- AES encrypt/decrypt now uses the correct argument counts (bytes-level API).
- Connection monitor task is entry-bound (no longer blocks HA startup), notification is status-driven with a fixed id, and stops cleanly on unload.
- Connection re-login loop: fixed thread leak (old threads holding a stale instance event), backoff now abandons reconnect on close, `connect_retry_count` resets to 0 once logged on.
- `AckToDao` — dropped dead `trans_*` handlers for tables with no consumers (behavior unchanged for the only live path: `logic_server_state` events).

### 🔄 Refactor

- Singleton consolidation via `SingletonMixin` (16 classes).
- Shared platform setup/refresh boilerplate extracted into `platform_helper.py` (switch/light/sensor/cover/climate).
- Removed dead code, orphan methods and unused imports across the component (A/B/C audit batches).

### 📝 Notes

- **Users upgrading from unofficial `V1.0.9`/`V1.0.10`-era builds:** this release continues from the refactored codebase. Entities, `unique_id`s (`leelen_logic_addr_*`) and option keys are unchanged; the version line just joins the `V1.0.x` release track under a cleaner major/minor scheme.
- Requires Home Assistant **2024.1.0+**.
- The `VSwitch` class name is kept in code; only the user-facing name became **V设备** (V switch device).

---

## V1.0.10 (2026-05-26)

- 新增 V 设备支持、实体联动、场景与按键自定义。

## V1.0.9 (2026-05-11)

- 增加新风、地暖以及 ZIGBEE 空调支持(贡献:wells1975)。

## V1.0.8 – V1.0.1

- 早期修复与功能迭代。