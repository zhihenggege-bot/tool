"""Read-only, independent post-batch configuration and stopped-state check."""
from remaining_serial_only_live_20261106 import *
from run_indoor_bench_20261105 import snap


def main():
    reference=D/'flash_special_remote_20261106.json'
    before=json.loads(reference.read_text('utf8'))['config']
    path=D/('independent_final_readback_20261109_'+time.strftime('%H%M%S')+'.json')
    assert not path.exists()
    report=dict(at=now(),read_only=True,reference=reference.relative_to(R).as_posix(),snapshots=[])
    c=runtime.client()
    try:
        report['versions']=c.read_holding_registers(1,2622,18)
        report['profiles']=c.read_holding_registers(1,1298,2)
        after={}
        for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)):
            after.update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        report['configuration_after']=after
        report['configuration_mismatches']={a:dict(before=v,after=after[a])
            for a,v in before.items() if a in after and a not in ('167','373') and v!=after[a]}
        report['excluded_dynamic_registers']=[167,373]
        report['gateway_1833']=c.read_holding_registers(1,1833,1)[0]
        for _ in range(3):
            report['snapshots'].append(snap(c));time.sleep(.4)
        report['checks']=dict(
            firmware_expected=report['versions']==runtime.EXPECTED,
            bench_profile=report['profiles'][1]==15107,
            configuration_restored=not report['configuration_mismatches'],
            dynamic_disable_restored=report['gateway_1833']==0,
            loads_stopped=all(s['state'][9]==0 and loads_off(s) for s in report['snapshots']),
            outdoor_stopped=all(all(v==0 for pair in s['outdoor_status'] for v in pair) for s in report['snapshots']),
            fault_free=all(not any(s['faults']) for s in report['snapshots']))
        report['active_fault_registers']=sorted({594+i for s in report['snapshots'] for i,v in enumerate(s['faults']) if v})
        report['passed']=all(report['checks'].values())
    except Exception:
        report['error']=traceback.format_exc();raise
    finally:
        c.close();dump(path,report)
    print(json.dumps(dict(evidence=str(path),checks=report['checks'],
        active_fault_registers=report['active_fault_registers'],
        mismatches=report['configuration_mismatches']),ensure_ascii=False))


if __name__=='__main__':main()
