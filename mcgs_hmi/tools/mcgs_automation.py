# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / ".tools"
for path in (
    TOOLS_DIR,
    TOOLS_DIR / "win32",
    TOOLS_DIR / "win32" / "lib",
    TOOLS_DIR / "Pythonwin",
):
    sys.path.insert(0, str(path))

os.add_dll_directory(str(TOOLS_DIR / "pywin32_system32"))
os.add_dll_directory(str(TOOLS_DIR))

from pywinauto import Application  # noqa: E402
from pywinauto.keyboard import send_keys  # noqa: E402


MCGS_PROCESS_ID = 86924
MCGS_MAIN_HANDLE = 923166
EXPORT_PATH = (
    Path(__file__).resolve().parents[1]
    / "exports"
    / "ModbusRTU_串口_设备信息"
)


def connect() -> Application:
    return Application(backend="win32").connect(process=MCGS_PROCESS_ID)


def add_base_zero_driver() -> None:
    app = connect()
    window = app.top_window()
    if window.window_text() != "设备管理":
        raise RuntimeError(f"当前窗口不是设备管理，而是：{window.window_text()}")

    target = window["Tree1"].get_item(
        "\\所有设备\\通用设备\\Modbus\\ModbusRtuBaseZero"
    )
    target.select()
    time.sleep(0.3)
    window["增加"].click()
    time.sleep(0.5)

    confirmation = app.top_window()
    if "所有设备添加到选定设备框" in confirmation.window_text():
        confirmation["是(&Y)"].click()
        time.sleep(0.5)
        window = app.top_window()

    window["确认"].click()
    time.sleep(1.0)
    print("ModbusRtuBaseZero 已加入设备工具箱")


def dump_top_window() -> None:
    app = connect()
    window = app.top_window()
    print(f"TOP: {window.window_text()} [{window.class_name()}]")
    window.print_control_identifiers()


def confirm_add_all() -> None:
    app = connect()
    window = app.top_window()
    window["是(&Y)"].click()
    time.sleep(0.5)
    manager = app.top_window()
    if manager.window_text() == "设备管理":
        manager["确认"].click()
        time.sleep(1.0)
    print("设备工具箱选择已确认")


def dump_device_window() -> None:
    app = connect()
    for window in app.windows():
        if window.window_text().startswith("组态检查列表"):
            window.close()

    main = app.window(handle=MCGS_MAIN_HANDLE)
    print(f"MAIN: {main.window_text()}")
    for index, tree in enumerate(main.children(class_name="SysTreeView32")):
        print(f"TREE {index}, hwnd={tree.handle}")

        def walk(item, level: int = 0) -> None:
            print(f"{'  ' * level}{item.text()!r}")
            try:
                item.expand()
            except Exception:
                pass
            for child in item.children():
                walk(child, level + 1)

        for root in tree.roots():
            walk(root)

    for window in app.windows():
        if window.window_text() != "设备工具箱":
            continue
        for list_view in window.children(class_name="SysListView32"):
            print("TOOLBOX:", list_view.texts())


def open_existing_modbus_device() -> None:
    app = connect()
    main = app.window(handle=MCGS_MAIN_HANDLE)
    tree = main.children(class_name="SysTreeView32")[0]
    root = tree.roots()[0]
    device = root.children()[0]
    print(f"打开设备：{device.text()}")
    device.select()
    tree.set_focus()
    tree.type_keys("{ENTER}")
    time.sleep(1.0)
    for window in app.windows():
        if window.is_visible():
            print(f"WINDOW: {window.window_text()} [{window.class_name()}]")


def export_device_info() -> None:
    app = connect()
    editor = app.top_window()
    if editor.window_text() != "设备编辑窗口":
        editors = [
            window
            for window in app.windows()
            if window.is_visible() and window.window_text() == "设备编辑窗口"
        ]
        if not editors:
            raise RuntimeError("未找到可见的设备编辑窗口")
        editor = editors[-1]
    print(f"导出设备窗口句柄: {editor.handle}")
    editor["设备信息导出"].click()
    time.sleep(1.0)
    app.top_window().print_control_identifiers()


def complete_device_info_export() -> None:
    app = connect()
    dialog = app.top_window()
    if dialog.window_text() != "另存为":
        raise RuntimeError(f"当前窗口不是另存为，而是: {dialog.window_text()}")
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    filename = dialog.child_window(class_name="Edit", found_index=0)
    filename.set_focus()
    send_keys("^a")
    send_keys(str(EXPORT_PATH), with_spaces=True)
    send_keys("%s")
    time.sleep(2.0)
    print(f"设备信息已导出到: {EXPORT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=(
            "add-base-zero-driver",
            "confirm-add-all",
            "complete-device-info-export",
            "dump-device-window",
            "dump-top-window",
            "export-device-info",
            "open-existing-modbus-device",
        ),
    )
    args = parser.parse_args()

    actions = {
        "add-base-zero-driver": add_base_zero_driver,
        "confirm-add-all": confirm_add_all,
        "complete-device-info-export": complete_device_info_export,
        "dump-device-window": dump_device_window,
        "dump-top-window": dump_top_window,
        "export-device-info": export_device_info,
        "open-existing-modbus-device": open_existing_modbus_device,
    }
    actions[args.action]()


if __name__ == "__main__":
    main()
