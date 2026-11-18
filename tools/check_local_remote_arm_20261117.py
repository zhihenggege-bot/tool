"""Execute linked V10.64 ARM control functions in Unicorn; no board access."""
import json
from build_local_remote_v1064_20261117 import OUT, OLD
from test_defrost_lifecycle_arm import Firmware


def fixture(path, source=0, timer=0, contact=0, auto=0, saved=0):
    f = Firmware(str(path))
    f.uc.mem_map(0x22000000, 0x100000)
    f.call('ParameterInit')
    for a in range(500):
        f.p(a, f.var('Parameter_def', index=a, width=2))
    for a, v in {163: source, 164: auto, 165: timer, 166: saved,
                 1388: 0, 709: 0, 710: 0, 398: 0, 214: 3}.items():
        f.p(a, v)
    f.var('X_02', contact)
    f.var('X02_En', contact)
    f.var('Systick_1ms', 30000)
    f.call('SwitchStatusProcess')
    return f


def snap(f):
    return {str(a): f.p(a) for a in (398, 700, 709, 166, 1388)}


def main():
    rows = []

    def check(ok, label, f):
        assert ok, (label, snap(f))
        rows.append(dict(label=label, passed=True, snapshot=snap(f)))

    for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
        path = OUT / profile / f'PSC330_V10.64_{profile}.axf'
        prefix = profile + ': '
        # Run actual interlock code for 10 seconds, including old stale flags.
        for timer in (0, 1):
            f = fixture(path, timer=timer)
            f.var('RemoteInterlockStopFlag', 1)
            f.var('RemoteInterlockResumeFlag', 1)
            f.call('SwitchStatusProcess')
            f.var('uc100ms', 1)
            for _ in range(100):
                f.call('BoardErrAction')
            check(f.var('RemoteInterlockStopFlag') == f.var('RemoteInterlockResumeFlag') == 0,
                  prefix + f'local timer={timer}: open X02 cannot interlock/resume', f)
            f.p(710, 0)
            if timer:
                f.p(1388, 1)
            else:
                f.p(398, 1)
            f.call('SwitchStatusProcess')
            check(f.p(398) == 1 and f.p(700) == (5 if timer else 4),
                  prefix + f'local timer={timer}: existing start still works', f)
            if timer:
                f.p(1388, 0)
            else:
                f.p(398, 0)
            f.call('SwitchStatusProcess')
            check(f.p(398) == 0, prefix + f'local timer={timer}: normal stop', f)

        for timer in (0, 1):
            f = fixture(path, source=1, timer=timer, auto=1, saved=1)
            f.p(1388, 1)
            f.p(398, 1)
            f.call('SwitchStatusProcess')
            check(f.p(398) == 0, prefix + f'remote timer={timer}: low X02 overrides HMI/timer/saved run', f)
            f.var('X_02', 1)
            f.var('X02_En', 1)
            f.call('SwitchStatusProcess')
            check(f.p(398) == 1 and f.p(700) == 4,
                  prefix + f'remote timer={timer}: X02 starts in ordinary control', f)
            f.p(709, 2)
            f.p(398, 0)
            f.p(1388, 0)
            f.call('SwitchStatusProcess')
            check(f.p(398) == 1, prefix + f'remote timer={timer}: HMI/timer stop ignored', f)
            f.var('X_02', 0)
            f.var('X02_En', 0)
            f.call('SwitchStatusProcess')
            check(f.p(398) == 0, prefix + f'remote timer={timer}: open contact requests normal stop', f)

        f = fixture(path, source=1, timer=1, contact=1)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 1 and f.p(700) == 4, prefix + 'closed contact at boot starts after initialization', f)
        # Contact recovers before normal stop completes: retain, then cancel or run.
        f.p(709, 3)
        f.var('X02_En', 0)
        f.call('SwitchStatusProcess')
        f.var('X02_En', 1)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 0 and f.var('RemoteInterlockResumeFlag') == 1,
              prefix + 'remote restart waits for full stop', f)
        f.p(709, 0)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 1, prefix + 'pending contact restart survives stopping interval', f)
        # Actual 3 s raw interlock remains restricted to remote.
        f.var('X_02', 0)
        f.var('uc100ms', 1)
        for _ in range(29):
            f.call('BoardErrAction')
        check(f.var('RemoteInterlockStopFlag') == 0, prefix + 'raw remote interlock before 3 seconds', f)
        f.call('BoardErrAction')
        check(f.var('RemoteInterlockStopFlag') == 1, prefix + 'raw remote interlock at 3 seconds', f)
        # Handover never treats the outgoing HMI status as a fresh local press.
        f.p(163, 0)
        f.p(165, 0)
        f.p(710, 0)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 0 and f.var('RemoteInterlockStopFlag') == f.var('RemoteInterlockResumeFlag') == 0,
              prefix + 'remote to local clears inherited start/interlock', f)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 0, prefix + 'local stays stopped without new command', f)
        f.p(398, 1)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 1, prefix + 'new local press starts normally', f)
        f.p(709, 2)
        f.p(163, 1)
        f.var('X02_En', 1)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 0 and f.var('RemoteInterlockResumeFlag') == 1,
              prefix + 'local to remote retires running source before restart', f)
        f.p(709, 0)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 1, prefix + 'new remote source starts when normal stop completed', f)
        f.p(165, 1)
        f.p(1388, 1)
        f.p(163, 0)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 0, prefix + 'stale timer target cannot start on return to local', f)
        f.p(1388, 0)
        f.call('SwitchStatusProcess')
        f.p(1388, 1)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 1 and f.p(700) == 5, prefix + 'timer re-arms through original zero handshake', f)

        for selected, timer, expected in ((0, 0, 0), (0, 1, 3), (1, 0, 1), (1, 1, 1)):
            f = fixture(path, source=selected, timer=timer)
            f.call('System_Real')
            check(f.p(714) == expected, prefix + f'control display source={selected},timer={timer}', f)

        # Fault and startup gates still win over a new remote contact.
        f = fixture(path, source=1, contact=1)
        f.p(710, 1)
        f.call('SwitchStatusProcess')
        check(f.p(398) == 0 and f.var('RemoteInterlockResumeFlag') == 0,
              prefix + 'system fault cancels remote startup/resume', f)
        f = fixture(path)
        f.var('Systick_1ms', 19999)
        f.p(398, 1)
        f.call('SwitchStatusProcess')
        check(f.p(700) == 10, prefix + '20-second initialization gate retained', f)

        # Compare the old/new local state machine, with healthy X02 on old code.
        for timer in (0, 1):
            old = fixture(OLD / profile / f'PSC330_V10.63_{profile}.axf', timer=timer, contact=1)
            new = fixture(path, timer=timer, contact=0)
            for step, command, fault in ((0, 0, 0), (0, 1, 0), (1, 1, 0),
                                         (2, 1, 0), (2, 0, 0), (3, 0, 0),
                                         (0, 0, 0), (0, 1, 0), (2, 1, 1), (0, 0, 0)):
                for fw in (old, new):
                    fw.p(709, step)
                    fw.p(710, fault)
                    fw.p(1388 if timer else 398, command)
                    fw.call('SwitchStatusProcess')
                check(snap(old) == snap(new), prefix + f'local timer={timer} differential step={step},cmd={command},fault={fault}', new)

        from check_special_remote_arm_20261106 import scenario, natural_completion
        for mode in (3, 4, 5):
            for kind in ('manual', 'fault'):
                result = scenario(OUT, '10.64', profile, mode, kind)
                assert result['passed'], result
                rows.append(dict(label=prefix + f'local special mode={mode}, {kind}', passed=True))
            for after in (0, 1):
                result = natural_completion(OUT, '10.64', profile, mode, after)
                assert result['passed'], result
                rows.append(dict(label=prefix + f'local special mode={mode}, completion={after}', passed=True))
        print('ARM PASS', profile, flush=True)

    report = dict(passed=True, assertions=len(rows), hardware_access=False,
                  linked_firmware='330 V10.64', timing_is_simulated=True, checks=rows)
    (OUT / 'local_remote_ARM.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print('ARM ASSERTIONS', len(rows), flush=True)


if __name__ == '__main__':
    main()
