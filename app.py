#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


UI_CHECKLIST = [
    "Main dashboard is clear and explains each feature.",
    "Users can return Home from every module.",
    "Language selector switches between English and Vietnamese.",
    "Current module and current path are visible.",
    "Files & Folders has Back, Forward, Up, Go To, and Refresh navigation.",
    "Buttons are aligned and grouped by purpose.",
    "Selected-item actions stay disabled until an item is selected.",
    "Dangerous actions require confirmation.",
    "Protected system folders cannot be deleted.",
    "Delete moves files to Trash when desktop Trash is available.",
    "Dialogs include Cancel and use plain-language labels.",
    "Friendly errors are shown for missing files, permission issues, existing destinations, missing dependencies, and cancelled permission prompts.",
    "File and folder paths with spaces are passed as arguments, not shell strings.",
    "File and folder sizes are shown as exact byte counts.",
    "Input boxes support Ctrl+A, Cut, Copy, Paste, and Select All.",
    "Double-clicking a folder opens it in the file table.",
    "Double-clicking a file opens a readable preview or a clear unsupported-file message.",
    "File table columns sort when their headings are clicked.",
    "The app stays open after successful or failed actions.",
]


def run_self_test() -> int:
    """Run the same backend checks used for handover."""
    script = PROJECT_DIR / "tests" / "self_test.sh"
    result = subprocess.run(["bash", str(script)], cwd=str(PROJECT_DIR), text=True)
    return result.returncode


def print_ui_checklist() -> int:
    print("SysAdmin GUI manual UI/UX checklist")
    print("=" * 40)
    for item in UI_CHECKLIST:
        print(f"[ ] {item}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Friendly Ubuntu system administration desktop app.")
    parser.add_argument("--self-test", action="store_true", help="Run backend handover tests and exit.")
    parser.add_argument("--ui-checklist", action="store_true", help="Print the manual UI/UX handover checklist and exit.")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if args.ui_checklist:
        return print_ui_checklist()

    import tkinter as tk
    from gui.main_window import MainWindow

    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
