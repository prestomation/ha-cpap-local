# CPAP Local — Home Assistant Integration

A Home Assistant custom integration that fetches ResMed CPAP therapy data from your device's SD card and exposes it as sensors. HACS-compatible.

Supports ResMed AirSense 10, AirSense 11, and S9 series devices. Data can be fetched via a WiFi SD card adapter (HTTP) or from a locally mounted SD card.

> **WiFi Note:** This integration does not manage your WiFi SD card adapter or network routing. That setup is your responsibility. Common approaches:
> - [EZ Share WiFi SD Card](https://www.amazon.com/s?k=ez+share+wifi+sd) — plug-and-play adapter that creates its own WiFi network
> - OpenWRT router routing — route traffic from the EZ Share AP to your Home Assistant host
> - Raspberry Pi bridge — connect to the EZ Share AP and bridge to your home network

---

## Installation via HACS

1. Open HACS in Home Assistant
2. Go to **Integrations → Custom Repositories**
3. Add `https://github.com/prestomation/ha-cpap-local` as an **Integration**
4. Search for "CPAP Local" and install
5. Restart Home Assistant

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **CPAP Local**
3. Follow the config flow:

### Step 1: Choose Connection Method

| Method | When to use |
|---|---|
| **HTTP (WiFi SD Card)** | Your CPAP is off, EZ Share adapter is on your home network |
| **Local Path** | SD card is mounted on the HA host (card reader or network share) |

### Step 2a: HTTP Setup
- **Adapter URL** — default `http://192.168.4.1` (EZ Share default IP)
- **Daily Sync Hour** — hour of day to fetch data (default 10 = 10:00 AM)

### Step 2b: Local Path Setup
- **SD Card Path** — full path to the SD card mount point (e.g. `/media/resmed_sd`)
- **Daily Sync Hour** — same as above

### Options (after setup)
- **AHI Threshold** — AHI level that triggers `binary_sensor.cpap_ahi_elevated` (default 10)
- **Minimum Usage Hours** — hours of use that defines compliance (default 4h, per insurance standards)
- **Raw DATALOG Sync** — optionally archive high-res per-breath DATALOG files to a local path

---

## Entities

### Sensors

| Entity | Unit | Description |
|---|---|---|
| `sensor.cpap_ahi` | events/h | Apnea-Hypopnea Index |
| `sensor.cpap_usage_hours` | h | Nightly usage duration |
| `sensor.cpap_mask_leak` | L/min | Median mask leak |
| `sensor.cpap_mask_leak_95` | L/min | 95th percentile mask leak |
| `sensor.cpap_pressure_median` | cmH2O | Median therapy pressure |
| `sensor.cpap_pressure_95` | cmH2O | 95th percentile pressure |
| `sensor.cpap_session_start` | timestamp | Mask-on time |
| `sensor.cpap_session_end` | timestamp | Mask-off time |
| `sensor.cpap_mode` | — | Therapy mode (CPAP, APAP, AutoSet, etc.) |
| `sensor.cpap_last_sync` | timestamp | Last successful data sync |

### Binary Sensors

| Entity | Description |
|---|---|
| `binary_sensor.cpap_used_last_night` | True if usage ≥ 1 hour |
| `binary_sensor.cpap_ahi_elevated` | True if AHI exceeded configured threshold |
| `binary_sensor.cpap_compliant` | True if usage ≥ configured minimum hours |

---

## Services

### `cpap_local.sync_now`
Immediately fetch the latest CPAP data, bypassing the scheduled sync time.

```yaml
service: cpap_local.sync_now
```

---

## Automation Example

```yaml
# Notify if AHI was elevated last night
automation:
  - alias: "CPAP AHI Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.cpap_ahi_elevated
        to: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "CPAP Alert"
          message: >
            Last night's AHI was {{ states('sensor.cpap_ahi') }} events/hour.
            Consider checking your mask fit.
```

---

## Requirements

- Home Assistant 2023.6+
- ResMed AirSense 10, AirSense 11, or S9 series device with SD card
- WiFi SD card adapter (e.g. EZ Share) or direct SD card access

## Dependencies

This integration uses [pycpap](https://github.com/prestomation/pycpap) for SD card data parsing.
