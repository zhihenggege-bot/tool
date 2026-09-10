# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / ".tools32"
for path in (
    TOOLS_DIR,
    TOOLS_DIR / "win32",
    TOOLS_DIR / "win32" / "lib",
    TOOLS_DIR / "Pythonwin",
):
    sys.path.insert(0, str(path))

os.add_dll_directory(str(TOOLS_DIR / "pywin32_system32"))
os.add_dll_directory(str(TOOLS_DIR))

from pywinauto import Application, Desktop  # noqa: E402


DEVICE_EDITOR_TITLE = "\u8bbe\u5907\u7f16\u8f91\u7a97\u53e3"
ADD_CHANNEL_TITLE = "\u6dfb\u52a0\u8bbe\u5907\u901a\u9053"

# Combo indexes verified against the installed ModbusRtuBaseZero driver.
REGISTER_4_AREA_INDEX = 3
UNSIGNED_16_INDEX = 16
SIGNED_16_INDEX = 17

ACCESS_CONTROL_IDS = {
    "ro": 1067,
    "wo": 1068,
    "rw": 1069,
}

OVERVIEW_BLOCKS = (
    # address, count, signed, access
    (388, 1, False, "rw"),
    (398, 1, False, "rw"),
    (500, 1, True, "ro"),
    (501, 1, False, "ro"),
    (510, 9, True, "ro"),
    (519, 1, False, "ro"),
    (524, 1, False, "rw"),
    (700, 13, False, "ro"),
    (861, 1, False, "ro"),
    (872, 2, False, "ro"),
    (874, 3, True, "ro"),
    (877, 2, False, "ro"),
    (879, 1, True, "ro"),
    (880, 5, False, "ro"),
    (890, 12, False, "ro"),
    (950, 2, False, "ro"),
    (2652, 1, False, "rw"),
    (2653, 1, False, "ro"),
)


def connect(process_id: int) -> Application:
    return Application(backend="win32").connect(process=process_id)


def find_visible_window(process_id: int, title: str):
    matches = [
        window
        for window in Desktop(backend="win32").windows(process=process_id)
        if window.is_visible() and window.window_text() == title
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one window {title!r}, found {len(matches)}")
    return matches[0]


def control_by_id(window, control_id: int, class_name: str):
    matches = [
        control
        for control in window.descendants(class_name=class_name)
        if control.control_id() == control_id
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one {class_name} control {control_id}, found {len(matches)}"
        )
    return matches[0]


def add_channel(
    process_id: int,
    address: int,
    count: int,
    signed: bool,
    access: str,
    frequency: int = 1,
) -> None:
    editor = find_visible_window(process_id, DEVICE_EDITOR_TITLE)
    editor.set_focus()
    control_by_id(editor, 1040, "Button").click_input()

    deadline = time.monotonic() + 5
    dialog = None
    while time.monotonic() < deadline:
        candidates = [
            window
            for window in Desktop(backend="win32").windows(process=process_id)
            if window.is_visible() and window.window_text() == ADD_CHANNEL_TITLE
        ]
        if candidates:
            dialog = candidates[0]
            break
        time.sleep(0.1)
    if dialog is None:
        raise TimeoutError("Add-channel dialog did not open")

    control_by_id(dialog, 1146, "ComboBox").select(
        REGISTER_4_AREA_INDEX
    )
    control_by_id(dialog, 1147, "ComboBox").select(
        SIGNED_16_INDEX if signed else UNSIGNED_16_INDEX
    )
    control_by_id(dialog, 1018, "Edit").set_edit_text(
        str(address)
    )
    control_by_id(dialog, 1019, "Edit").set_edit_text(
        str(count)
    )
    control_by_id(dialog, 1022, "Edit").set_edit_text(
        str(frequency)
    )
    control_by_id(dialog, ACCESS_CONTROL_IDS[access], "Button").click_input()
    control_by_id(dialog, 1040, "Button").click_input()

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        still_open = any(
            window.is_visible() and window.window_text() == ADD_CHANNEL_TITLE
            for window in Desktop(backend="win32").windows(process=process_id)
        )
        if not still_open:
            break
        time.sleep(0.1)
    else:
        raise TimeoutError(f"Add-channel dialog did not close for {address}")

    print(
        f"added address={address} count={count} "
        f"type={'signed' if signed else 'unsigned'} access={access}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--address", type=int)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--signed", action="store_true")
    parser.add_argument("--access", choices=("ro", "wo", "rw"), default="ro")
    parser.add_argument("--frequency", type=int, default=1)
    parser.add_argument("--overview-preset", action="store_true")
    args = parser.parse_args()

    connect(args.process_id)
    if args.overview_preset:
        for address, count, signed, access in OVERVIEW_BLOCKS:
            add_channel(
                process_id=args.process_id,
                address=address,
                count=count,
                signed=signed,
                access=access,
                frequency=args.frequency,
            )
    else:
        if args.address is None:
            parser.error("--address is required without --overview-preset")
        add_channel(
            process_id=args.process_id,
            address=args.address,
            count=args.count,
            signed=args.signed,
            access=args.access,
            frequency=args.frequency,
        )
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
