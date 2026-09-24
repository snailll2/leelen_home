# Leelen Home

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1.0-blue.svg)](https://www.home-assistant.io/)

**English** | [中文](README_CN.md)

Home Assistant integration for **Leelen (立林)** smart home devices (IoT 2.0 gateways).

Connect your Leelen gateway — central AC, curtains, lights, smart wall sockets and
sensors — into Home Assistant. Device control can run **directly over LAN** or
**through the internet (WAN)**; you switch at any time from the integration options.

---

## ✨ Features

### Connection modes (`connect_mode`)

| Mode | How it works | When to use |
|------|--------------|-------------|
| **LAN (local)** | Device frames are sent directly to the gateway on the local network over TCP + TLS | Fastest, no internet dependency; requires your HA host to reach the gateway IP on your LAN |
| **WAN (internet)** | Device frames are tunneled through the Leelen cloud (pass-through) | Cross-network / when the gateway is not on the same segment as HA |

- Switchable any time from **Options → Connection Mode**; saving takes effect immediately (the integration auto-reloads).
- In WAN mode the integration establishes **no local connection** at all, so state updates return cleanly over the cloud tunnel.
- Default is `LAN` — device connection is attempted over LAN first, then WAN if that fails.

### Device platforms

Entities are created by **logic type** (`logic_srv.logic_type`, never by hard-coded device
names or addresses), so the same integration adapts correctly to any gateway — no per-home
configuration. Panels that duplicate the same channel (`display = 0`) are skipped, matching
what the official app shows.

| Platform | Devices (logic types) |
|----------|---------|
| **Climate** | Three dedicated entity classes, dispatched by logic type: |
| | **Air conditioner** (`AirConditioner`) — central AC, AC actuator, infrared AC, 485/KTV AC, ZigBee AC gateway (`146/242/157/658/770/773/778/782`). Single-frame control of power + mode + fan speed + target temperature; per-type function codes (55297, or 51232 for actuators). |
| | **Fresh air fan** (`FreshAirFan`) — fresh air, ventilation system, AC-fresh combos (`148/152/664/771/774/777/780/783`). Level 0/1/2/3/0xFE = off / low / mid / high / auto; per-type function codes (49185, or 49156). |
| | **Floor heating** (`FloorHeatingClimate`) — floor heating valve, control & actuator (`150/662/772/775/776/779`). Power bit is bit 4 of the state byte (0x10); set-temperature frames never touch the power bit, so turning up the temperature can’t accidentally switch it off (51234, or 51213). |
| **Cover** | **Wireless curtain** (`Cover`) — wireless curtain motor (`570`). power_state 0/1/2/3 = closed / open / stop / move-to-position; exposes open / close / set-position. |
| **Light** | **Wireless light** (`Light`) — wireless light switch (`514`). Strict on / off (no dimming); a single ON_OFF frame carries both the command and the confirmed state. |
| **Switch** | Two entity classes: |
| | **Smart wall socket** (`Switch`) — Zigbee smart wall socket (`518`). On / off, with power & energy on the standard attributes: `current_power_w` (raw report ×0.1 → W), `today_energy_kwh`, `month_energy_kwh` (fetched live from the gateway meter, refreshed every 10 min). |
| | *(The same socket also exposes 3 standalone sensor entities — see **Sensor** below.)* |
| | **V switch device** (`VSwitch`) — ARM-style arm/disarm switch (`259`). 1 = armed (on), 2 = disarmed (off); links to any HA entity by `entity_id` (Options → Link) so toggling the V switch drives the linked entity — one master arm switch for the whole house. |
| | *(572 Dual-curtain panel is kept for legacy address matching; its channels are `srv_type=0` so they are filtered out at device query and never build an entity.)* |
| **Sensor** | Sensor classes by logic type: |
| | **Temperature** (`65`) — °C temperature sensor |
| | **PM2.5** (`75`) — µg/m³ air-quality sensor |
| | **Humidity** (`66`) — % relative-humidity sensor |
| | **Door/window** (`586`) — binary door sensor (open / closed) |
| | **Water leak** (`591`) — binary moisture sensor (dry / wet) |
| | **Smart wall socket** (`518`) — standalone, page-visible power/energy sensors shared with the socket's `Switch`: **power** (`current_power_w`, W, measurement), **today energy** (`today_energy_kwh`), **month energy** (`month_energy_kwh`) — same values as the `Switch` attributes, fed by the same event stream (no extra requests). |
| | **Gateway attributes** (`dev_addr = 0`) — one sensor per reported gateway property: **主版本** (main version), **软件版本** (software version), **IP地址**, **MAC地址**, **WiFi名称** (SSID). Only properties present in the gateway's `property_tbl` are created (older firmware with fewer properties simply yields fewer entities). |
| | **Gateway online** (`dev_addr = 0`) — binary sensor reflecting the gateway link status (`gateway_link_up()`): `on` when the LAN/WAN link is logged in, `off` otherwise. Shares the device entry with the gateway's V switch entities (same gateway device). |
| **Button** | Utility press-to-act entities, grouped under each device's **configuration** section: |
| | **Device locate** (`DeviceLocateButton`) — created for every locatable physical device (real `dev_addr` that has at least one entity channel). Press sends the official **device-locate** command (DEVICE_HINT + flash mode); the device's status LED blinks for ~30 s. |
| | **Curtain motor: change direction** (`CurtainMotorDirectionButton`) — one per curtain-motor channel that holds a writable direction property (163). Press **flips** the motor direction (wire value = `1 − current`). |
| | **Curtain motor: reset travel** (`CurtainMotorResetButton`) — same channel as above. Press **re-triggers the travel-limit learning**, keeping the current direction bit (wire value = `direction + 2`). |


### Options menu

Configure anything from **Settings → Devices & Services → Leelen Home → Options**:

| Menu item | What it does |
|-----------|--------------|
| **Refresh** | Re-fetch the device list from the cloud / gateway and rebuild entities |
| **Link / Manage Links** | Link a V switch device (VSwitch) to any other HA entity by its `entity_id` — toggling the switch drives the linked entity's state (e.g. one master arm switch for the whole house) |
| **Gateway IP** | Manually override the gateway LAN IP. Use this when the gateway changed IP via DHCP but the cloud `dump.db` still reports a stale address |
| **Sync Rooms** | Push your Leelen room structure into Home Assistant **areas** automatically (also runs in the background at setup) |
| **Connection Mode** | Switch between LAN / WAN — see above |

Any option save triggers an automatic reload ("save-now-effective"), so no manual `Reload` is needed.

---

## 📦 Installation

Requires **Home Assistant 2024.1.0 or newer**.

### HACS (recommended)

1. Open HACS → Integrations → “+” → custom repository
2. Add `https://github.com/snailll2/leelen_home` (category: **Integration**)
3. Click **Download**, then restart Home Assistant

### Manual

1. Copy `custom_components/leelen_home/` into your Home Assistant `config/custom_components/`
2. Restart Home Assistant

---

## ⚙️ Configuration

1. Go to **Settings → Devices & Services → Add Integration** and search for **“Leelen Home”**
2. Enter the **phone number** bound to your Leelen account
3. Enter the **SMS verification code** received on that phone
4. The integration logs in, discovers the bound gateway, and creates entities for the online devices

> The account must have the gateway bound in the official **Leelen Home (小立管家) App** before setup.

### V switch device entity linking

1. **Options → Link** and pick the V switch device entity
2. Pick the target entity by its `entity_id` (any platform)
3. When the V switch device turns on/off, the linked entity follows the same state — handy for a "master arm" switch in automations or dashboards.

### Gateway IP override (`gateway_ip`)

Cloud `dump.db` sometimes reports a stale LAN IP for the gateway after a DHCP re-lease. If devices go offline while the gateway is actually online:

1. Find the gateway's real current IP (e.g. from your router's DHCP client list)
2. **Options → Gateway IP**, enter it, save.

The override wins over the cloud-provided value.

---

## 🛠 Troubleshooting

### LAN mode: "cannot control / devices unreachable"

- Confirm the gateway is actually at the configured IP: `ping <gateway-ip>` from the HA host.
- The gateway IP may have changed via DHCP — check your router's client list and update **Options → Gateway IP**.
- Note that cloud `dump.db` may report a stale/phantom IP that answers ping but connects nothing — prefer an IP confirmed from your router or by scanning for the gateway's TCP port (`49153`).
- In WAN mode the gateway is reached through the internet, so LAN reachability is irrelevant — switch modes if the network segment changed.

### Devices not showing up

- Try **Options → Refresh** to re-fetch devices.
- Verify the devices are online/paired in the Leelen app and bound to the same gateway.

### Login fails

- SMS code expires quickly — request a fresh one if it fails.
- Ensure the account owns/binds the gateway you're configuring.

### Still stuck?

Open an [issue](https://github.com/snailll2/leelen_home/issues) with the log excerpt of
`custom_components/leelen_home` (or `Leelen` logger) from `home-assistant.log`.

---

## 📄 License

MIT. Not an official project; not affiliated with Leelen.