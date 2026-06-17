# SysAdmin GUI

SysAdmin GUI is a single-window Ubuntu administration tool built with Python 3, Tkinter, ttk, and shell backends. It opens on a simple Home dashboard, keeps a fixed left sidebar visible, and changes the right content area between Files & Folders, Scheduled Tasks, Date & Time, Software Manager, and About.

## Architecture

Python owns the desktop experience: windows, sidebar navigation, forms, tables, validation, confirmations, progress windows, and friendly messages. Shell scripts own system functions: file operations, cron actions, time settings, package operations, and action logging.

Python calls shell scripts with argument lists through `subprocess.run`, captures stdout and stderr, and never builds interactive terminal flows. Privileged actions are launched through `pkexec`.

## Why Python GUI + Shell Backend

Tkinter is available on Ubuntu through `python3-tk`, is lightweight, and supports a persistent desktop layout without terminal menus. Shell scripts keep system-level commands auditable and testable.

## Features

- Create, delete, rename, copy, move, browse, search, compress, extract, and change permissions for files and folders.
- List, add, and remove app-created cron jobs.
- View local time, UTC time, timezone, and sync status.
- Change timezone, toggle time sync, and set date/time with root confirmation.
- Search packages, list installed packages, install selected packages, and remove selected packages.
- Switch the interface between English and Vietnamese from the top bar.
- Mock mode for safe self-testing with `MOCK_MODE=1`.

## Installation

Run from the project folder:

```bash
bash install.sh
```

The installer installs dependencies, copies the project to `/opt/sysadmin_gui`, creates a desktop launcher, and runs the self-test. The desktop menu entry is:

```text
SysAdmin GUI
```

## How To Run

During development:

```bash
python3 app.py
```

After installation, use the desktop menu entry or run:

```bash
python3 /opt/sysadmin_gui/app.py
```

## Self-Test

Run either command:

```bash
python3 app.py --self-test
bash tests/self_test.sh
```

The self-test checks Python syntax, shell syntax, required files, executable bits, terminal UI bans, safe shell invocation, file operations, cron expression generation, and required Python symbols.

For the manual handover review checklist, run:

```bash
python3 app.py --ui-checklist
```

## Troubleshooting

- If the app does not open, install Tkinter with `sudo apt install python3-tk`.
- If root actions fail, make sure `pkexec` and PolicyKit are installed.
- If package search returns no results, run `sudo apt update`.
- If logs are missing, check `logs/sysadmin_gui.log` in the development folder or `/var/log/sysadmin_gui.log` after installation.
- In mock mode, file operations are restricted to the test directory set by `SYSADMIN_GUI_MOCK_ROOT`.
