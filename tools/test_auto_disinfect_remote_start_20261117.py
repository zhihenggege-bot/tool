"""Time the real remote auto-disinfection start, using legal X02 polarity simulation."""
from pathlib import Path
import json
import sys
import time
import traceback

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'psc330_monitor_tool/psc330_monitor'))
from app import ModbusRtuClient, DEFAULT_BAUD
from datetime import datetime

D = R / '测试证据/自动消排毒远程启动_20261117'
D.mkdir(exist_ok=True)
P = D / 'board_start.json'
assert not P.exists(), 'Preserve previous test evidence'
c = ModbusRtuClient()
c.open('COM6', DEFAULT_BAUD)
q = dict(started=datetime.now().astimezone().isoformat(), stimulus='330正常协议，157极性模拟X02；没有RAM写入', events=[], passed=False)
start = time.monotonic()


def save():
    temp = P.with_suffix('.tmp')
    temp.write_text(json.dumps(q, ensure_ascii=False, indent=2), 'utf8')
    temp.replace(P)


def rd(a, n=1):
    return c.read_holding_registers(1, a, n)


def wr(a, v):
    q['events'].append(dict(t=time.monotonic(), at=datetime.now().astimezone().isoformat(), write=[a, v]))
    c.write_single_register(1, a, v)
    assert rd(a)[0] == v, (a, v, rd(a))
    save()


def sample(label):
    t = time.monotonic()
    s = dict(at=datetime.now().astimezone().isoformat(), t=t, seconds=t-start, label=label,
             state=rd(700, 15), source=rd(163, 4), mode=rd(236)[0], actual_mode=rd(1)[0],
             x02=rd(1352)[0], command=rd(398)[0], phase=rd(885, 3),
             do=rd(814, 8)+rd(1366, 8), ao=rd(914, 10), faults=rd(594, 33),
             outdoor_status=[rd(1555, 2), rd(1625, 2)])
    with (D / 'samples.jsonl').open('a', encoding='utf8') as f:
        f.write(json.dumps(s, ensure_ascii=False)+'\n')
    return s


def stopped(s):
    return s['state'][9] == 0 and not any(s['do']) and not any(s['ao'])


def wait(label, pred, seconds):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        s = sample(label)
        assert not any(s['faults']), ('unexpected_fault', s)
        if pred(s):
            return s
        time.sleep(.1)
    raise AssertionError(('timeout', label, s))


original = {}
try:
    q['versions'] = rd(2622, 18)
    q['timing'] = rd(1298, 2)
    assert q['versions'][:3] == [330, 10, 64]
    assert q['timing'][1] == 15107
    before = sample('before')
    q['before'] = before
    assert stopped(before) and before['source'][0] == 1 and before['x02'] == 0 and not any(before['faults'])
    original = {a: rd(a)[0] for a in (157, 163, 164, 165, 166, 236, 323, 324, 325, 326, 398, 1388, 1319, 1341)}
    q['original'] = original
    assert original[323] > 0, 'Disinfection duration must be enabled'
    wr(236, 5)
    # Register 1 is the legacy cool/heat/vent alias, not the special-mode selector.
    wait('select_auto_mode', lambda s: s['mode'] == 5 and stopped(s), 10)
    start = time.monotonic()
    q['contact_write_t'] = start
    wr(157, 1-original[157])
    contact = wait('X02_closed', lambda s: s['x02'] == 1, 10)
    q['contact_closed'] = contact
    first = wait('valves_open', lambda s: s['phase'][0] == 1 and s['mode'] == 5, 10)
    q['valves_open'] = first
    save()
    print('REMOTE START: valves open, waiting original 150 seconds', flush=True)
    fan, disinfect = None, None
    last = None
    end = time.monotonic()+190
    while time.monotonic() < end:
        s = sample('remote_start')
        assert not any(s['faults']) and s['x02'] == 1, ('fault_or_contact_changed', s)
        assert s['source'][0] == 1 and s['state'][14] == 1 and s['command'] == 1
        assert not any(v for pair in s['outdoor_status'] for v in pair), ('unexpected_outdoor_start', s)
        key = (s['phase'][0], tuple(s['do']))
        if key != last:
            print('TRANSITION', round(s['seconds'], 3), 'phase', s['phase'], 'DO', s['do'], flush=True)
            q['events'].append(dict(transition=s)); save(); last=key
        if s['do'][3] and fan is None:
            fan = s; q['fan_on'] = fan; save()
        if s['do'][10] and disinfect is None:
            disinfect = s; q['disinfect_on'] = disinfect; save()
            break
        time.sleep(.1)
    assert fan is not None and disinfect is not None, 'start timeout'
    fan_delay = fan['t']-first['t']
    disinfect_delay = disinfect['t']-fan['t']
    q['measured'] = dict(contact_to_valves=first['t']-contact['t'], valves_to_fan=fan_delay,
                         fan_to_disinfect=disinfect_delay, contact_to_disinfect=disinfect['t']-contact['t'])
    assert 148.5 <= fan_delay <= 151.5, q['measured']
    assert 18.5 <= disinfect_delay <= 21.5, q['measured']
    q['passed'] = True
    print('TIMING PASS', json.dumps(q['measured']), flush=True)
except Exception:
    q['error'] = traceback.format_exc()
    print(q['error'], flush=True)
finally:
    try:
        if original:
            wr(157, original[157])
            q['normal_stopped'] = wait('remote_open_normal_stop', stopped, 35)
            for a in (236, 326):
                if rd(a)[0] != original[a]:
                    wr(a, original[a])
            time.sleep(.5)
            q['restored'] = {a: rd(a)[0] for a in original}
            q['configuration_changes'] = {str(a): [original[a], q['restored'][a]] for a in original if original[a] != q['restored'][a]}
            q['after'] = sample('after_restore')
            assert not q['configuration_changes'], q['configuration_changes']
            assert stopped(q['after']) and q['after']['x02'] == 0
            q['restore_passed'] = True
    except Exception:
        q['restore_error'] = traceback.format_exc()
        q['passed'] = False
    q['finished'] = datetime.now().astimezone().isoformat()
    save()
    c.close()
    print('BOARD FINISHED', q['passed'], 'restore', q.get('restore_passed'), flush=True)
if not q['passed']:
    raise SystemExit(1)
