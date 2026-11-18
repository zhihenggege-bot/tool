"""Offline execution of the generated MCGS subset; never opens hardware.

This checks the actual delivered script, not an independently rewritten
scheduler. It does not certify the MCGS compiler or a device driver.
"""
from pathlib import Path
import csv
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'MCGSPro周定时_每天一时段'
DAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
MODE = 'R0165_定时模式使能'
TARGET = 'R1388_定时运行目标'
STATUS = 'R0700_系统状态'
STEP = 'R0709_开关机步骤'
SOURCE = 'R0714_当前控制方式'
SELECTION = 'R0163_控制来源'


def compile_script():
    source = (ROOT / (PREFIX + '_循环脚本.txt')).read_text('utf-8-sig')
    lines, indent = [], 0
    for original in source.splitlines():
        line = original.split("'", 1)[0].strip()
        if not line:
            continue
        if line.lower() == 'endif':
            indent -= 1
            assert indent >= 0
            continue
        if line.lower() == 'else':
            indent -= 1
            lines.append('    ' * indent + 'else:')
            indent += 1
            continue
        if line.lower().startswith('if '):
            assert line.lower().endswith(' then'), line
            expr = line[3:-5].replace('<>', '!=')
            expr = re.sub(r'(?<![<>=!])=(?!=)', '==', expr)
            expr = re.sub(r'\bAnd\b', 'and', expr, flags=re.I)
            expr = re.sub(r'\bOr\b', 'or', expr, flags=re.I)
            lines.append('    ' * indent + 'if ' + expr + ':')
            indent += 1
            continue
        line = line.replace('$Week', 'clock_week').replace('$Hour', 'clock_hour').replace('$Minute', 'clock_minute')
        assert re.match(r'^\w+\s*=\s*[^=]+$', line), line
        lines.append('    ' * indent + line)
        name = line.split('=', 1)[0].strip()
        if name.startswith('R'):
            assert name in (MODE, TARGET), name
            lines.append('    ' * indent + f'writes.append(({name!r}, {name}))')
    assert indent == 0
    return compile('\n'.join(lines), str(ROOT / (PREFIX + '_循环脚本.txt')), 'exec')


CODE = compile_script()
with (ROOT / (PREFIX + '_变量表.csv.txt')).open(encoding='utf-8-sig', newline='') as handle:
    DEFAULT = {row['变量名']: int(row['内部变量初值']) for row in csv.DictReader(handle)}


def fresh():
    return dict(DEFAULT, clock_week=1, clock_hour=9, clock_minute=0,
                writes=[], **{STATUS: 4})


def run(env, minute=None):
    if minute is not None:
        day, within = divmod(minute, 1440)
        env.update(clock_week=(day + 1) % 7, clock_hour=within // 60, clock_minute=within % 60)
    env['writes'] = []
    exec(CODE, {'__builtins__': {}}, env)
    return env['writes']


def schedule(env, day, start, end, enabled=1):
    env[DAYS[day]] = enabled
    env[f'open_hour_{day+1}'], env[f'open_minute_{day+1}'] = divmod(start, 60)
    env[f'close_hour_{day+1}'], env[f'close_minute_{day+1}'] = divmod(end, 60)


def oracle(minute, periods):
    # Independent local-day formulation: today plus yesterday's carry-over.
    day, within = divmod(minute, 1440)
    for index, start, end in periods:
        if start < end and day == index and start <= within < end:
            return 1
        if start > end:
            if day == index and within >= start:
                return 1
            if day == (index + 1) % 7 and within < end:
                return 1
    return 0


def main():
    checks = 0

    def check(value, note):
        nonlocal checks
        assert value, note
        checks += 1

    # Full-week minute coverage, including adjacent-day overlap and Sunday wrap.
    for periods in [[], [(0, 480, 1080)], [(6, 1380, 120)],
                    [(i, 1320 if i % 2 else 480, 360 if i % 2 else 1080) for i in range(7)],
                    [(0, 1320, 360), (1, 300, 540), (6, 1380, 120)],
                    [(i, 0, 0) for i in range(7)]]:
        env = fresh()
        for day, start, end in periods:
            schedule(env, day, start, end)
        for minute in range(10080):
            check(run(env, minute) == [], 'Disabled schedule wrote device')
            check(env['nWTarget'] == oracle(minute, periods), f'Week boundary mismatch: {periods}, {minute}')

    # Standalone enabled-day coverage at the start/end and following midnight.
    for day in range(7):
        for start, end in [(480, 1080), (1380, 60), (0, 1), (1439, 0), (480, 480)]:
            env = fresh()
            schedule(env, day, start, end)
            for offset in [-1, 0, 1, 59, 60, 479, 480, 1080, 1380, 1439, 1440, 1499, 1500]:
                minute = (day * 1440 + offset) % 10080
                run(env, minute)
                check(env['nWTarget'] == oracle(minute, [(day, start, end)]), 'Single-day boundary')

    # Real script command sequence with one-cycle delayed firmware mode feedback.
    env = fresh()
    schedule(env, 0, 480, 1080)
    env.update(bWeeklyScheduleEnable=1)
    events = []
    for tick in range(18):
        writes = run(env)
        events.extend((tick, name, value) for name, value in writes)
        env[SOURCE] = 3 if env[MODE] else 0
        check(not any(name == TARGET and value == 1 for name, value in writes)
              or env['nWPhase'] == 3, 'Start target before initialization')
    check(env[TARGET] == 1 and env[MODE] == 1, 'Initial timed start')
    check(events[0][1:] == (MODE, 1), 'Wrong first write when target already zero')
    check(sum(name == TARGET and value == 1 for _, name, value in events) == 1, 'Redundant target writes')
    check(run(env, 1080) == [(TARGET, 0)], 'End boundary did not issue stop')

    # Cold controller with stale 1388=1: clear before mode/start, wait out DLAY.
    env = fresh()
    schedule(env, 0, 480, 1080)
    env.update(bWeeklyScheduleEnable=1, **{MODE: 1, SOURCE: 3, TARGET: 1, STATUS: 10})
    check(run(env) == [(TARGET, 0)], 'Stale target not cleared first')
    for _ in range(25):
        check(not any(name == TARGET and value == 1 for name, value in run(env)), 'Start during DLAY')
    env[STATUS] = 4
    for _ in range(12):
        run(env)
    check(env[TARGET] == 1, 'No start after DLAY and zero handshake')

    # HMI-only restart while running must not send an artificial stop.
    env = fresh()
    schedule(env, 0, 480, 1080)
    env.update(bWeeklyScheduleEnable=1, **{MODE: 1, SOURCE: 3, TARGET: 1, STEP: 2, STATUS: 5})
    check(run(env) == [] and env['nWPhase'] == 3, 'HMI restart interrupted active run')
    check(run(env, 1080) == [(TARGET, 0)], 'HMI restart failed to follow current window')

    # After source handover the firmware can still report step=2 for one scan,
    # but status=9 means normal stopping, not an active timed run.
    env = fresh()
    schedule(env, 0, 480, 1080)
    env.update(bWeeklyScheduleEnable=1, **{MODE: 1, SOURCE: 3, TARGET: 1, STEP: 2, STATUS: 9})
    check(run(env) == [(TARGET, 0)] and env['nWPhase'] == 1,
          'Source handover misidentified as uninterrupted timed operation')

    # Re-read mismatch retries, including a dropped write, cannot flood every tick.
    env = fresh()
    schedule(env, 0, 480, 1080)
    env.update(bWeeklyScheduleEnable=1, nWPhase=3, **{MODE: 1, SOURCE: 3})
    ticks = []
    for tick in range(16):
        env[TARGET] = 0  # Device keeps returning zero: write deliberately not delivered.
        if run(env):
            ticks.append(tick)
    check(ticks == [0, 5, 10, 15], f'Retry cadence {ticks}')

    # Exit wins even over broken clock/config; wait for actual stop step before 165=0.
    env.update(nWExit=1, bWeeklyScheduleEnable=0, nWRetry=0, clock_week=9,
               open_hour_1=30, **{TARGET: 1, STEP: 1})
    check(run(env) == [(TARGET, 0)], 'Exit did not clear target despite invalid clock')
    for _ in range(10):
        check(not any(name == MODE and value == 0 for name, value in run(env)), 'Exited before stopped')
    env[STEP] = 0
    for _ in range(10):
        run(env)
        env[SOURCE] = 3 if env[MODE] else 0
    check(env['nWExit'] == 0 and env[MODE] == 0 and env['nWResult'] == 6, 'Exit did not finish')

    # Invalid enabled-day values stop an enabled schedule, but ignored days don't invalidate it.
    env = fresh()
    schedule(env, 0, 480, 1080)
    env.update(bWeeklyScheduleEnable=1, open_hour_1=24, **{TARGET: 1})
    check(run(env) == [(TARGET, 0)] and env['nWResult'] == 102, 'Invalid settings did not stop')
    env[DAYS[0]] = 0
    run(env)
    check(env['nWConfigError'] == 0, 'Disabled day incorrectly invalidates schedule')

    # Remote must never be stopped/started by a saved or newly-enabled plan,
    # including an exit request and invalid time settings. Keep saved settings.
    for selected in (1, 2):
        for exiting in (0, 1, 2):
            env = fresh()
            schedule(env, 0, 480, 1080)
            env.update(bWeeklyScheduleEnable=1, nWExit=exiting, nWPhase=3,
                       **{SELECTION: selected, MODE: 1, TARGET: 1, SOURCE: selected, STEP: 2})
            for tick in range(12):
                check(run(env) == [], 'Nonlocal schedule wrote a device command')
            check(env['nWResult'] == 7 and env['nWExit'] == exiting and
                  env['bWeeklyScheduleEnable'] == 1 and env[MODE] == 1,
                  'Nonlocal pause lost saved plan or exit request')
            env[SELECTION] = 0
            env[SOURCE] = 3
            env[STEP] = 0
            check(run(env) == ([(MODE, 0)] if exiting == 2 else [(TARGET, 0)]),
                  'Return to local did not resume handshake/exit')

    print(json.dumps(dict(passed=True, assertions=checks, full_week_sets=6,
                         hardware_access=False, mcgs_compiler_checked=False), ensure_ascii=False))


if __name__ == '__main__':
    main()
