# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import ctypes
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

from pywinauto import Application, Desktop, mouse  # noqa: E402
from pywinauto.controls.common_controls import ToolbarWrapper  # noqa: E402
from pywinauto.keyboard import send_keys  # noqa: E402
import win32clipboard  # noqa: E402


PROCESS_ID = 25760
MAIN_HANDLE = 2042746
MDI_HANDLE = 2435234
OVERVIEW_FRAME_HANDLE = 9051628
TOOLBOX_TOOLBAR_HANDLE = 12656122

WM_MDIACTIVATE = 0x0222
LABEL_TOOL_INDEX = 7


def window_by_handle(handle: int):
    return Desktop(backend="win32").window(handle=handle)


def activate_overview() -> None:
    ctypes.windll.user32.SendMessageW(
        MDI_HANDLE,
        WM_MDIACTIVATE,
        OVERVIEW_FRAME_HANDLE,
        0,
    )
    ctypes.windll.user32.SetForegroundWindow(MAIN_HANDLE)
    time.sleep(0.4)


def visible_dialog(title: str | None = None):
    candidates = []
    for window in Desktop(backend="win32").windows(process=PROCESS_ID):
        if not window.is_visible() or window.class_name() != "#32770":
            continue
        if title is None or window.window_text() == title:
            candidates.append(window)
    if len(candidates) != 1:
        titles = [window.window_text() for window in candidates]
        raise RuntimeError(
            f"Expected one visible dialog, found {len(candidates)}: {titles}"
        )
    return candidates[0]


def control_by_id(dialog, control_id: int, class_name: str, visible=True):
    matches = [
        control
        for control in dialog.descendants(class_name=class_name)
        if control.control_id() == control_id
        and (not visible or control.is_visible())
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one visible {class_name} id={control_id}, "
            f"found {len(matches)}"
        )
    return matches[0]


def click_tool(index: int) -> None:
    toolbar = ToolbarWrapper(
        window_by_handle(TOOLBOX_TOOLBAR_HANDLE).element_info
    )
    if index >= toolbar.button_count():
        raise IndexError(
            f"Tool index {index}; buttons={toolbar.button_count()}"
        )
    toolbar.button(index).click_input()


def paste_text(text: str) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    send_keys("^v")


def create_label(
    left: int,
    top: int,
    width: int,
    height: int,
    text: str,
) -> tuple[int, int]:
    activate_overview()
    click_tool(LABEL_TOOL_INDEX)
    start = (left, top)
    end = (left + width, top + height)
    mouse.press(coords=start)
    mouse.move(coords=end)
    mouse.release(coords=end)
    time.sleep(0.4)
    send_keys("^a")
    paste_text(text)
    send_keys("{ENTER}")
    mouse.click(coords=(end[0] + 8, end[1] + 8))
    time.sleep(0.3)
    return start, end


def open_label_properties(center_x: int, center_y: int):
    activate_overview()
    mouse.double_click(coords=(center_x, center_y))
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        dialogs = [
            window
            for window in Desktop(backend="win32").windows(process=PROCESS_ID)
            if window.is_visible()
            and window.class_name() == "#32770"
            and "标签" in window.window_text()
        ]
        if dialogs:
            return dialogs[0]
        time.sleep(0.1)
    raise TimeoutError("Label property dialog did not open")


def bind_numeric_output(
    center_x: int,
    center_y: int,
    expression: str,
    decimals: int = 0,
) -> None:
    dialog = open_label_properties(center_x, center_y)
    output_toggle = control_by_id(dialog, 1035, "Button")
    if output_toggle.get_check_state() == 0:
        output_toggle.click_input()
    tab = control_by_id(dialog, 1082, "SysTabControl32")
    tab.select(2)
    time.sleep(0.3)

    control_by_id(dialog, 1018, "Edit").set_edit_text(expression)
    control_by_id(dialog, 1068, "Button").click_input()
    time.sleep(0.2)

    if decimals > 0:
        float_radio = control_by_id(dialog, 1006, "Button")
        if float_radio.get_check_state() == 0:
            float_radio.click_input()

        # MCGS only enables the decimal-count input when "natural decimal"
        # is cleared.  The default state varies with the selected output type.
        natural_decimal = control_by_id(dialog, 1034, "Button")
        if natural_decimal.get_check_state() != 0:
            natural_decimal.click_input()
        control_by_id(dialog, 1022, "Edit").set_edit_text(str(decimals))
    else:
        integer_radio = control_by_id(dialog, 1007, "Button")
        if integer_radio.get_check_state() == 0:
            integer_radio.click_input()

    confirm = [
        control
        for control in dialog.descendants(class_name="Button")
        if control.control_id() == 1040
        and control.is_visible()
        and control.window_text().startswith("确认")
    ]
    if len(confirm) != 1:
        raise RuntimeError(f"Expected confirm button, found {len(confirm)}")
    confirm[0].click_input()
    time.sleep(0.5)


def save_project() -> None:
    activate_overview()
    send_keys("^s")
    time.sleep(1)


def build_probe() -> None:
    # The overview canvas begins at screen y=114 while the MDI child is maximized.
    label = create_label(28, 190, 120, 30, "室内温度")
    value = create_label(154, 190, 100, 30, "0.0")
    bind_numeric_output(
        (value[0][0] + value[1][0]) // 2,
        (value[0][1] + value[1][1]) // 2,
        "设备0_只读4WB0511/10.0",
        decimals=1,
    )
    save_project()


OVERVIEW_FIELDS = (
    # (caption, expression, decimal places, left, top)
    ("室内温度 (℃)", "设备0_只读4WB0511/10.0", 1, 28, 190),
    ("室内湿度 (%RH)", "设备0_只读4WUB0501/10.0", 1, 28, 228),
    ("新风温度 (℃)", "设备0_只读4WB0512/10.0", 1, 28, 266),
    ("送风温度 (℃)", "设备0_只读4WB0510/10.0", 1, 28, 304),
    ("系统状态", "设备0_只读4WUB0700", 0, 28, 360),
    ("运行步骤", "设备0_只读4WUB0709", 0, 28, 398),
    ("故障停机", "设备0_只读4WUB0710", 0, 28, 436),
    ("报警状态", "设备0_只读4WUB0861", 0, 28, 474),
    ("外机台数", "设备0_读写4WUB0388", 0, 368, 190),
    ("目标压机数", "设备0_只读4WUB0881", 0, 368, 228),
    ("压机控制方式", "设备0_只读4WUB0872", 0, 368, 266),
    ("制冷/制热需求", "设备0_只读4WUB0880/1000.0", 3, 368, 304),
    ("再热/辅热需求", "设备0_只读4WUB0890/1000.0", 3, 368, 360),
    ("加湿需求", "设备0_只读4WUB0892/1000.0", 3, 368, 398),
    ("送风机输出 (V)", "设备0_只读4WUB0900/10.0", 1, 368, 436),
    ("房间压差 (Pa)", "设备0_只读4WB0902", 0, 368, 474),
)


def create_bound_label(
    caption: str,
    expression: str,
    decimals: int,
    left: int,
    top: int,
) -> None:
    create_label(left, top, 180, 28, caption)
    value = create_label(left + 188, top, 118, 28, "0")
    bind_numeric_output(
        (value[0][0] + value[1][0]) // 2,
        (value[0][1] + value[1][1]) // 2,
        expression,
        decimals,
    )


def build_overview() -> None:
    # The first room-temperature pair already exists as the verified binding
    # probe.  Preserve it instead of stacking a duplicate pair on top of it.
    for field in OVERVIEW_FIELDS[1:]:
        create_bound_label(*field)
    save_project()


def verify_binding(center_x: int, center_y: int) -> None:
    dialog = open_label_properties(center_x, center_y)
    tab = control_by_id(dialog, 1082, "SysTabControl32")
    tab.select(2)
    time.sleep(0.3)
    expression = control_by_id(dialog, 1018, "Edit").window_text()
    numeric_output = control_by_id(dialog, 1068, "Button").get_check_state()
    decimal_places = control_by_id(dialog, 1022, "Edit").window_text()
    print(
        f"expression={expression!r}; numeric_output={numeric_output}; "
        f"decimal_places={decimal_places!r}"
    )
    cancel = [
        control
        for control in dialog.descendants(class_name="Button")
        if control.control_id() == 1041
        and control.is_visible()
        and control.window_text().startswith("鍙栨秷")
    ]
    if len(cancel) != 1:
        raise RuntimeError(f"Expected cancel button, found {len(cancel)}")
    cancel[0].click_input()
    time.sleep(0.3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("probe", "overview", "verify", "activate"),
    )
    args = parser.parse_args()

    Application(backend="win32").connect(process=PROCESS_ID)
    if args.action == "probe":
        build_probe()
    elif args.action == "overview":
        build_overview()
    elif args.action == "verify":
        # A one-decimal and an integer label from the first batch.
        verify_binding(275, 242)
        verify_binding(615, 242)
    else:
        activate_overview()
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
