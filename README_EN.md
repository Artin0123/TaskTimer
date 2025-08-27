Sponsor me to make an Android version (needs $25 listing fee):  

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/arttin)  

[![ko-fi](https://www.ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/U7U01KBWBU)  

# TaskTimer — Duration-based recurring reminders

Use a fixed duration to remind you, not a specific calendar datetime. Set a duration (e.g., 7 days, 30 days) and reuse it for subscriptions/bills/routine tasks. When it’s due, click Reset to start the next round.

> Core difference from typical calendar apps: it’s not a one-time alarm scheduled at a specific future moment, but a reminder based on a fixed duration. This fits subscription renewals, trial ends, routine checks, backups, etc.

## Features

- Lightweight, free, open-source, no ads
- Import/Export tasks
- Manage multiple tasks independently
- Description field supports link preview and opens links in your browser
- Duration-based countdown and reuse
  - Supports seconds / minutes / hours / days, quick input 1–99 with unit
  - Shows target time and remaining time, notifies when due
  - After due, the task remains; click “Reset” to start the next round (effectively infinite reuse)
- Notifications
  - Built-in in-app lightweight toast, configurable position; click to open edit
  - Optional Windows native notifications (winotify)
- Settings & appearance
  - Light/Dark/System themes; large fonts; DPI-aware for crisp display
  - Optional “Run at startup” and “Start minimized to tray”

## Run from source

Environment: Windows 10/11, Python 3.13

1) Install dependencies

```cmd
pip install -r requirements.txt
```

Optional (system tray icon):

```cmd
pip install pystray pillow
```

2) Run

```cmd
python TaskTimer.py
```

Notes:
- Task data is stored at: `%USERPROFILE%\TaskTimer\tasks.json`.
- Settings file `TaskTimer.json`:
  - Running .py from source: placed next to `TaskTimer.py`.
  - Packed .exe: placed next to the .exe.

## Usage

- Add a task → input “value + unit” → Save.
- Start/Pause: independent across tasks.
- Reset: sets next target to “now + duration”.
- Notifications:
  - In-app toast always appears;
  - If “system notifications” is enabled, a Windows notification also shows.
- Run at startup: enable/disable in Settings (implemented via a shortcut in the Startup folder).
- System tray: with the optional dependencies installed, the app can minimize to the system tray; otherwise it falls back to normal minimize.

## Special Thanks
GPT, Claude, Gemini
