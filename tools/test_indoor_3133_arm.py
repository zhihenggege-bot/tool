"""Specification 3.1-3.3 regression against actual Keil ARM machine code.

No serial, flashing or physical IO. Build PSC330 first, then:
    py -3 tools/test_indoor_3133_arm.py
"""
from test_defrost_lifecycle_arm import indoor

passed = 0


def check(condition, label):
    global passed
    assert condition, label
    passed += 1
    print('PASS', label)


def board(mode=0):
    f = indoor()
    f.uc.mem_map(0x22000000, 0x100000)
    f.call('ParameterInit')
    for i in range(500):
        f.p(i, f.var('Parameter_def', index=i, width=2))
    for k, v in {38: 0, 214: 5, 236: mode, 1: mode, 700: 4, 709: 1, 329: 1,
                 330: 0, 331: 0, 381: 0, 386: 0, 153: 0}.items():
        f.p(k, v)
    for i in range(335, 339):
        f.p(i, 0)
    for i in range(250, 258):
        f.p(i, 1)
    f.var('Systick_1ms', 30000)
    return f


def at(f, seconds, *functions):
    f.var('Systick_1ms', 30000 + int(seconds * 1000))
    f.var('uc1s', 1)
    for fn in functions:
        f.call(fn)


def out(f, ch):
    # Board labels are Y00..Y07,Y10..Y17, not decimal array indexes.
    return f.var('output', index=(ch if ch < 10 else ch - 2), width=1)


def ao(f, ch):
    return f.var('DA', index=ch, width=2)


def main():
    # Switch fresh damper follows the valve sequence even when AO demand is zero.
    for basis in (0, 1, 2):
        f = board(2)
        for reg, value in {335: 1, 336: 1, 337: 1, 338: 1,
                           330: 1, 331: 1, 328: 30, 132: 30, 135: 30,
                           377: basis, 380: 0, 378: 10, 902: 100,
                           500: 100, 379: 0, 381: 0, 386: 1}.items():
            f.p(reg, value)
        f.var('X_15', 1)
        f.var('X_14', 1)

        def cycle(second):
            at(f, second, 'SysBoardAction', 'SysDataPross',
               'IndoorFanValveOutputs', 'IndoorEnforceConfiguredOutputDisable',
               'IoOutAction', 'IndoorEnforceConfiguredOutputDisable')

        cycle(0)
        check(out(f, 14) == 1 and f.p(897) == 1000 and ao(f, 3) == 0,
              f'vent DO basis{basis}: opens immediately despite zero analog demand; display stays1000')
        check(all(out(f, ch) for ch in (4, 7, 11)) and
              not any(out(f, ch) for ch in (3, 6, 10)),
              f'vent DO basis{basis}: all installed dampers precede fans')
        for second, expected in ((149.999, (0, 0, 0)), (150, (0, 0, 1)),
                                 (180, (1, 0, 1)), (210, (1, 1, 1)),
                                 (219.999, (1, 1, 1)), (220, (1, 1, 1))):
            cycle(second)
            check(tuple(out(f, ch) for ch in (3, 6, 10)) == expected and out(f, 14),
                  f'vent DO basis{basis}: correct startup fans and fresh damper at{second}s')
        check(f.p(709) == 2 and f.p(888) == f.p(889) == 10,
              f'vent DO basis{basis}: startup completes only after both pressure qualifications')
        f.p(700, 0)
        cycle(230)  # First scan observes run->stop; next scan enters stop sequence.
        for second, expected in ((230, (0, 1, 1)), (259.999, (0, 1, 1)),
                                 (260, (0, 0, 1)), (290, (0, 0, 0)),
                                 (319.999, (0, 0, 0))):
            cycle(second)
            check(tuple(out(f, ch) for ch in (3, 6, 10)) == expected and out(f, 14),
                  f'vent DO basis{basis}: fresh damper holds during staggered stop at{second}s')
        cycle(320)
        check(f.p(709) == 0 and not any(out(f, ch) for ch in (3, 4, 6, 7, 10, 11, 14))
              and f.p(897) == 0 and ao(f, 3) == 0,
              f'vent DO basis{basis}: all dampers close only after last fan stops30s')

    for mode in (0, 1, 2):
        f = board(mode)
        for reg, value in {335: 1, 377: 2, 380: 0}.items():
            f.p(reg, value)
        f.call('IndoorApplyFanValveState', 1, 0, 0, 0)
        f.call('IndoorEnforceConfiguredOutputDisable')
        check(out(f, 14) and f.p(897) == 1000 and ao(f, 3) == 0,
              f'normal mode{mode}: switch damper ignores manual AO zero')
        f.call('IndoorApplyFanValveState', 0, 0, 0, 0)
        check(not out(f, 14) and f.p(897) == 0,
              f'normal mode{mode}: close command overrides switch damper')

    f = board(2)
    for reg, value in {335: 1, 377: 2, 380: 0}.items():
        f.p(reg, value)
    f.call('IndoorApplyFanValveState', 1, 0, 0, 0)
    f.p(710, 1)
    f.call('SysBoardAction')
    f.call('IndoorEnforceConfiguredOutputDisable')
    check(not out(f, 14) and f.p(897) == 0 and f.p(709) == 0,
          'fault stop still overrides switch fresh damper and clears final demand display')

    for mode in (0, 2):
        f = board(2)
        for reg, value in {335: mode, 377: 2, 380: 0}.items():
            f.p(reg, value)
        f.call('IndoorApplyFanValveState', 1, 0, 0, 0)
        f.call('IndoorEnforceConfiguredOutputDisable')
        check(not out(f, 14) and ao(f, 3) == 0 and f.p(897) == 0,
              f'fresh mode{mode}: absent/manual AO zero must not be forced open')
        if mode == 2:
            f.p(380, 50)
            f.call('IndoorApplyFanValveState', 1, 0, 0, 0)
            f.call('IndoorEnforceConfiguredOutputDisable')
            check(not out(f, 14) and ao(f, 3) == 500 and f.p(897) == 500,
                  'manual AO5V remains proportional and never energizes Y14')

    # Full UserAction entry: actual HMI command processing plus final IO guards.
    f = board(2)
    for reg, value in {709: 0, 163: 0, 164: 1, 166: 1}.items():
        f.p(reg, value)
    for second in range(5, 10):
        f.var('Systick_1ms', second * 1000)
        f.var('uc1s', 1)
        f.call('UserAction')
    f.var('Systick_1ms', 20000)
    f.call('UserAction')
    for reg, value in {335: 1, 336: 1, 337: 1, 338: 1, 330: 1, 331: 1,
                       328: 30, 132: 30, 135: 30, 377: 2, 380: 0,
                       386: 1, 700: 4, 398: 1, 709: 1}.items():
        f.p(reg, value)
    f.var('X_15', 1)
    f.var('X_14', 1)

    def user_cycle(second):
        at(f, second, 'UserAction', 'IndoorEnforceConfiguredOutputDisable',
           'IoOutAction', 'IndoorEnforceConfiguredOutputDisable')

    for second, expected in ((0, (0, 0, 0)), (149.999, (0, 0, 0)),
                             (150, (0, 0, 1)), (180, (1, 0, 1)),
                             (210, (1, 1, 1)), (219.999, (1, 1, 1)),
                             (220, (1, 1, 1))):
        user_cycle(second)
        check(tuple(out(f, ch) for ch in (3, 6, 10)) == expected and
              out(f, 14) and f.p(897) == 1000,
              f'UserAction ventilation startup{second}s: switch damper survives command and final guards')
    check(f.p(709) == 2 and f.p(888) == f.p(889) == 10,
          'UserAction ventilation startup requires both pressure10s qualifications')
    f.p(398, 0)
    user_cycle(230)
    for second, expected in ((230, (0, 1, 1)), (260, (0, 0, 1)),
                             (290, (0, 0, 0)), (319.999, (0, 0, 0))):
        user_cycle(second)
        check(tuple(out(f, ch) for ch in (3, 6, 10)) == expected and out(f, 14),
              f'UserAction ventilation stop{second}s: command0 retains damper until fans and30s finish')
    user_cycle(320)
    check(f.p(709) == 0 and not out(f, 14) and f.p(897) == 0,
          'UserAction ventilation completes shutdown and closes switch damper')
    check(not any(out(f, ch) for ch in (0, 1, 2, 12, 13, 15, 16, 17)) and
          all(f.field(True, u, 'CompControl', c) == 0 for u in range(1, 5) for c in range(2)),
          'UserAction ventilation leaves heat/humidifier/disinfection/compressor requests off')

    # Execute the real CRC-checked 1460 response parser, not only RAM mirrors.
    for unit in range(1, 5):
        f = board()
        buf = f.symbols['ucUart5Buff'][0]
        f.var('PSC316LastReadAddr', 1460, index=unit - 1, width=2)
        for cycle, mask in enumerate((0x8c00, 0x7000)):
            # The parser now requires a live request, including its deadline.
            f.var('Systick_1ms', 30000 + cycle * 10)
            f.uc.mem_write(buf, bytes([unit, 3, 5, 180, 0, 42, 0, 0]))
            f.call('PSC316Gateway_NoteTransmit')
            frame = bytearray([unit, 3, 84] + [0] * 84 + [0, 0])
            frame[23:25] = mask.to_bytes(2, 'big')
            f.uc.mem_write(buf, bytes(frame))
            frame[-2:] = f.call('CreatCRC', buf, len(frame) - 2).to_bytes(2, 'big')
            f.uc.mem_write(buf, bytes(frame))
            f.var('ucUart5ReceLen', len(frame))
            f.call('ModuleReciData')
            f.var('Systick_1ms', 30010 + cycle * 10)
            f.call('ModuleReciData')
            check(f.field(False, unit, 'InStatus1') == mask and
                  f.call('IndoorOutdoorStopped') == cycle,
                  f'outdoor{unit}: CRC-checked1470 fan bits gate shutdown through actual parser ({mask:#06x})')

    for unit in range(1, 5):
        f = board()
        for mask in (0x0400, 0x0800, 0x8000):
            f.field(False, unit, 'InStatus1', value=mask)
            check(f.call('IndoorOutdoorStopped') == 0,
                  f'outdoor{unit}: published fan drive {mask:#06x} blocks stop completion')
        f.field(False, unit, 'InStatus1', value=0x73ff)
        check(f.call('IndoorOutdoorStopped') == 1,
              f'outdoor{unit}: four-way/crankcase/inputs are not mistaken for fan drives')

    f = board(0)
    f.p(709, 3)
    f.call('IndoorApplyFanValveState', 1, 1, 0, 0)
    f.field(False, 1, 'InStatus1', value=0x0400)
    at(f, 0, 'SysBoardAction')
    at(f, 90, 'SysBoardAction')
    check(f.p(709) == 3 and out(f, 3),
          'compressors off but outdoor fan on: indoor supply remains running')
    f.field(False, 1, 'InStatus1', value=0)
    at(f, 100, 'SysBoardAction')
    at(f, 129.999, 'SysBoardAction')
    check(out(f, 3) and f.p(709) == 3,
          'cooling purge starts when outdoor fan outputs are confirmed off')
    f.field(False, 1, 'InStatus1', value=0x0800)
    at(f, 130, 'SysBoardAction')
    f.field(False, 1, 'InStatus1', value=0)
    at(f, 140, 'SysBoardAction')
    at(f, 169.999, 'SysBoardAction')
    check(out(f, 3) and f.p(709) == 3,
          'outdoor fan reactivation invalidates the previous stopped edge and purge')
    at(f, 170, 'SysBoardAction')
    check(not out(f, 3) and f.p(709) == 4,
          'indoor fan stops only after a fresh full30s purge')
    at(f, 200, 'SysBoardAction')
    check(f.p(709) == 0, 'shutdown completes after outdoor fan stop, purge and valve delay')

    f = board()
    at(f, 0, 'SysBoardAction')
    for _ in range(10):
        f.call('SysBoardAction')
    check(not out(f, 3), 'no damper: repeated scans do not bypass 10 seconds')
    at(f, 9.999, 'SysBoardAction')
    check(not out(f, 3), 'no damper: fan remains off before 10s')
    at(f, 10, 'SysBoardAction')
    check(out(f, 3) == 1, 'no damper: fan starts at 10s')

    f = board()
    f.p(386, 2)
    f.var('X_15', 1)
    at(f, 0, 'SysBoardAction', 'SysDataPross')
    at(f, 10, 'SysBoardAction', 'SysDataPross')
    for second in range(11, 20):
        at(f, second, 'SysBoardAction', 'SysDataPross')
        check(f.p(709) == 1 and f.p(888) == second - 10,
              f'double call at {second}s: pressure advances once, startup waits')
    at(f, 20, 'SysBoardAction', 'SysDataPross')
    check(f.p(709) == 2, 'full 10 seconds closed permits cooling startup')

    f = board()
    f.p(336, 2)
    f.p(130, 50)
    f.p(386, 2)
    f.var('X_15', 1)
    f.call('IndoorApplyFanValveState', 1, 0, 0, 0)
    at(f, 0, 'IndoorPressureReady')
    at(f, 100, 'IndoorPressureReady')
    check(ao(f, 7) == 500 and f.p(888) == 0, 'damper AO7 cannot qualify a stopped DO fan')

    f = board()
    for reg in (335, 336, 337, 338):
        f.p(reg, 1)
    f.p(206, 1)  # Old custom damper delay must not shorten fixed 150s.
    f.p(330, 1)
    f.p(331, 1)
    f.p(386, 1)
    f.var('X_15', 1)
    f.var('X_14', 1)
    at(f, 0, 'SysBoardAction', 'SysDataPross')
    at(f, 149.999, 'SysBoardAction', 'SysDataPross')
    check(not out(f, 3) and not out(f, 10), 'configured dampers always wait full 150s')
    at(f, 150, 'SysBoardAction', 'SysDataPross')
    check(out(f, 10) and not out(f, 3), 'default start: exhaust first at150s')
    at(f, 180, 'SysBoardAction', 'SysDataPross')
    check(out(f, 3) and not out(f, 6), 'default start: supply 30s after exhaust')
    at(f, 210, 'SysBoardAction', 'SysDataPross')
    check(out(f, 6) and f.p(709) == 1, 'return fan starts after supply; return qualification begins')
    at(f, 219.999, 'SysBoardAction', 'SysDataPross')
    check(f.p(709) == 1, 'return pressure requires its full 10 seconds')
    at(f, 220, 'SysBoardAction', 'SysDataPross')
    check(f.p(709) == 2, 'normal startup completes after all required qualifications')

    for delay in (-30, 0, 30, 90):
        f = board(2)
        f.p(331, 1)
        f.p(328, delay)
        at(f, 0, 'SysBoardAction')
        at(f, 10, 'SysBoardAction')
        check((out(f, 3), out(f, 10)) == ((1, 0) if delay < 0 else ((1, 1) if delay == 0 else (0, 1))),
              f'fan order honors signed/zero interval {delay}s')
        at(f, 10 + abs(delay), 'SysBoardAction')
        check(out(f, 3) and out(f, 10), f'both fans running after actual interval {delay}s')

    # Shutdown captures the currently running fans and shares one sequence.
    for delay in (-30, 0, 30, 90):
        f = board(2)
        f.p(709, 4)
        f.p(330, 1)
        f.p(331, 1)
        f.p(328, delay)
        f.p(335, 1)
        f.call('IndoorApplyFanValveState', 1, 1, 1, 1)
        at(f, 0, 'SysBoardAction')
        check((out(f, 3), out(f, 10)) == ((1, 0) if delay < 0 else ((0, 0) if delay == 0 else (0, 1))),
              f'stop: first-started fan stops last for interval {delay}s')
        deadline = 90 if delay in (-30, 30) else (60 if delay == 0 else 150)
        for second in range(1, deadline):
            at(f, second, 'SysBoardAction')
        check(f.p(709) == 4, f'stop interval {delay}: valves retain full post-run delay')
        at(f, deadline, 'SysBoardAction')
        check(f.p(709) == 0 and not out(f, 14), f'stop interval {delay}: finishes and closes damper')

    f = board(1)
    f.p(709, 3)
    f.p(248, 0)
    f.p(128, 2)
    f.p(333, 1)
    f.var('DA', 800, index=0, width=2)
    f.var('DA', 800, index=1, width=2)
    f.call('IndoorApplyFanValveState', 1, 1, 0, 0)
    at(f, 0, 'SysBoardAction')
    at(f, 29.999, 'SysBoardAction')
    check(ao(f, 0) == 800 and ao(f, 1) == 800, 'heating stop without humidifier retains heat for30s')
    at(f, 30, 'SysBoardAction')
    check(ao(f, 0) == ao(f, 1) == 0 and out(f, 3), 'heating30s: heat/preheat off, supply remains on')
    at(f, 89.999, 'SysBoardAction')
    check(out(f, 3), 'heating post-heat purge keeps fan on for60s')
    at(f, 90, 'SysBoardAction')
    check(not out(f, 3), 'heating fan stops after complete60s purge')
    at(f, 120, 'SysBoardAction')
    check(f.p(709) == 0, 'heating shutdown completes after valve30s')

    for mode in range(6):
        for restart in (0, 1):
            f = board(mode)
            f.p(709, 0)
            f.p(163, 0)
            f.p(164, restart)
            f.p(166, 1)
            f.p(161, 271)
            for second in range(5, 10):
                f.var('Systick_1ms', second * 1000)
                f.var('uc1s', 1)
                f.call('UserAction')
            check(f.p(166) == 1, f'boot mode{mode}, restart{restart}: saved run bit survives delay')
            f.var('Systick_1ms', 20000)
            f.call('UserAction')
            check(f.p(236) == mode and f.p(161) == 271 and f.p(700) == (4 if restart else 0),
                  f'boot mode{mode}, restart{restart}: exact saved mode/temp and requested run policy')

    for source, signal in ((1, 'X02_En'), (2, None)):
        f = board()
        f.p(163, source)
        f.p(164, 0)
        f.p(166, 1)
        if signal:
            f.var(signal, 1)
        else:
            f.p(735, 1)
        f.call('SwitchStatusProcess')
        f.call('SwitchStatusProcess')
        check(f.p(700) == 0, f'source{source}: held ON cannot bypass disabled power restart')
        if signal:
            f.var(signal, 0)
        else:
            f.p(735, 0)
        f.call('SwitchStatusProcess')
        if signal:
            f.var(signal, 1)
        else:
            f.p(735, 1)
        f.call('SwitchStatusProcess')
        check(f.p(700) == 4, f'source{source}: a fresh OFF-to-ON command starts normally')

    f = board(2)
    f.p(330, 1)
    f.p(386, 3)
    f.var('X_14', 1)
    f.call('IndoorApplyFanValveState', 1, 1, 1, 0)
    at(f, 0, 'IndoorPressureReady')
    at(f, 9, 'IndoorPressureReady')
    check(f.p(889) == 9, 'return-only switch qualifies without a supply switch')
    f.var('X_14', 0)
    at(f, 9.5, 'IndoorPressureReady')
    f.var('X_14', 1)
    at(f, 10, 'IndoorPressureReady')
    at(f, 19.999, 'IndoorPressureReady')
    check(f.p(889) == 9, 'pressure bounce discards the previous closed interval')
    at(f, 20, 'IndoorPressureReady')
    check(f.call('IndoorPressureReady') == 1, 'pressure bounce requires a new full10s interval')

    # Real UserAction transition preserves old mode/EEV policy until all loads stop.
    f = board(0)
    f.p(709, 0)
    f.p(163, 0)
    f.p(164, 1)
    f.p(166, 1)
    for second in range(5, 10):
        f.var('Systick_1ms', second * 1000)
        f.var('uc1s', 1)
        f.call('UserAction')
    f.var('Systick_1ms', 20000)
    f.call('UserAction')
    f.p(709, 2)
    f.call('IndoorApplyFanValveState', 1, 1, 0, 0)
    f.p(125, 1)
    f.p(248, 1)
    f.p(334, 1)
    f.p(323, 1)
    for c in range(2):
        f.field(True, 1, 'CompControl', c, 1)
        f.field(False, 1, 'CompStatus', c, 2)
        f.var('CompMinRunCount', 1000, 2+c, 4)
    f.call('CompActionIntervalUpdate')
    f.p(236, 3)
    at(f, 0, 'UserAction')
    check(f.p(236) == 0 and f.p(709) == 3 and
          all(f.field(True, 1, 'CompControl', c) == 1 for c in range(2)),
          'enter disinfection: retains cooling mode and both compressor requests during humidifier wait')
    at(f, 29.999, 'UserAction')
    check(all(f.field(True, 1, 'CompControl', c) == 1 for c in range(2)),
          'special transition does not clear requests before full30s')
    at(f, 30, 'UserAction')
    remaining = [f.field(True, 1, 'CompControl', c) for c in range(2)]
    check(sum(remaining) == 1, 'special transition unloads exactly one compressor at30s')
    for c, value in enumerate(remaining):
        if value == 0:
            f.field(False, 1, 'CompStatus', c, 0)
    # Consume the injected stopped feedback without reinitializing the injected
    # long-running history (real UserMain tracks that history continuously).
    at(f, 30, 'CompActionIntervalUpdate')
    at(f, 59.999, 'UserAction')
    check(sum(f.field(True, 1, 'CompControl', c) for c in range(2)) == 1,
          'special transition honors full30s compressor switch interval')
    at(f, 60, 'UserAction')
    check(all(f.field(True, 1, 'CompControl', c) == 0 for c in range(2)),
          'second compressor unloads after interval')
    for c in range(2):
        f.field(False, 1, 'CompStatus', c, 0)
    at(f, 60, 'UserAction')
    at(f, 90, 'UserAction')
    check(not out(f, 3) and f.p(236) == 0, 'special transition waits outdoor stop and cooling purge before fan stop')
    at(f, 120, 'UserAction')
    at(f, 120, 'UserAction')
    check(f.p(236) == 3 and f.p(709) == 2 and not out(f, 3),
          'only after normal shutdown does disinfection begin its own damper phase')

    f = board(4)
    f.p(709, 0)
    f.p(331, 1)
    f.p(328, -30)
    f.p(335, 1)
    at(f, 0, 'IndoorDisinfectExhaustAction')
    at(f, 150, 'IndoorDisinfectExhaustAction')
    at(f, 180, 'IndoorDisinfectExhaustAction')
    f.p(700, 0)
    at(f, 190, 'IndoorDisinfectExhaustAction')
    check(out(f, 3) and not out(f, 10) and out(f, 14),
          'manual special stop uses reversed fan order, retaining dampers')
    at(f, 220, 'IndoorDisinfectExhaustAction')
    check(not out(f, 3) and out(f, 14), 'manual special stop finishes fan interval before damper delay')
    at(f, 250, 'IndoorDisinfectExhaustAction')
    check(f.p(709) == 0 and not out(f, 14), 'manual special stop completes normal damper30s')

    f = board(2)
    f.p(709, 2)
    f.call('IndoorModeTransitionAction')
    f.p(236, 3)
    f.call('IndoorModeTransitionAction')
    check(f.var('IndoorPendingWorkMode') == 3 and f.p(236) == 2,
          'mode change queues the new mode while retaining the active mode')
    f.p(700, 0)
    f.call('IndoorModeTransitionAction')
    f.p(709, 0)
    f.call('IndoorModeTransitionAction')
    check(f.var('IndoorPendingWorkMode') == 0xFFFFFFFF and f.p(236) == 2,
          'user stop cancels a queued special-mode restart')

    f = board(3)
    f.p(709, 0)
    f.p(323, 1)
    f.p(337, 1)
    f.call('IndoorModeTransitionAction')
    at(f, 0, 'IndoorDisinfectExhaustAction')
    at(f, 150, 'IndoorDisinfectExhaustAction')
    at(f, 170, 'IndoorDisinfectExhaustAction')
    f.p(236, 1)
    f.p(700, 4)
    at(f, 180, 'IndoorModeTransitionAction', 'IndoorDisinfectExhaustAction')
    check(not out(f, 12) and not out(f, 3) and out(f, 7) and f.p(236) == 3,
          'special-to-heat stops disinfection/fan and retains valves for normal shutdown')
    f.p(700, 4)
    at(f, 210, 'IndoorModeTransitionAction', 'IndoorDisinfectExhaustAction')
    f.p(700, 4)
    f.call('IndoorModeTransitionAction')
    check(f.p(236) == 1 and f.p(709) == 0 and not out(f, 7),
          'special-to-heat applies the requested mode only after complete shutdown')

    for mode in (0, 3, 5):
        f = board(mode)
        f.p(709, 2)
        for ch in range(16):
            f.var('output', 1, index=ch, width=1)
        for ch in range(8):
            f.var('DA', 900, index=ch, width=2)
        for unit in range(1, 5):
            for comp in range(2):
                f.field(True, unit, 'CompControl', comp, 1)
        f.var('X03_En', 1)  # Actual qualified fan-overload input, not just its helper.
        f.call('ErrorCheck')
        f.call('IndoorEnforceConfiguredOutputDisable')
        check(all(f.var('output', index=ch, width=1) == 0 for ch in range(16)) and
              all(ao(f, ch) == 0 for ch in range(8)) and f.p(709) == 0,
              f'mode{mode}: actual emergency fault immediately clears every load output')
        check(all(f.field(True, unit, 'CompControl', comp) == 0
                  for unit in range(1, 5) for comp in range(2)),
              f'mode{mode}: emergency clears all outdoor compressor requests')

    f = board(2)
    f.p(709, 4)
    f.p(331, 1)
    f.p(338, 1)
    f.p(328, 0)
    f.p(135, 90)
    f.call('IndoorApplyFanValveState', 1, 1, 0, 1)
    at(f, 0, 'SysBoardAction')
    at(f, 30, 'SysBoardAction')
    check(out(f, 11) and f.p(709) == 4, 'exhaust damper configured90s survives common30s delay')
    at(f, 90, 'SysBoardAction')
    check(not out(f, 11) and f.p(709) == 0, 'exhaust damper closes at its fan-relative90s deadline')

    for mode, heat, preheat in ((2, 2, 1), (3, 2, 1), (1, 2, 1), (0, 2, 1)):
        f = board(mode)
        f.p(128, heat)
        f.p(333, preheat)
        f.p(346, 200)
        f.p(512, -10)
        f.p(709, 0)
        f.call('IndoorEmergencyStopLoads')
        f.call('IndoorEnforceConfiguredOutputDisable')
        check(ao(f, 0) == ao(f, 1) == 0, f'mode{mode}: stopped outputs stay zero in freezing fresh air')
    f = board(2)
    f.p(709, 2)
    f.p(128, 2)
    f.p(333, 1)
    f.p(346, 200)
    f.p(512, -10)
    f.call('IndoorEnforceConfiguredOutputDisable')
    check(ao(f, 0) == ao(f, 1) == 0, 'ventilation never reopens heating/preheat water valves')

    f = board(1)
    f.p(709, 2)
    f.p(128, 1)
    f.p(127, 0)
    f.p(129, 0)
    f.p(332, 1)
    f.field(False, 1, 'CanDefrost', value=8)
    f.call('HeatControl_UP')
    check(ao(f, 9) == 1000 and ao(f, 0) == 0,
          'independent heat-pump auxiliary uses DA9 without enabling cooling reheat')

    # Low-ambient minimum follows the selected output mode and fault gates.
    for heat_mode in (0, 3, 4):
        f = board(1)
        for addr, value in {709: 2, 128: heat_mode, 127: 1,
                            332: 1, 346: 200, 512: -10}.items():
            f.p(addr, value)
        f.call('HeatControl_UP')
        f.call('IndoorEnforceConfiguredOutputDisable')
        check(ao(f, 0) == 0,
              f'heat mode{heat_mode}: winter minimum cannot energize an inactive heat AO')
    f = board(1)
    for addr, value in {709: 2, 128: 1, 127: 1, 129: 0,
                        332: 1, 346: 200, 512: -10}.items():
        f.p(addr, value)
    f.call('HeatControl_UP')
    f.call('IndoorEnforceConfiguredOutputDisable')
    check((f.p(940) & 0x08) and ao(f, 0) == 0,
          'invalid heat-pump aux combination stays off after winter minimum guard')
    f = board(1)
    for addr, value in {709: 2, 128: 2, 127: 0,
                        346: 200, 512: -10, 738: 300, 739: 250}.items():
        f.p(addr, value)
    f.call('HeatControl_UP')
    f.call('IndoorEnforceConfiguredOutputDisable')
    check(ao(f, 0) == 200,
          'valid analog heating retains its configured low-ambient minimum')
    f = board(1)
    for addr, value in {709: 2, 333: 1, 374: 1,
                        346: 200, 512: -10, 599: 1}.items():
        f.p(addr, value)
    f.call('PreHeatControl')
    f.call('IndoorEnforceConfiguredOutputDisable')
    check(ao(f, 1) == 0,
          'preheat sensor fault cannot reopen analog preheat via winter minimum')
    f = board(0)
    for addr, value in {709: 2, 127: 1, 332: 1,
                        346: 200, 512: -10, 738: 300, 739: 250}.items():
        f.p(addr, value)
    f.call('HeatControl_UP')
    f.call('IndoorEnforceConfiguredOutputDisable')
    check(ao(f, 0) == 200 and ao(f, 9) == 0,
          'valid cooling reheat retains its configured low-ambient minimum')
    f = board(1)
    for addr, value in {709: 2, 333: 1, 374: 0,
                        346: 200, 512: -10, 738: 300, 739: 250}.items():
        f.p(addr, value)
    f.call('PreHeatControl')
    f.call('IndoorEnforceConfiguredOutputDisable')
    check(ao(f, 1) == 200,
          'valid preheat retains its configured low-ambient minimum')

    f = board()
    f.p(709, 2)
    f.p(315, 1)
    f.p(327, 0)
    f.p(512, 400)
    f.call('SysNergryAction_PID')
    check(f.p(118) == 0 and f.p(707) == 4, 'ambient capacity control blocked outside full-fresh-air systems')
    f.p(327, 1)
    f.call('SysNergryAction_PID')
    check(f.p(118) > 0, 'explicit fixed-speed full-fresh-air system permits ambient capacity control')
    for controller in ('SysNergryAction', 'SysNergryAction_PID'):
        f.p(38, 1)
        f.p(118, 4)
        f.call(controller)
        check(f.p(118) == 0 and f.p(707) == 4,
              f'{controller}: inverter configuration cannot bypass the ambient-control restriction')

    for emergency, extra in ((0, 20), (1, 10)):
        f = board()
        f.p(1406, emergency)
        f.p(1153, 100)
        f.var('uc1s', 0)
        target = f.call('EEVCloseStepTarget', 0, 100, 500)
        check(target == 100 + extra and f.p(1153) == 100 + extra,
              f'EEV close mode{emergency}: exact additional{extra} steps')
        f.var('uc1s', 1)
        first = f.call('EEVCloseStepTarget', 0, 100 + extra, 500)
        second = f.call('EEVCloseStepTarget', 0, 100 + extra, 500)
        check(first == second == 80 + extra, f'EEV mode{emergency}:20step tick consumed once')

    for pid in (0, 1):
        f = board(1)
        f.p(709, 2)
        f.p(365, pid)
        f.p(10, 500)
        f.p(12, 500)
        f.p(21, 350)
        # Home every channel once before injecting the actual positions.
        f.call('EEV_ActionAll')
        for ch in range(8):
            f.p(1153 + ch, 100)
        f.field(False, 1, 'CanDefrost', value=7)
        f.field(False, 2, 'CompStatus', value=3)
        f.field(True, 2, 'CompControl', value=1)
        # Complete homing, then put one circuit in recovery and another in heat.
        for ch in range(8):
            f.p(1153 + ch, 0)
        f.call('EEV_ActionAll')
        f.p(1153, 350)
        f.p(1155, 100)
        f.call('EEVSpecCloseReset', 2, 100)
        f.var('uc1s', 0)
        f.call('EEV_ActionAll')
        check(f.p(1145) == 350 and f.p(1147) == 120,
              f'EEV option{pid}: another heating channel cannot overwrite recovery350')
        f.var('uc1s', 1)
        f.call('EEV_ActionAll')
        check(f.p(1145) == 350 and f.p(1147) == 100,
              f'EEV option{pid}: normal heating closes its own valve20steps per tick')
        f.call('EEV_ActionAll')
        check(f.p(1147) == 100, f'EEV option{pid}: repeated scan does not duplicate closing tick')
        f.p(1406, 1)
        f.p(805, 1)
        f.p(804, 400)
        f.var('uc1s', 0)
        f.call('EEV_ActionAll')
        check(f.p(1145) == 360, f'EEV option{pid}: emergency overrides recovery/manual with current+10')

    for mode in (3, 4, 5):
        f = board(mode)
        f.p(709, 0)
        f.p(323, 1)
        f.p(324, 1)
        f.p(325, 0)
        f.p(335, 1)
        f.p(336, 1)
        f.p(337, 1)
        f.p(338, 1)
        f.p(331, 1)
        at(f, 0, 'IndoorDisinfectExhaustAction')
        at(f, 149.999, 'IndoorDisinfectExhaustAction')
        check(not out(f, 3) and not out(f, 12), f'special mode{mode}: full150s damper travel')
        if mode != 4:
            at(f, 150, 'IndoorDisinfectExhaustAction')
            at(f, 169.999, 'IndoorDisinfectExhaustAction')
            check(out(f, 3) and not out(f, 12), f'mode{mode}: disinfect waits full20s after fan')
            at(f, 170, 'IndoorDisinfectExhaustAction')
            check(out(f, 12), f'mode{mode}: disinfect energizes at170s')
            at(f, 229.999, 'IndoorDisinfectExhaustAction')
            check(out(f, 12), f'mode{mode}: full60s disinfection')
            at(f, 230, 'IndoorDisinfectExhaustAction')
            check(not out(f, 12) and not out(f, 3), f'mode{mode}: disinfection ends and supply stops')
            if mode == 5:
                at(f, 259.999, 'IndoorDisinfectExhaustAction')
                check(out(f, 7) and not out(f, 14), 'combined: return valve stays open for30s changeover')
                at(f, 260, 'IndoorDisinfectExhaustAction')
                check(not out(f, 7) and out(f, 14), 'combined: switches to fresh/exhaust valve path after30s')
                at(f, 409.999, 'IndoorDisinfectExhaustAction')
                check(not out(f, 3) and not out(f, 10), 'combined: new path receives full150s travel')
                at(f, 410, 'IndoorDisinfectExhaustAction')
                at(f, 440, 'IndoorDisinfectExhaustAction')
                at(f, 499.999, 'IndoorDisinfectExhaustAction')
                check(out(f, 3) and out(f, 10), 'combined: exhaust receives its full60s duration')
                at(f, 500, 'IndoorDisinfectExhaustAction')
                at(f, 530, 'IndoorDisinfectExhaustAction')
                at(f, 560, 'IndoorDisinfectExhaustAction')
                check(f.p(709) == 0 and f.p(700) == 0 and not out(f, 14),
                      'combined: full cycle ends with shared fan/damper shutdown')
        else:
            at(f, 150, 'IndoorDisinfectExhaustAction')
            at(f, 180, 'IndoorDisinfectExhaustAction')
            check(out(f, 3) and out(f, 10), 'exhaust: both fans run after configured interval')
            at(f, 239.999, 'IndoorDisinfectExhaustAction')
            check(out(f, 3), 'exhaust: duration measured from both fans running')
            at(f, 240, 'IndoorDisinfectExhaustAction')
            check(not out(f, 3) and out(f, 10), 'exhaust completion uses normal staggered fan stop')
            at(f, 270, 'IndoorDisinfectExhaustAction')
            at(f, 300, 'IndoorDisinfectExhaustAction')
            check(f.p(709) == 0 and not out(f, 14), 'exhaust finishes after fan interval and damper30s')

    f = board(3)
    f.p(709, 0)
    f.p(323, 1)
    f.p(325, 1)
    f.p(326, 1)
    f.p(337, 1)
    for second in (0, 150, 170, 230, 260):
        at(f, second, 'IndoorDisinfectExhaustAction')
    check(f.p(236) == 1 and f.p(709) == 0 and f.p(700) == 4 and not out(f, 7),
          'AfterMode1 restores the saved normal mode only after valves have closed')

    for mode in (3, 4, 5):
        for after in (0, 1):
            f = board(mode)
            f.p(709, 0)
            f.p(323, 0)
            f.p(324, 0)
            f.p(325, after)
            f.p(326, 1)
            f.call('IndoorDisinfectExhaustAction')
            check(f.p(709) == 0 and not out(f, 3) and not out(f, 12),
                  f'mode{mode}, AfterMode{after}: zero duration never energizes special loads')
            check(f.p(700) == (4 if after else 0) and f.p(236) == (1 if after else mode),
                  f'mode{mode}, AfterMode{after}: disabled function honors the configured completion policy')

    print(f'{passed} specification checks passed against built ARM firmware.')


if __name__ == '__main__':
    main()
