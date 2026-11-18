"""Authorized V10.64 deployment and source tests; normal Modbus stimuli only."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import argparse
import hashlib
import json
import sys
import time
import traceback

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'psc330_monitor_tool/psc330_monitor'))
from app import ModbusRtuClient, DEFAULT_BAUD
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from verify_board_flash_vs_hex import parse_hex, blocks_of

D = R / '测试证据/本地远程X02_20261117'
I = R / '.codex-tmp/local_remote_v1064_20261117/BENCH_ONLY_3S'
OLD = R / '.codex-tmp/vfd_unload_min30_v1063_v1246_20261117/BENCH_ONLY_3S'
UID = '50FF73067289515145451367'
EXPECTED = [330, 10, 64, 2026, 11, 17, 316, 12, 46, 2026, 11, 17, 316, 12, 46, 2026, 11, 17]
D.mkdir(parents=True, exist_ok=True)


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='milliseconds')


def dump(p, q):
    temp = p.with_suffix(p.suffix + '.tmp')
    temp.write_text(json.dumps(q, ensure_ascii=False, indent=2), 'utf8')
    temp.replace(p)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def event(kind, **kw):
    with (D / 'events.jsonl').open('a', encoding='utf8') as f:
        f.write(json.dumps({**dict(at=now(), t=time.monotonic(), kind=kind), **kw}, ensure_ascii=False) + '\n')


def client():
    c = ModbusRtuClient()
    c.open('COM6', DEFAULT_BAUD)
    return c


def verify(t, path):
    mem = parse_hex(path)
    for lo, hi in blocks_of(mem):
        for a in range(lo, hi, 4096):
            n = min(4096, hi - a)
            assert bytes(t.read_memory_block8(a, n)) == bytes(mem[a + j] for j in range(n)), (path.name, hex(a))
    return len(mem)


def rd(c, a, n=1):
    try:
        values = c.read_holding_registers(1, a, n)
        event('read', address=a, count=n, values=values)
        return values
    except Exception as exc:
        event('read_error', address=a, count=n, error=repr(exc))
        raise


def wr(c, a, v):
    event('write_issue', address=a, value=v)
    c.write_single_register(1, a, v & 65535)
    actual = rd(c, a)[0]
    assert actual == (v & 65535), (a, v, actual)
    event('write_verified', address=a, value=v)


def snapshot(c, label):
    q = dict(at=now(), t=time.monotonic(), label=label, state=rd(c, 700, 15),
             do=rd(c, 814, 8) + rd(c, 1366, 8), ao=rd(c, 914, 10),
             x02=rd(c, 1352)[0], command=rd(c, 398)[0], source=rd(c, 163, 4),
             target=rd(c, 1388)[0], faults=rd(c, 594, 33),
             outdoor_status=[rd(c, 1555, 2), rd(c, 1625, 2)])
    event('snapshot', **q)
    return q


def off(q):
    return q['state'][9] == 0 and not any(q['ao']) and not any(v for j, v in enumerate(q['do']) if j != 5)


def deploy():
    path = D / 'deployment.json'
    assert not path.exists(), 'Preserve previous deployment evidence'
    m = json.loads((I / 'manifest.json').read_text('utf8'))
    assert all(sha(R / n) == h for n, h in m['source_inventory'].items())
    assert all(sha(I / n) == h for n, h in m['artifacts'].items())
    assert json.loads((I.parent / 'local_remote_ARM.json').read_text('utf8'))['passed']
    original = json.loads((D / 'preflight.json').read_text('utf8'))
    q = dict(started=now(), authorization='烧录测试', profile='BENCH_ONLY_3S',
             unchanged_outdoor=True, boards=[], source_inventory=m['source_inventory'], artifacts=m['artifacts'])
    dump(path, q)
    c = client()
    try:
        q['versions_before'] = rd(c, 2622, 18)
        assert q['versions_before'] == original['versions']
        q['before'] = snapshot(c, 'before_flash')
        assert off(q['before']) and q['before']['command'] == 0
        assert rd(c, 1300) == [0] and rd(c, 1299) == [15107]
        q['config_before'] = original['config']
        assert rd(c, 1341) == [30]
        dump(path, q)
    finally:
        c.close()
    try:
        for label, uid, target, device, stem in (
            ('316_WJ1', '56FF6E065067545548562587', 'stm32f103rc', 0x414, 'PSC316_V12.46_BENCH_ONLY_3S'),
            ('316_WJ2', '30FF71064E4B323247481843', 'stm32f103rc', 0x414, 'PSC316_V12.46_BENCH_ONLY_3S'),
            ('330', UID, 'stm32f407ze', 0x413, 'PSC330_V10.63_BENCH_ONLY_3S')):
            row = dict(board=label, probe=uid, programmed=False)
            q['boards'].append(row)
            with ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override=target,
                    options={'connect_mode': 'attach', 'resume_on_disconnect': False, 'frequency': 1000000}) as ss:
                t = ss.target
                assert t.read32(0xE0042000) & 0xfff == device
                row['before_verified_bytes'] = verify(t, OLD / (stem + '.hex'))
                if label == '330':
                    t.halt()
                    debug = t.read32(0xE0042008)
                    started = False
                    complete = False
                    try:
                        for suffix, a, size in (('flash', 0x08000000, 512 * 1024), ('sram', 0x20000000, 128 * 1024)):
                            dest = D / ('330_before_' + suffix + '.bin')
                            assert not dest.exists()
                            dest.write_bytes(bytes(t.read_memory_block8(a, size)))
                            row[suffix + '_backup'] = dict(file=dest.name, bytes=size, sha256=sha(dest))
                        dump(path, q)
                        t.write32(0xE0042008, debug | 0x1800)
                        t.reset_and_halt()
                        t.write32(0xE0042008, t.read32(0xE0042008) | 0x1800)
                        image = I / 'PSC330_V10.64_BENCH_ONLY_3S.hex'
                        row['programming_started'] = now()
                        started = True
                        dump(path, q)
                        FileProgrammer(ss, chip_erase='sector', trust_crc=False).program(str(image))
                        row['programmed'] = True
                        row['verified_bytes'] = verify(t, image)
                        row['flash_verified'] = complete = True
                        dump(path, q)
                    finally:
                        if complete:
                            t.write32(0xE0042008, debug)
                            t.reset()
                        elif not started:
                            t.write32(0xE0042008, debug)
                            t.resume()
                        else:
                            t.halt()
                            row['recovery_required'] = True
                            dump(path, q)
                else:
                    row['flash_verified'] = True
                    row['verified_bytes'] = row['before_verified_bytes']
                dump(path, q)
            print('FLASH VERIFIED', label, 'programmed', row['programmed'], row['verified_bytes'], flush=True)
        c = client()
        try:
            deadline = time.monotonic() + 90
            while True:
                try:
                    v = rd(c, 2622, 18)
                    state = rd(c, 700, 15)
                    if v == EXPECTED and state[0] != 10:
                        break
                except Exception:
                    pass
                assert time.monotonic() < deadline, 'boot or version timeout'
                time.sleep(.5)
            # Allow the ordinary input and mirror refill to settle; never alter RAM.
            time.sleep(6)
            q['versions_after'] = rd(c, 2622, 18)
            q['config_after'] = {}
            for a, n in ((0, 125), (125, 125), (250, 125), (375, 125), (1229, 60),
                         (1298, 2), (1319, 26), (1388, 12), (1830, 96), (2680, 98)):
                q['config_after'].update({str(a + j): v for j, v in enumerate(rd(c, a, n))})
            changes = {a: [v, q['config_after'][a]] for a, v in q['config_before'].items() if q['config_after'][a] != v}
            q['diagnostic_changes'] = {a: v for a, v in changes.items() if int(a) in (167, 373) or
                (1830 <= int(a) < 1926 and (int(a) - 1830) % 48 in range(42, 47))}
            q['configuration_changes'] = {a: v for a, v in changes.items() if a not in q['diagnostic_changes']}
            assert not q['configuration_changes'], q['configuration_changes']
            q['after'] = snapshot(c, 'post_flash')
            assert off(q['after']) and not any(q['after']['faults'])
            assert rd(c, 1341) == [30]
        finally:
            c.close()
        q.update(passed=True, finished=now())
        dump(path, q)
    except BaseException:
        q.update(error=traceback.format_exc(), finished=now())
        dump(path, q)
        raise


def tests():
    path = D / 'board_tests.json'
    assert not path.exists()
    c = client()
    original = json.loads((D / 'deployment.json').read_text('utf8'))['config_after']
    q = dict(started=now(), firmware=EXPECTED, profile='BENCH_ONLY_3S', cases=[],
             scope='Actual board normal Modbus commands and X02 polarity input simulation; software outputs. No output/status RAM writes, physical contact or formal timing acceptance.')
    touched = set()

    def save():
        dump(path, q)

    def setv(a, v):
        assert str(a) in original, a
        touched.add(a)
        wr(c, a, v)

    def wait(label, pred, timeout=70, hold=0):
        end = time.monotonic() + timeout
        held = None
        while True:
            s = snapshot(c, label)
            assert not any(s['faults']), (label, 'unexpected_fault', s)
            if pred(s):
                if held is None:
                    held = time.monotonic()
                if time.monotonic() - held >= hold:
                    return s
            else:
                held = None
            assert time.monotonic() < end, (label, 'timeout', s)
            time.sleep(.2)

    def stop():
        setv(163, 0)
        setv(1388, 0)
        setv(165, 0)
        setv(398, 0)
        return wait('normal_stop', off)

    def contact(v):
        before = rd(c, 1352)[0]
        if before != v:
            setv(157, 1 - rd(c, 157)[0])
        return wait('X02_input_' + str(v), lambda s: s['x02'] == v, 10, .5)

    def baseline():
        stop()
        for a, v in {164: 0, 236: 2, 132: 0, 135: 0, 328: 0, 329: 2, 330: 0, 331: 0}.items():
            if rd(c, a) != [v]:
                setv(a, v)
        contact(0)

    def running(s):
        return s['state'][9] == 2 and s['do'][3] == 1 and s['ao'][7] > 0

    def case(name, action):
        row = dict(name=name, started=now(), passed=False)
        q['cases'].append(row)
        save()
        try:
            baseline()
            row['result'] = action()
            row['passed'] = True
        except Exception:
            row['error'] = traceback.format_exc()
        finally:
            row['after_normal_stop'] = stop()
            row['finished'] = now()
            save()
        print('BOARD CASE', name, row['passed'], flush=True)

    def local_manual():
        setv(398, 1)
        a = wait('local_manual_open_X02', running, hold=8)
        contact(1)
        b = wait('local_manual_closed_X02', running, hold=4)
        contact(0)
        z = wait('local_manual_reopen_X02', running, hold=6)
        setv(398, 0)
        return dict(open=a, closed=b, reopened=z, stopped=wait('manual_stop', off))

    def local_timer():
        setv(165, 1)
        wait('local_timer_mode', lambda s: s['state'][14] == 3)
        time.sleep(1)
        setv(1388, 1)
        a = wait('local_timer_open_X02', running, hold=6)
        assert a['state'][0] == 5
        contact(1)
        b = wait('local_timer_closed_X02', running, hold=4)
        contact(0)
        setv(1388, 0)
        return dict(start=a, contact_toggle=b, stopped=wait('timer_stop', off))

    def remote(timer):
        setv(165, timer)
        setv(163, 1)
        setv(1388, 1)
        c.write_single_register(1, 398, 1)
        event('write_issue', address=398, value=1, note='remote ignored command; firmware may clear before readback')
        a = wait('remote_open_contact_ignores_local_commands', lambda s: off(s) and s['command'] == 0, hold=5)
        contact(1)
        b = wait('remote_X02_start', running)
        assert b['state'][14] == 1 and b['state'][0] == 4
        setv(1388, 0)
        c.write_single_register(1, 398, 0)
        event('write_issue', address=398, value=0, note='remote ignored local stop')
        z = wait('remote_ignores_HMI_and_timer_stop', running, hold=5)
        contact(0)
        return dict(open=a, start=b, ignores_stop=z, stopped=wait('remote_X02_stop', off))

    def handover():
        setv(398, 1)
        wait('handover_local_running', running)
        contact(1)
        setv(163, 1)
        rows = []
        end = time.monotonic() + 70
        saw_stop = False
        while True:
            s = snapshot(c, 'local_to_remote_closed_contact')
            rows.append(s)
            if s['state'][9] in (0, 3) or s['command'] == 0:
                saw_stop = True
            if saw_stop and running(s) and s['command'] == 1:
                break
            assert time.monotonic() < end, 'handover did not stop/restart'
            time.sleep(.12)
        setv(163, 0)
        a = wait('remote_to_local_no_inherited_start', lambda s: off(s) and s['command'] == 0, hold=5)
        setv(398, 1)
        b = wait('new_local_press_after_handover', running)
        return dict(transition=rows, local_stopped=a, local_restart=b)

    def timer_return():
        setv(165, 1)
        setv(163, 1)
        setv(1388, 1)
        contact(1)
        wait('remote_before_return_to_timer', running)
        setv(163, 0)
        a = wait('stale_timer_target_must_not_restart', off, hold=5)
        setv(1388, 0)
        time.sleep(1)
        setv(1388, 1)
        b = wait('timer_zero_handshake_restart', running)
        assert b['state'][0] == 5
        return dict(stale_target_stopped=a, handshake_restart=b)

    try:
        assert rd(c, 2622, 18) == EXPECTED
        assert off(snapshot(c, 'test_preflight'))
        case('本地手动忽略X02，手动正常启停', local_manual)
        case('本地独立定时忽略X02，定时正常启停', local_timer)
        case('远程X02启停，手动与1388不接管（165=0）', lambda: remote(0))
        case('远程X02优先于定时（165=1）', lambda: remote(1))
        case('运行中本地远程切换，清除旧命令', handover)
        case('远程返回本地定时必须重新零目标握手', timer_return)
    finally:
        try:
            q['before_restore'] = stop()
            # Original source is local with timer disabled: restore it last,
            # after input polarity and all fan/mode settings have returned.
            for a in sorted(touched - {163, 164, 165, 166, 236, 398, 1388}):
                wr(c, a, original[str(a)])
            for a in (236, 1388, 165, 163, 164, 166):
                if a in touched:
                    wr(c, a, original[str(a)])
            c.write_single_register(1, 398, 0)
            q['restore_mismatches'] = {str(a): [original[str(a)], rd(c, a)[0]] for a in touched
                if a != 398 and rd(c, a)[0] != original[str(a)]}
            assert not q['restore_mismatches'], q['restore_mismatches']
            q['restored'] = True
            q['final'] = snapshot(c, 'after_restore')
            assert off(q['final']) and not any(q['final']['faults'])
            assert rd(c, 1341) == [30] and rd(c, 1319) == [1]
            q['passed'] = all(row['passed'] for row in q['cases'])
        except BaseException:
            q['restoration_error'] = traceback.format_exc()
            raise
        finally:
            q['finished'] = now()
            save()
            c.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('deploy', 'tests'))
    args = p.parse_args()
    globals()[args.action]()
