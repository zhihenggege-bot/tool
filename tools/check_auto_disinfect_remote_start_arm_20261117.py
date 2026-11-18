"""Execute the linked special-mode start at exact boundaries; no board IO."""
from pathlib import Path
import json
from test_defrost_lifecycle_arm import Firmware

R = Path(__file__).resolve().parents[1]
B = R / '.codex-tmp/local_remote_v1064_20261117'
rows = []


def setup(profile, source, timer):
    f = Firmware(str(B / profile / f'PSC330_V10.64_{profile}.axf'))
    f.uc.mem_map(0x22000000, 0x100000)
    f.call('ParameterInit')
    for a in range(500):
        f.p(a, f.var('Parameter_def', index=a, width=2))
    for a, v in {1: 2, 236: 5, 163: source, 164: 0, 165: timer, 166: 0, 398: 0,
                 1388: 0, 214: 3, 709: 0, 700: 0, 710: 0,
                 323: 1, 324: 1, 325: 0, 329: 2, 330: 0, 331: 1, 328: 0,
                 132: 0, 135: 0, 335: 0, 336: 0, 337: 0, 338: 0,
                 381: 0, 386: 0}.items():
        f.p(a, v)
    for a in range(250, 258):
        f.p(a, 1)
    f.var('Systick_1ms', 30000)
    f.var('X_02', 0); f.var('X02_En', 0)
    f.call('SwitchStatusProcess')
    if source:
        f.var('X_02', 1); f.var('X02_En', 1)
    elif timer:
        f.p(1388, 1)
    else:
        f.p(398, 1)
    f.call('SwitchStatusProcess')
    f.call('IndoorDisinfectExhaustAction')
    assert f.p(885) == 1
    return f


def advance(f, ms):
    f.var('Systick_1ms', 30000+ms)
    f.call('SwitchStatusProcess')
    f.call('IndoorDisinfectExhaustAction')
    return dict(ms=ms, step=f.p(885), command=f.p(398), sys=f.p(700),
                supply=f.var('output', index=3, width=1),
                disinfect=f.var('output', index=10, width=1),
                exhaust=f.var('output', index=8, width=1))


for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
    for source, timer in ((0, 0), (0, 1), (1, 0), (1, 1)):
        f = setup(profile, source, timer)
        # Remote and local must take the same specified 150s + 20s start.
        for ms, phase, fan, disinfect in ((0, 1, 0, 0), (149999, 1, 0, 0),
                                         (150000, 2, 1, 0), (169999, 2, 1, 0),
                                         (170000, 3, 1, 1)):
            s = advance(f, ms)
            assert (s['step'], s['supply'], s['disinfect']) == (phase, fan, disinfect), (profile, source, timer, s)
            rows.append(dict(profile=profile, source=source, timer=timer, passed=True, **s))
        # Check the next auto phase's stop/wait/re-open order too, offline.
        for ms, phase, fan, disinfect, exhaust in ((230000, 5, 0, 0, 0), (259999, 5, 0, 0, 0),
                                                   (260000, 1, 0, 0, 0), (409999, 1, 0, 0, 0),
                                                   (410000, 4, 1, 0, 1)):
            s = advance(f, ms)
            assert (s['step'], s['supply'], s['disinfect'], s['exhaust']) == (phase, fan, disinfect, exhaust), (profile, source, timer, s)
            rows.append(dict(profile=profile, source=source, timer=timer, passed=True, **s))

D = R / '测试证据/自动消排毒远程启动_20261117'
D.mkdir(exist_ok=True)
(D / 'ARM_start_boundaries.json').write_text(json.dumps(dict(passed=True, total=len(rows),
    scope='实际链接ARM；本地手动/定时与远程启动边界、消毒到排毒顺序；非硬件测量', rows=rows), ensure_ascii=False, indent=2), 'utf8')
print(len(rows), 'actual ARM boundary checks passed')
