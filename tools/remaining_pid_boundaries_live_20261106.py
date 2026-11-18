"""Remaining initial-demand and preheat boundaries, normal inputs only."""
from remaining_pid_live_20261106 import *


def initial(family):
    b = HeatBench('initial_boundaries_' + family)
    reader = None
    try:
        b.setup(0 if family == 'cool' else 1)
        b.config({315: 1, 327: 1, 128: 1, 127: 0, 332: 0, 333: 0,
                  125: 0, 126: 0, 248: 0, 334: 0, 160: 270, 161: 270,
                  412: 3, 120: 20, 416: 5, 417: 100, 418: 0,
                  426: 5, 427: 100, 428: 0, 329: 2, 330: 0, 331: 0,
                  346: 0, 320: 0, 30: 0, 12: 500})
        b.temperature(2, 50)
        b.temperature(0, 270)
        reader = Reader(b, family)
        b.start()
        for i, (error, demand) in enumerate(zip((5, 6, 20, 21, 40, 41, 50, 51), (0, 200, 200, 300, 300, 400, 400, 500))):
            cid = f'T11-{(41 if family == "cool" else 49)+i:03d}'
            b.config({315: 1})
            time.sleep(.25)
            assert reader.read()['valid'] == 0
            requested = 270 + error if family == 'cool' else 270 - error
            b.temperature(0, requested)
            b.config({315: 0})
            p = reader.phase('initial_' + str(error), 7, kp=5, ti=100, T=3)
            ticks = p['ticks'][:2]
            exact = len(ticks) == 2 and all(t['after']['history'][0] == error for t in ticks)
            passed = p['passed'] and exact and all(t['after']['valid'] == j+1 and t['after']['n'] == demand for j, t in enumerate(ticks))
            b.record_local(cid, passed,
                f'{family}初始E={error/10:.1f}℃，要求N={demand}，前两拍实际N={[t["after"]["n"] for t in ticks]}，'
                f'实际E={[t["after"]["history"][0] for t in ticks]}；正常控制方式切换清历史，不写PID RAM。',
                {'passed': passed, 'requested_error': error, 'expected_demand': demand, 'phase': p, 'exact_input': exact})
            assert passed, (cid, 'Inspect input precision and retained scan data')
    except Exception:
        b.log['error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        if reader: reader.close()
        b.finish()
        print('INITIAL RESTORED', family, b.log.get('restored'), b.path, flush=True)


def preheat():
    b = HeatBench('preheat_temperature_boundaries')
    reader = None
    try:
        b.setup(1)
        b.config({128: 0, 127: 0, 332: 0, 333: 1, 334: 0, 126: 0, 248: 0,
                  346: 0, 374: 1, 375: 50, 376: 40, 412: 1,
                  350: 5, 351: 100, 352: 0, 329: 2, 330: 0, 331: 0})
        b.temperature(3, 39)
        reader = PidReader(b, 'preheat')
        b.start()
        for i, temp in enumerate((39, 40, 41, 50, 59, 60, 61)):
            cid = f'T11-{78+i:03d}'
            # Establish a nonzero, nonsaturated demand through ordinary PID
            # before each boundary; do not fabricate the starting demand.
            b.config({350: 10, 351: 1})
            b.temperature(3, 30)
            began = time.monotonic()
            while reader.read()['n'] < 150:
                assert time.monotonic()-began < 30
                time.sleep(.05)
            b.config({350: 5, 351: 100})
            b.temperature(3, temp)
            p = reader.phase('post_temperature_' + str(temp), 6, 5, 100, 0, 1, 40)
            exact = all(t['after']['history'][0] == 50-temp for t in p['ticks'])
            nonsaturated = all(0 < t['before']['n'] < 1000 for t in p['ticks'])
            passed = p['passed'] and exact and nonsaturated
            b.record_local(cid, passed,
                f'预热后温{temp/10:.1f}℃，设定5℃/幅差4℃，默认Kp5/Ti100/Td0；'
                f'{len(p["ticks"])}真实扫描，严格死区及DA1逐拍匹配={p["passed"]}；'
                f'合法校准输入精确={exact}，起始非饱和={nonsaturated}。',
                {'passed': passed, 'temperature': temp, 'phase': p, 'exact_input': exact, 'nonsaturated': nonsaturated})
            assert passed, cid
    except Exception:
        b.log['error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        if reader: reader.close()
        b.finish()
        print('PREHEAT BOUNDARIES RESTORED', b.log.get('restored'), b.path, flush=True)


def humidity_deadband():
    b = HeatBench('humidity_exact_deadband')
    reader = None
    try:
        b.setup(1)
        b.config({128: 0, 127: 0, 332: 0, 333: 0, 334: 1, 126: 1, 248: 1,
                  168: 0, 162: 500, 361: 400, 412: 1, 353: 1, 354: 1, 355: 0,
                  346: 0, 329: 2, 330: 0, 331: 0})
        ai_exact(b, 300)
        reader = Reader(b, 'humidity')
        b.start()
        prepare = reader.phase('establish_nonzero_demand', 12, kp=1, ti=1, width=400)
        assert prepare['passed']
        b.config({354: 100})
        phases = []
        for e in (0, 99, -99, 100, -100):
            ai_exact(b, 500-e)
            p = reader.phase('exact_humidity_error_' + str(e), 5, kp=1, ti=100, width=400)
            p['exact_error'] = all(t['after']['history'][0] == e for t in p['ticks'])
            p['nonsaturated'] = all(0 < t['before']['n'] < 1000 for t in p['ticks'])
            phases.append(p)
        passed = all(p['passed'] and p['exact_error'] and p['nonsaturated'] for p in phases)
        b.record_local('T11-036', passed,
            '加湿E=0/±9.9/±10.0%RH、SDF40%RH，AI1工程映射软件模拟后逐点回读精确误差；'
            '非饱和需求下严格死区及DA2逐拍核对；不等同物理湿度信号源。',
            {'passed': passed, 'phases': phases, 'prepare': prepare})
        assert passed
    except Exception:
        b.log['error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        if reader: reader.close()
        b.finish()
        print('HUMIDITY DEADBAND RESTORED', b.log.get('restored'), b.path, flush=True)


def environmental_heat(cooling=False):
    b = HeatBench('environment_cool_targets' if cooling else 'environment_heat_targets')
    try:
        b.setup(0 if cooling else 1)
        b.config({315: 1, 327: 1, 128: 1, 127: 0, 332: 0, 333: 0,
                  334: 0, 126: 0, 248: 0, 316: 350, 317: 220,
                  318: 0, 319: 120, 329: 2, 330: 0, 331: 0,
                  346: 0, 320: 0, 30: 0, 12: 500})
        b.temperature(2, 219 if cooling else 121)
        b.start()
        rows = {}
        points = (219, 220, 221, 252, 253, 285, 317, 318, 349, 350, 351) if cooling else (-1, 0, 1, 30, 60, 90, 119, 120, 121)
        # Both directions; observe target computation separately from delayed
        # compressor hardware availability and final actual running count.
        for direction, temps in (('up', points), ('down', tuple(reversed(points)))):
            for i, temp in enumerate(temps):
                cid = f'T09-{(1 if cooling else 12)+points.index(temp):03d}'
                b.temperature(2, temp)
                time.sleep(.3)
                s = b.sample('environment_heat_' + str(temp))
                actual_temp = signed16(b.rd(512)[0])
                cn = b.rd(2678)[0]
                want = (cn if actual_temp >= 350 else 0 if actual_temp <= 220 else (cn*(actual_temp-220)+129)//130) if cooling else (cn if actual_temp <= 0 else 0 if actual_temp >= 120 else (cn*(120-actual_temp)+119)//120)
                target = b.rd(881)[0]
                row = dict(direction=direction, requested_temp=temp, actual_temp=actual_temp,
                           installed=cn, expected=want, target=target, snapshot=s,
                           passed=actual_temp == temp and cn == 4 and target == want)
                rows.setdefault(cid, []).append(row)
                b.log['environment_rows'] = rows
                b.save()
                print('ENV', 'COOL' if cooling else 'HEAT', direction, temp, target, want, row['passed'], flush=True)
        for cid, samples in rows.items():
            ok = len(samples) == 2 and all(r['passed'] for r in samples)
            b.record_local(cid, ok,
                f'全新风定频、CN=4，默认'+('HLM35℃/HLC22℃' if cooling else 'HRM0℃/HRC12℃')+f'；新风{samples[0]["requested_temp"]/10:.1f}℃'
                f'双向目标台数={[s["target"] for s in samples]}，独立向上取整公式={[s["expected"] for s in samples]}。'
                '本例确认目标计算；逐台时序、实际信号源和端子仍待验。', {'passed': ok, 'rows': samples})
        assert all(s['passed'] for samples in rows.values() for s in samples)
    except Exception:
        b.log['error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        b.finish()
        print('ENV HEAT RESTORED', b.log.get('restored'), b.path, flush=True)


def ambient_preheat():
    b=HeatBench('default_ambient_preheat')
    try:
        b.setup(1)
        b.config({128:0,127:0,332:0,333:1,334:0,126:0,248:0,346:0,
                  374:0,356:0,357:-50,329:2,330:0,331:0})
        initial=signed16(b.rd(512)[0])
        offset=signed16(b.rd(493)[0])
        base=initial-offset
        points=(1,0,-1,-10,-25,-49,-50,-51)
        reachable=[temp for temp in points if -100<=temp-base<=100]
        b.log['unreachable_cases']={f'T11-{70+i:03d}':dict(requested=temp,raw_temperature=base,
            required_offset=temp-base,decision='跳过：超过合法±10℃校准可达范围；不写越界值')
            for i,temp in enumerate(points) if temp not in reachable}
        b.save()
        if not reachable:return
        b.temperature(2,max(reachable))
        b.start()
        rows={}
        for direction,temps in (('descending',reachable),('ascending',list(reversed(reachable)))):
            for temp in temps:
                cid=f'T11-{70+points.index(temp):03d}'
                b.temperature(2,temp)
                time.sleep(.3)
                actual=signed16(b.rd(512)[0])
                s=b.sample_heat(cid)
                want=max(0,min(1000,-actual*20))
                row=dict(direction=direction,requested=temp,actual=actual,expected=want,snapshot=s,
                         passed=actual==temp and s['preheat']==want and s['ao'][1]==want)
                rows.setdefault(cid,[]).append(row)
                b.log['ambient_rows']=rows
                b.save()
                print('DEFAULT PREHEAT',direction,temp,s['preheat'],want,row['passed'],flush=True)
        for cid,samples in rows.items():
            passed=len(samples)==2 and all(s['passed'] for s in samples)
            b.record_local(cid,passed,
                f'默认预热开启0℃/满载−5℃，新风{samples[0]["requested"]/10:.1f}℃双向'
                f'N/DA1={[s["snapshot"]["preheat"] for s in samples]}；按clamp(−T/5,0,1)核对；'
                '合法NTC校准，实际端子电压未测。',{'passed':passed,'rows':samples})
    except Exception:
        b.log['error']=traceback.format_exc()
        b.save()
        raise
    finally:
        b.finish()
        print('DEFAULT PREHEAT RESTORED',b.log.get('restored'),b.path,flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--families', nargs='+', default=['cool', 'heatpump', 'preheat', 'envheat'])
    for family in p.parse_args().families:
        if family == 'preheat': preheat()
        elif family == 'humidity': humidity_deadband()
        elif family == 'envheat': environmental_heat()
        elif family == 'envcool': environmental_heat(cooling=True)
        elif family == 'ambient-preheat': ambient_preheat()
        else: initial(family)
