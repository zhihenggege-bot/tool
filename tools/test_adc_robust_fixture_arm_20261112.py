"""Offline actual ADC and scaling ARM: normal endpoints tolerate raw variation."""
import hashlib
import json
from test_defrost_lifecycle_arm import Firmware, ROOT


def main():
    rows=[];hashes={}
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        path=ROOT/'.codex-tmp/restart_guard_v1060_v1243_20261112'/profile/f'PSC316_V12.43_{profile}.axf'
        hashes[profile]=hashlib.sha256(path.read_bytes()).hexdigest()
        f=Firmware(path);f.var('Systick_1ms',5000)
        for ch in range(4):
            f.p(468+ch,1)
            for off,val in {0:1,1:1,2:800,3:1600,4:1737,5:2380,8:0,9:0}.items():
                f.p(302+12*ch+off,val)
        for raw,expected in ((600,1737),(745,1737),(1000,1737),(3500,2380),(3724,2380),(3780,2380)):
            for ch in range(6):
                f.var('ADC_Val',raw,ch,2)
                for j in range(10):f.write(f.symbols['ADC_Val_Filter'][0]+20*ch+2*j,raw,2)
            f.var('uc10ms',1);f.var('ADNum',9);f.call('ADProcess')
            for ch in range(4):
                signal=f.var('AI',index=ch,width=2)
                actual=f.call('OutdoorScaleAiChannel',ch,signal)
                row=dict(profile=profile,ch=ch,raw=raw,actual_signal=signal,expected_pressure=expected,
                    actual_pressure=actual,passed=actual==expected)
                rows.append(row);assert row['passed'],row
    q=dict(total=len(rows),passed=sum(r['passed'] for r in rows),rows=rows,AXF_SHA256=hashes,
        hardware_access=False,scope='Normal AI signal800/1600 clamps tested acquisition variations; no control threshold edits')
    dest=ROOT/'测试证据/四项复核_20261112/restart_fix/adc_robust_fixture_ARM_results.json'
    dest.write_text(json.dumps(q,indent=2),encoding='utf8')
    print(q['passed'],q['total'])


if __name__=='__main__':main()
