"""Verify fixture raw values with actual ADProcess ARM; no hardware access."""
import json
import hashlib
from test_defrost_lifecycle_arm import Firmware, ROOT


def main():
    rows=[];hashes={}
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        path=ROOT/'.codex-tmp/restart_guard_v1060_v1243_20261112'/profile/f'PSC316_V12.43_{profile}.axf'
        hashes[profile]=hashlib.sha256(path.read_bytes()).hexdigest()
        f=Firmware(path);f.var('Systick_1ms',5000)
        for ch in range(4):f.p(468+ch,1)
        for raw,expected in ((745,400),(3724,2000)):
            for ch in range(6):
                f.var('ADC_Val',raw,ch,2)
                for j in range(10):f.write(f.symbols['ADC_Val_Filter'][0]+20*ch+2*j,raw,2)
            f.var('uc10ms',1);f.var('ADNum',9);f.call('ADProcess')
            for ch in range(4):
                actual=f.var('AI',index=ch,width=2)
                row=dict(profile=profile,channel=ch,signal_type=1,raw_adc=raw,expected=expected,actual=actual,passed=actual==expected)
                rows.append(row);assert row['passed'],row
    d=ROOT/'测试证据/四项复核_20261112/restart_fix/adc_fixture_ARM_results.json'
    d.write_text(json.dumps(dict(total=len(rows),passed=sum(r['passed'] for r in rows),hardware_access=False,AXF_SHA256=hashes,rows=rows),indent=2),encoding='utf8')
    print(len(rows),'actual ADC fixture scale checks passed')


if __name__=='__main__':main()
