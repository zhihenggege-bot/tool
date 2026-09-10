# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
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

from pywinauto import Application, Desktop  # noqa: E402


ERROR_TEXT = "程序执行出现异常"
MAIN_TITLE = "McgsPro组态环境"


def visible_windows(process_id: int) -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []
    for window in Desktop(backend="win32").windows(process=process_id):
        if not window.is_visible():
            continue
        windows.append(
            {
                "handle": window.handle,
                "title": window.window_text(),
                "class_name": window.class_name(),
            }
        )
    return windows


def find_error_dialog(process_id: int):
    for window in Desktop(backend="win32").windows(process=process_id):
        if not window.is_visible():
            continue
        try:
            texts = " ".join(window.texts())
        except Exception:
            texts = window.window_text()
        if ERROR_TEXT in texts:
            return window
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--compat", default="")
    parser.add_argument("--wait", type=float, default=8.0)
    args = parser.parse_args()

    if args.compat:
        os.environ["__COMPAT_LAYER"] = args.compat
    else:
        os.environ.pop("__COMPAT_LAYER", None)

    result: dict[str, object] = {
        "compat": args.compat,
        "project": args.project,
        "launched": False,
        "main_window": False,
        "animation_clicked": False,
        "crashed": False,
        "windows": [],
    }

    app = None
    try:
        command = f'"{args.exe}" "{args.project}"'
        app = Application(backend="win32").start(command)
        result["launched"] = True
        result["process_id"] = app.process

        main_window = app.window(title=MAIN_TITLE)
        main_window.wait("visible ready", timeout=20)
        result["main_window"] = True

        animation = main_window.child_window(
            title="动画组态",
            class_name="Button",
        )
        animation.wait("visible enabled ready", timeout=10)
        animation.click()
        result["animation_clicked"] = True

        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline:
            error = find_error_dialog(app.process)
            if error is not None:
                result["crashed"] = True
                result["error_title"] = error.window_text()
                break
            time.sleep(0.25)

        result["windows"] = visible_windows(app.process)
        result["passed"] = (
            result["animation_clicked"]
            and not result["crashed"]
            and len(result["windows"]) > 0
        )
    except Exception as exc:
        result["exception"] = f"{type(exc).__name__}: {exc}"
        result["passed"] = False
    finally:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if app is not None:
            try:
                app.kill()
            except Exception:
                pass

    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
