# Leelen Home

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1.0-blue.svg)](https://www.home-assistant.io/)

Home Assistant integration for Leelen (立林) smart home devices.

## Features

- **Climate**: Central air conditioner control
- **Cover**: Curtain motor control
- **Light**: Wireless light control
- **Sensor**: Temperature, humidity, PM2.5 sensors
- **Binary Sensor**: Door sensors, water immersion sensors
- **Switch**: Smart wall socket control

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant
2. Go to "Integrations" → Click "+" button
3. Search for "Leelen Home" or add as custom repository:
   - Repository: `https://github.com/snailll/leelen-home`
   - Category: Integration
4. Click "Download"
5. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/leelen` folder to your Home Assistant `config/custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Leelen Home"
4. Enter your phone number and verification code
5. Select the devices you want to add

## Supported Devices

| Device Type | Model |
|------------|-------|
| Central AC | TYPE_CENTER_AIR_CONDITIONER |
| Curtain | TYPE_WIRELESS_CURTAIN |
| Light | TYPE_WIRELESS_LIGHT |
| Temperature Sensor | TYPE_TEMPERATURE_SENSOR |
| Humidity Sensor | TYPE_HUMIDITY_SENSOR |
| PM Sensor | TYPE_PM_SENSOR |
| Door Sensor | TYPE_WIRELESS_DOOR_SENSOR |
| Water Sensor | TYPE_WIRELESS_WATER_IMMERSION_SENSOR |
| Socket | ZIGBEE_SMART_WALL_SOCKET |

## Troubleshooting

### Cannot connect to gateway

- Ensure your Home Assistant can access the Leelen cloud service
- Check if your account is bound to a gateway device in the Leelen app

### Devices not showing up

- Try refreshing devices from the integration options
- Check if devices are online in the Leelen app

## Support

If you encounter any issues, please [open an issue](https://github.com/snail0903/leelen-home/issues) on GitHub.

## License

This project is licensed under the MIT License.
