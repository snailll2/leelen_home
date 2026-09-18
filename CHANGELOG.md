# 更新日志 / Changelog

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