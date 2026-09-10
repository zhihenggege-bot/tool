# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / (
    ".tools32" if sys.maxsize <= 2**32 else ".tools"
)
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
from pywinauto.keyboard import send_keys  # noqa: E402
from pywinauto import mouse  # noqa: E402


MCGS_EXE = Path(r"D:\McgsPro\Program\McgsSetPro.exe")


def window_record(window) -> dict[str, object]:
    rectangle = window.rectangle()
    return {
        "handle": window.handle,
        "title": window.window_text(),
        "class_name": window.class_name(),
        "visible": window.is_visible(),
        "enabled": window.is_enabled(),
        "rectangle": [
            rectangle.left,
            rectangle.top,
            rectangle.right,
            rectangle.bottom,
        ],
    }


def process_windows(process_id: int) -> list:
    return [
        window
        for window in Desktop(backend="win32").windows(process=process_id)
        if window.is_visible()
    ]


def find_main_window(process_id: int, timeout: float = 20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        candidates = process_windows(process_id)
        candidates.sort(
            key=lambda window: window.rectangle().width()
            * window.rectangle().height(),
            reverse=True,
        )
        for window in candidates:
            if (
                window.class_name().startswith("Afx:")
                and window.window_text() == "McgsPro\u7ec4\u6001\u73af\u5883"
            ):
                return window
        for window in candidates:
            if (
                window.window_text().startswith(
                    "McgsPro\u7ec4\u6001\u73af\u5883"
                )
                and window.class_name().startswith("Afx:")
            ):
                return window
        time.sleep(0.25)
    raise TimeoutError("MCGS main window was not found")


def mcgs_process_ids() -> set[int]:
    result: set[int] = set()
    for window in Desktop(backend="win32").windows():
        try:
            if (
                window.window_text().startswith(
                    "McgsPro\u7ec4\u6001\u73af\u5883"
                )
                and (
                    window.class_name().startswith("Afx:")
                    or window.class_name() == "#32770"
                )
            ):
                result.add(window.process_id())
        except Exception:
            continue
    return result


def launch_project(project: Path) -> tuple[Application, object]:
    if not MCGS_EXE.exists():
        raise FileNotFoundError(MCGS_EXE)
    if not project.exists():
        raise FileNotFoundError(project)

    before = mcgs_process_ids()
    launcher = Application(backend="win32").start(
        f'"{MCGS_EXE}" "{project}"',
        timeout=20,
    )
    deadline = time.monotonic() + 20
    process_id = launcher.process
    while time.monotonic() < deadline:
        candidates = mcgs_process_ids()
        new_candidates = candidates - before
        if new_candidates:
            process_id = max(new_candidates)
        try:
            main = find_main_window(process_id, timeout=0.5)
            break
        except TimeoutError:
            time.sleep(0.2)
    else:
        raise TimeoutError("MCGS editor process was not found")

    app = Application(backend="win32").connect(process=process_id)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if main.is_visible() and main.is_enabled():
            break
        time.sleep(0.2)
    else:
        raise TimeoutError("MCGS main window did not become ready")
    return app, main


def connect_process(process_id: int) -> tuple[Application, object]:
    app = Application(backend="win32").connect(process=process_id)
    return app, find_main_window(process_id)


def dump_descendants(window) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for control in window.descendants():
        try:
            record = window_record(control)
            record["control_id"] = control.control_id()
            records.append(record)
        except Exception as exc:
            records.append({"error": f"{type(exc).__name__}: {exc}"})
    return records


def find_process_window(process_id: int, title: str):
    matches = [
        window
        for window in process_windows(process_id)
        if window.window_text() == title
    ]
    if len(matches) != 1:
        raise LookupError(
            f"window title {title!r} matched {len(matches)} windows"
        )
    return matches[0]


def select_workspace(
    main,
    process_id: int,
    button_index: int | None,
    button_title: str | None,
) -> None:
    if button_title is not None:
        buttons_by_handle = {}
        for window in process_windows(process_id):
            candidates = []
            if window.class_name() == "Button":
                candidates.append(window)
            candidates.extend(window.descendants(class_name="Button"))
            for button in candidates:
                if button.is_visible() and button.is_enabled():
                    buttons_by_handle[button.handle] = button
        matches = [
            button for button in buttons_by_handle.values()
            if button.window_text() == button_title
        ]
        if len(matches) != 1:
            raise LookupError(
                f"button title {button_title!r} matched {len(matches)} controls"
            )
        matches[0].click()
        return

    buttons = [
        control
        for control in main.descendants(class_name="Button")
        if control.is_visible() and control.is_enabled()
    ]
    if button_index is None:
        return
    if button_index >= len(buttons):
        raise IndexError(
            f"button index {button_index} is out of range; "
            f"visible buttons={len(buttons)}"
        )
    buttons[button_index].click()


def select_tab(main, tab_title: str) -> None:
    tabs = [
        control
        for control in main.descendants(class_name="SysTabControl32")
        if control.is_visible() and control.is_enabled()
    ]
    if len(tabs) != 1:
        raise LookupError(f"expected one visible tab control, found {len(tabs)}")
    tabs[0].select(tab_title)


def open_list_item(window, item_title: str) -> None:
    lists = [
        control
        for control in window.descendants(class_name="SysListView32")
        if control.is_visible() and control.is_enabled()
    ]
    if len(lists) != 1:
        raise LookupError(f"expected one visible list view, found {len(lists)}")
    item = lists[0].get_item(item_title)
    item.select()
    item.double_click_input()


def select_tree_path(window, tree_path: str) -> None:
    trees = [
        control
        for control in window.descendants(class_name="SysTreeView32")
        if control.is_visible() and control.is_enabled()
    ]
    if len(trees) != 1:
        raise LookupError(f"expected one visible tree view, found {len(trees)}")
    path = [part.strip() for part in tree_path.split(">") if part.strip()]
    if not path:
        raise ValueError("tree path must contain at least one item")
    item = trees[0].get_item(path)
    item.ensure_visible()
    item.select()


def save_screenshots(process_id: int, output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for index, window in enumerate(process_windows(process_id)):
        title = "".join(
            character if character.isalnum() else "_"
            for character in window.window_text()
        ).strip("_")
        title = title[:60] or "untitled"
        path = output_dir / f"{index:02d}_{window.handle}_{title}.png"
        window.capture_as_image().save(path)
        paths.append(str(path))
    return paths


def inspect_project(args) -> int:
    project = Path(args.project).resolve()
    output_dir = Path(args.output_dir).resolve()
    app = None
    report: dict[str, object] = {
        "project": str(project),
        "action": "inspect",
    }
    try:
        if args.process_id is not None:
            app, main = connect_process(args.process_id)
        else:
            app, main = launch_project(project)
        report["process_id"] = app.process
        report["main"] = window_record(main)
        report["main_descendants"] = dump_descendants(main)
        target = (
            find_process_window(app.process, args.target_window_title)
            if args.target_window_title is not None
            else main
        )

        if args.send_keys is not None:
            target.set_focus()
            send_keys(args.send_keys)
            time.sleep(args.wait)

        if args.click is not None:
            x_text, y_text = args.click.split(",", 1)
            mouse.click(coords=(int(x_text), int(y_text)))
            time.sleep(args.wait)

        if args.tab_title is not None:
            select_tab(target, args.tab_title)
            time.sleep(args.wait)

        if args.tree_path is not None:
            select_tree_path(target, args.tree_path)
            time.sleep(args.wait)

        if args.list_item is not None:
            open_list_item(target, args.list_item)
            time.sleep(args.wait)

        if args.button_index is not None or args.button_title is not None:
            select_workspace(
                main,
                app.process,
                args.button_index,
                args.button_title,
            )
            time.sleep(args.wait)

        report["windows"] = [
            {
                **window_record(window),
                "descendants": dump_descendants(window),
            }
            for window in process_windows(app.process)
        ]
        report["screenshots"] = save_screenshots(app.process, output_dir)
        report["success"] = True
    except Exception as exc:
        report["success"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
        if (
            app is not None
            and args.process_id is None
            and not args.keep_open
        ):
            try:
                app.kill()
            except Exception:
                pass
    return 0 if report.get("success") else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--project", required=True)
    inspect_parser.add_argument(
        "--output-dir",
        default=str(ROOT / "captures"),
    )
    inspect_parser.add_argument("--button-index", type=int)
    inspect_parser.add_argument("--button-title")
    inspect_parser.add_argument("--target-window-title")
    inspect_parser.add_argument("--send-keys")
    inspect_parser.add_argument("--click")
    inspect_parser.add_argument("--tab-title")
    inspect_parser.add_argument("--tree-path")
    inspect_parser.add_argument("--list-item")
    inspect_parser.add_argument("--process-id", type=int)
    inspect_parser.add_argument("--wait", type=float, default=2.0)
    inspect_parser.add_argument("--keep-open", action="store_true")
    inspect_parser.set_defaults(func=inspect_project)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Python 3.12 can trigger a comtypes teardown fault after pywinauto exits.
    # The automation work is already complete, so bypass that broken teardown.
    os._exit(exit_code)
