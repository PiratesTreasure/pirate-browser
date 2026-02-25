# 🏴‍☠️ Pirate Browser

An automated desktop app for [ShippingManager.cc](https://shippingmanager.cc) that handles fuel/CO2 purchasing and vessel departures automatically.

## Features

- ⛽ **Auto Fuel Rebuy** — buys fuel automatically when the price drops below your threshold
- 🌿 **Auto CO2 Rebuy** — buys CO2 automatically when the price drops below your threshold
- 🚢 **Auto Depart** — departs all ready vessels on a timer
- 📊 **Live Dashboard** — see your fuel, CO2, cash and market prices in real time
- 📋 **Departure Log** — track income, fuel and CO2 used per departure
- 🌐 **Auto Browser Detection** — works with Chrome, Edge or Firefox

## Screenshot

> Dashboard runs alongside the game in your browser

## Installation

### Option 1 — Run from source

**Requirements:** Python 3.11, Chrome/Edge/Firefox

```bash
git clone https://github.com/chrisridger/pirate-browser.git
cd pirate-browser
pip install -r requirements.txt
py -3.11 pirate_browser.py
```

### Option 2 — Windows Installer

Download the latest `PirateBrowser_Setup.exe` from the [Releases](../../releases) page and run it.

## Usage

1. Launch the app
2. Log into ShippingManager.cc in the browser window that opens
3. Once logged in the auto-manager activates automatically
4. Go to the **Settings** tab to configure your thresholds
5. Click **▶ Run Check Now** to trigger an immediate check

## Settings

| Setting | Description |
|---|---|
| Fuel Mode | `off` / `basic` / `intelligent` |
| Fuel Price Threshold | Only buys when price is at or below this value ($/t) |
| CO2 Mode | `off` / `basic` |
| CO2 Price Threshold | Only buys when price is at or below this value ($/t) |
| Min Cash Reserve | Never spends below this cash balance |
| Auto Depart | Automatically departs all ready vessels |
| Check Interval | How often the auto-manager runs (seconds) |

## How It Works

Pirate Browser uses Selenium to control a real browser session. Instead of clicking buttons, it calls the game's API directly — the same way the game does — so it works reliably without any browser extensions or script injection.

## Requirements

- Python 3.11+
- Chrome, Edge, or Firefox
- Windows 10/11

## License

MIT — see [LICENSE](LICENSE)
