# 更新日志 / Changelog

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