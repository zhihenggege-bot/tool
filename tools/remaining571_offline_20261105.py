"""Supplemental current-image numeric audit; NO physical hardware access.

Historical numeric oracle reused with exact image paths overridden. Raw failures
are retained; they are not silently rewritten as acceptance successes.
"""
import sys, json, traceback, hashlib, importlib.util,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.codex-tmp'))
import spec3438_arm as t
PACKAGE=os.environ.get('PSC_BENCH_PACKAGE','.codex-tmp/runtime_count_v1050_v1239_20261105')
VERSION=os.environ.get('PSC_BENCH_INDOOR_VERSION','10.50')
t.PROFILE=PACKAGE
t.IN=PACKAGE+f'/BENCH_ONLY_3S/PSC330_V{VERSION}_BENCH_ONLY_3S.axf'
t.PROD=PACKAGE+f'/PRODUCTION/PSC330_V{VERSION}_PRODUCTION.axf'
t.D=ROOT/f'测试证据/内机实测_20261105/BENCH_V10{int(VERSION.split(".")[1]):02d}_V1239'
# The historical board() default argument captured the old path at definition.
t.board.__defaults__=(t.IN,)
t.checks=[]

def main():
    errors=[]
    for fn in (t.ambient_and_initial,t.allocation,t.coil,t.autoswitch,
               t.heat_preheat_humid,t.compressor_pid_numeric,
               t.output_and_inhibits,t.remaining_boundaries,t.shared_pid):
        print('OFFLINE START',fn.__name__,flush=True)
        try:fn()
        except Exception:errors.append({'function':fn.__name__,'error':traceback.format_exc()})
    report={'scope':f'current V{VERSION} BENCH actual ARM offline; no hardware IO or full scheduler',
            'image':t.IN,'sha256':hashlib.sha256((ROOT/t.IN).read_bytes()).hexdigest(),
            'checks':t.checks,'errors':errors}
    (t.D/'remaining571_offline_numeric.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('OFFLINE TOTAL',len(t.checks),'MISMATCH',sum(not c['passed'] for c in t.checks),'ERRORS',len(errors),flush=True)
    # Additional oracle imports the overridden module; exports to the NEW folder.
    import spec3438_additional_arm

if __name__=='__main__':main()
