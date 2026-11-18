"""Independent read-only recovery check; preserve environmental alarms as such."""
from remaining_serial_only_live_20261106 import *
from run_indoor_bench_20261105 import snap


def main():
    reference=D/'remaining571_heat_dynamic_serial_multifault_priorities_20261106_170656.json'
    initial=json.loads(reference.read_text('utf8'))
    before=initial['full_configuration_before']
    batches=[]
    for p in sorted(D.glob('remaining571_heat_dynamic_*_20261106_*.json')):
        d=json.loads(p.read_text('utf8'))
        if d.get('started','')>=initial['started']:
            assert d.get('restored') is True and not d.get('cleanup_error'),str(p)
            batches.append((p,d))
    report=dict(at=now(),read_only=True,reference=reference.relative_to(R).as_posix(),
        batches=[p.relative_to(R).as_posix() for p,_ in batches],snapshots=[])
    path=D/('serial_followup_final_readback_20261106_'+time.strftime('%H%M%S')+'.json')
    assert not path.exists()
    c=runtime.client()
    try:
        report['versions']=c.read_holding_registers(1,2622,18)
        report['profiles']=c.read_holding_registers(1,1298,2)
        after={}
        for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)):
            after.update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        report['full_configuration_after']=after
        report['configuration_mismatches']={a:dict(before=v,after=after[a])
            for a,v in before.items() if a in after and a!='398' and v!=after[a]}
        for _ in range(3):
            report['snapshots'].append(snap(c));time.sleep(.4)
        report['temperatures_510_513']=[signed16(v) for v in c.read_holding_registers(1,510,4)]
        report['ntc_calibrations_492_495']=[signed16(v) for v in c.read_holding_registers(1,492,4)]
        report['checks']=dict(
            expected_firmware=report['versions']==runtime.EXPECTED,
            bench_profile=report['profiles'][1]==15107,
            configuration_restored=not report['configuration_mismatches'],
            all_loads_stopped=all(s['state'][9]==0 and loads_off(s) for s in report['snapshots']),
            outdoor_stopped=all(all(v==0 for pair in s['outdoor_status'] for v in pair) for s in report['snapshots']),
            fault_free=all(not any(s['faults']) for s in report['snapshots']))
        report['active_fault_registers']=sorted({594+i for s in report['snapshots'] for i,v in enumerate(s['faults']) if v})
        report['passed']=all(report['checks'].values())
        if report['active_fault_registers']==[619]:
            report['environment_note']='AI1室内湿度输入无效报警仍在；未清除故障位，未将有报警的终检记为全部通过。配置恢复/停止状态另按各检查项判定。'
    except Exception:
        report['error']=traceback.format_exc();raise
    finally:
        c.close();dump(path,report)
    print(json.dumps(dict(evidence=str(path),checks=report['checks'],
        active_fault_registers=report['active_fault_registers'],
        mismatches=report['configuration_mismatches']),ensure_ascii=False))


if __name__=='__main__':main()
