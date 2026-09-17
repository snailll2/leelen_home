# Leelen Home

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1.0-blue.svg)](https://www.home-assistant.io/)

**English** | [中文](README.md)

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
- Default is `LAN` — existing users' behavior is unchanged.

### Device platforms

| Platform | Devices |
|----------|---------|
| **Climate** | Central air-conditioner control |
| **Cover** | Wireless curtain motor |
| **Light** | Wireless light switch |
| **Switch** | Zigbee smart wall socket + arm/disarm switch (VSwitch) |
| **Sensor** | Temperature, humidity, PM2.5 sensors |

### Options menu

Configure anything from **Settings → Devices & Services → Leelen Home → Options**:

| Menu item | What it does |
|-----------|--------------|
| **Refresh** | Re-fetch the device list from the cloud / gateway and rebuild entities |
| **Link / Manage Links** | Link a VSwitch (arm/disarm switch) to any other HA entity by its `entity_id` — toggling the switch drives the linked entity's state (e.g. one master arm switch for the whole house) |
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

> The account must have the gateway bound in the official **Leelen App** (立林智能 / 立林家) before setup.

### Entity linking (VSwitch)

1. **Options → Link** and pick the VSwitch entity
2. Pick the target entity by its `entity_id` (any platform)
3. When the VSwitch turns on/off, the linked entity follows the same state — handy for a "master arm" switch in automations or dashboards.

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