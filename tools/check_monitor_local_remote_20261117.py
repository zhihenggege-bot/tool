"""Real Tk callbacks and event loop; optional stopped-board read/write checks."""
import json
from pathlib import Path
import sys
import time
import tkinter as tk

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'psc330_monitor_tool/psc330_monitor'))
import app

live = '--live' in sys.argv
D = R / '测试证据/本地远程X02_20261117'
root = tk.Tk()
root.withdraw()
ui = app.Psc330MonitorApp(root)
p = ui.control_source_panel
rows, errors = [], []
app.messagebox.showerror = lambda *args: errors.append(str(args))


def check(name, value):
    rows.append(dict(name=name, passed=bool(value)))
    assert value, name


class Device:
    is_open = True

    def __init__(self):
        self.values = {a: 0 for a in range(2900)}
        self.values.update({2622: 330, 2623: 10, 2624: 64})
        self.writes = []

    def read_holding_registers(self, slave, a, n):
        return [self.values[a + i] for i in range(n)]

    def write_single_register(self, slave, a, v):
        self.writes.append((a, v))
        self.values[a] = v

    def close(self):
        self.is_open = False


def run(operation, value=None, expect_error=False):
    ui._run_control_source_job(operation, value)
    deadline = time.monotonic() + 15

    def finished():
        if not p.busy or time.monotonic() > deadline:
            root.quit()
        else:
            root.after(30, finished)

    root.after(30, finished)
    root.mainloop()
    check(f'{operation}/{value}/completed', not p.busy)
    check(f'{operation}/{value}/result', ('操作未完成' in p.status.get()) == expect_error)


result = dict(version=app.MONITOR_VERSION, hardware_access=live, rows=rows)
try:
    if live:
        ui.client.open('COM6', app.DEFAULT_BAUD)
        read = lambda a, n=1: ui.client.read_holding_registers(1, a, n)
        before = {a: read(a)[0] for a in (163, 164, 165, 166, 398, 1388, 709, 1319, 1341)}
        result['before'] = before
        run('read')
        if before[163] == 1:
            result['scope'] = '设备已由现场切为远程运行；核验远程状态与写入隔离，不停机或修改模式'
            check('live/remote-feedback', ui.values.get(714) == 1)
            check('live/manual-and-timer-disabled', all(str(b['state']) == 'disabled' for b in (ui.manual_start_button, ui.manual_stop_button, p.timer_button, *p.target_buttons)))
            run('source', 1)  # Same-value write/readback, no source transition.
            run('manual', 0, expect_error=True)
            run('timer_target', 0, expect_error=True)
        else:
            check('live/original-stopped-local-manual', all(before[a] == 0 for a in (163, 165, 166, 398, 1388, 709)))
            run('source', 0)
            run('timer_mode', 1)
            check('live/timer-mode-readback', read(165)[0] == 1 and read(1388)[0] == 0)
            run('timer_target', 0)
            run('timer_mode', 0)
        after = {a: read(a)[0] for a in before}
        result['after'] = after
        check('live/restore-matches', after == before)
        result['versions'] = read(2622, 18)
        result['outputs_after'] = {'do': read(814, 8), 'ao': read(914, 10)}
    else:
        device = Device()
        ui.client = device
        run('read')
        check('ui/two-source-choices', tuple(p.source_combo['values']) == ('本地', '远程 X02'))
        check('ui/initial-manual-enabled', str(ui.manual_start_button['state']) == 'normal')
        p.source.set('远程 X02')
        ui._refresh_tables()
        check('ui/poll-preserves-selection', p.source.get() == '远程 X02')
        run('source', 1)
        check('ui/remote-disables-local', all(str(b['state']) == 'disabled' for b in (ui.manual_start_button, ui.manual_stop_button, p.timer_button, *p.target_buttons)))
        writes = list(device.writes)
        run('manual', 1, expect_error=True)
        check('ui/remote-manual-no-writes', device.writes == writes)
        run('source', 0)
        run('timer_mode', 1)
        check('ui/timer-enables-targets-only', str(p.target_buttons[0]['state']) == 'normal' and str(ui.manual_start_button['state']) == 'disabled')
        run('timer_target', 0)
        run('timer_mode', 0)
        # Exercise actual manual button callbacks, which must never change 163.
        writes = len(device.writes)
        ui.manual_start_button.invoke()
        deadline = time.monotonic() + 3
        def wait_manual():
            if not p.busy or time.monotonic() > deadline:
                root.quit()
            else:
                root.after(30, wait_manual)
        root.after(30, wait_manual)
        root.mainloop()
        check('ui/manual-callback-only-398', device.writes[writes:] == [(398, 1)])
        device.values[2624] = 63
        run('read')
        check('ui/old-firmware-disables-source', str(p.source_button['state']) == 'disabled')
        device.values[2624] = 64
        run('read')
        check('poll/covers-source-feedback', any(b.start <= 714 < b.start + b.count for b in app.POLL_BLOCKS))
        check('poll/covers-timer-target', any(b.start <= 1388 < b.start + b.count for b in app.POLL_BLOCKS))
    check('ui/no-unhandled-errors', not errors)
    ui.disconnect()
    check('ui/disconnect-disables', str(p.source_button['state']) == 'disabled' and str(ui.manual_start_button['state']) == 'disabled')
    result['passed'] = True
except Exception as exc:
    result['passed'] = False
    result['error'] = repr(exc)
    raise
finally:
    ui.client.close()
    root.destroy()
    dest = D / ('monitor_live.json' if live else 'monitor_gui.json')
    D.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(version=app.MONITOR_VERSION, live=live, passed=result.get('passed'), checks=len(rows)), ensure_ascii=False))
