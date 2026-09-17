# Leelen Home

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1.0-blue.svg)](https://www.home-assistant.io/)

**中文** | [English](README_EN.md)

Home Assistant 的 **立林(Leelen)智能家居**集成,适配立林 IoT 2.0 网关。

把立林网关下的中央空调、窗帘、灯光、智能插座与传感器接入 Home Assistant。控制既可以走**局域网(LAN)直连**,也可以走**互联网(WAN)云端透传**,随时可在集成选项里切换。

---

## ✨ 功能特性

### 双连接模式(`connect_mode`)

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **LAN(局域网)** | 设备帧通过 TCP + TLS 直接发给局域网内的网关 | 速度最快、不依赖外网;需要 HA 主机能访问到网关 IP |
| **WAN(互联网)** | 设备帧经立林云端做透传(pass-through)转发 | 跨网段 / 网关与 HA 不在同一局域网时 |

- 随时可在 **选项 → 连接方式** 里切换;保存即生效(集成自动重载)。
- WAN 模式下集成**完全不建立本地连接**,状态回程全部走云端隧道,干净无干扰。
- 默认 `LAN`,老用户行为不变。

### 设备平台

| 平台 | 设备 |
|------|------|
| **Climate**(空调) | 中央空调控制 |
| **Cover**(窗帘) | 无线窗帘电机 |
| **Light**(灯光) | 无线灯光 |
| **Switch**(开关) | Zigbee 智能插座 + 布防开关(VSwitch) |
| **Sensor**(传感器) | 温湿度、PM2.5 传感器 |

### 选项菜单

在 **设置 → 设备与服务 → Leelen Home → 选项** 中配置:

| 菜单项 | 作用 |
|--------|------|
| **刷新(Refresh)** | 从云端/网关重新拉取设备列表并重建实体 |
| **关联(Link) / 管理关联(Manage Links)** | 把布防开关(VSwitch)联动到任意 HA 实体(`entity_id`)——开关联动即驱动对方状态,一个开关实现全屋布防 |
| **网关 IP(Gateway IP)** | 手动覆盖网关局域网 IP。网关 DHCP 换 IP 而云端 `dump.db` 仍记录旧地址时使用 |
| **同步房间(Sync Rooms)** | 将立林房间结构自动同步为 Home Assistant 的**区域**(setup 时也会后台自动跑) |
| **连接方式(Connection Mode)** | 切换 LAN / WAN,见上文 |

选项保存即生效(自动重载),无需手动 Reload。

---

## 📦 安装

要求 **Home Assistant 2024.1.0 或更新版本**。

### HACS(推荐)

1. HACS → 集成 → “+” → 自定义仓库
2. 添加 `https://github.com/snailll2/leelen_home`(类别:**Integration**)
3. 点击 **Download**,然后重启 Home Assistant

### 手动安装

1. 把 `custom_components/leelen_home/` 复制到 HA 的 `config/custom_components/` 下
2. 重启 Home Assistant

---

## ⚙️ 配置

1. **设置 → 设备与服务 → 添加集成**,搜索 **“Leelen Home”**
2. 输入已绑定立林账号的**手机号**
3. 输入手机收到的**短信验证码**
4. 集成登录、发现绑定的网关,并为在线设备创建实体

> 配置前,账号须先在官方**立林智能 / 立林家 App**里绑定好对应网关。

### VSwitch 实体联动

1. **选项 → 关联** 选择布防开关实体
2. 按 `entity_id` 选择目标实体(任意平台)
3. 布防开关打开/关闭时,被联动实体跟随同一状态——适合在自动化或仪表盘里做「总布防开关」

### 网关 IP 手工覆盖(`gateway_ip`)

网关 DHCP 重新分配后,云端 `dump.db` 偶尔会保留旧局域网 IP,导致设备「离线」。若网关实际在线:

1. 确认网关当前真实 IP(例如到路由器 DHCP 客户端列表里查)
2. **选项 → 网关 IP** 填入并保存

覆盖值优先于云端下发的地址。

---

## 🛠 故障排查

### LAN 模式:控制不了 / 设备不可达

- 确认网关确实在配置的 IP 上:HA 主机上 `ping <网关IP>`。
- 网关 IP 可能被 DHCP 重新分配——查路由器客户端列表,更新 **选项 → 网关 IP**。
- 注意:云端 `dump.db` 可能上报一个过期的「幽灵 IP」——能 ping 通但连云失败。应以路由器确认的 IP 为准,或扫网关 TCP 端口(`49153`)确认。
- WAN 模式经互联网访问网关,与局域网不可达无关——网络段变了就切换连接方式。

### 设备不显示

- 试试 **选项 → 刷新** 重新拉取设备。
- 确认设备在立林 App 里在线、且绑定在同一个网关下。

### 登录失败

- 短信验证码有效期很短,失败及时重新获取。
- 确认账号拥有/绑定了待配置的网关。

### 还搞不定?

带 `home-assistant.log` 里 `custom_components/leelen_home`(或 `Leelen` logger)的日志片段,开一个 [issue](https://github.com/snailll2/leelen_home/issues)。

---

## 📄 License

MIT,与立林科技无关联,本项目非官方。