"""Execute actual330 ARM: legal outdoor waits, bounded failed starts and feedback."""
import hashlib
import json
from test_defrost_lifecycle_arm import Firmware, ROOT

B=ROOT/'.codex-tmp/restart_guard_v1060_v1243_20261112'
D=ROOT/'测试证据/四项复核_20261112/restart_guard_ARM_results.json'
ROWS=[]


def check(profile,name,actual,expected):
    row=dict(profile=profile,name=name,actual=actual,expected=expected,passed=actual==expected)
    ROWS.append(row);assert row['passed'],row


def image(profile):
    f=Firmware(B/profile/f'PSC330_V10.60_{profile}.axf')
    for u in range(4):f.var('PSC316SetValid',1,u,1)
    return f


def main():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        f=image(profile)
        for delay,base in ((0,60),(15,75),(255,300)):
            f.p(45,delay)
            for stop in (10,30,60,120,300):
                for unit in range(1,5):
                    f.p(1830+(unit-1)*48+15,stop)
                    check(profile,f'unit{unit}/delay{delay}/stop{stop}',f.call('CompStartTimeoutSeconds',unit),base+stop)
        f.p(45,15)
        for unit in range(1,5):
            for invalid in (0,9,301,65535):
                f.p(1830+(unit-1)*48+15,invalid)
                check(profile,f'unit{unit}/invalid{invalid}/bounded',f.call('CompStartTimeoutSeconds',unit),75)
            f.p(1830+(unit-1)*48+15,120)
            f.var('PSC316SetValid',0,unit-1,1)
            check(profile,f'unit{unit}/unknown-settings/original-guard',f.call('CompStartTimeoutSeconds',unit),75)
            f.var('PSC316SetValid',1,unit-1,1)
        for stop in (10,30,60,120,300):
            for comp in (0,1):
                f=image(profile);f.p(45,15);f.p(1845,stop)
                start=0x100000000-5000
                f.field(True,1,'CompControl',comp,1)
                f.field(True,1,'CompVVFfre',comp,25)
                f.var('Systick_1ms',start);f.call('CompStartStateUpdate')
                f.var('Systick_1ms',start+75000);f.call('CompStartStateUpdate')
                check(profile,f'comp{comp}/stop{stop}/old75s-request-retained',f.field(True,1,'CompControl',comp),1)
                timeout=(75+stop)*1000
                f.var('Systick_1ms',start+timeout-1);f.call('CompStartStateUpdate')
                check(profile,f'comp{comp}/stop{stop}/before-new-boundary',f.field(True,1,'CompControl',comp),1)
                f.var('Systick_1ms',start+timeout);f.call('CompStartStateUpdate')
                check(profile,f'comp{comp}/stop{stop}/failed-start-withdraws',f.field(True,1,'CompControl',comp),0)
                check(profile,f'comp{comp}/stop{stop}/failed-start-frequency-zero',f.field(True,1,'CompVVFfre',comp),0)
                check(profile,f'comp{comp}/stop{stop}/retry-still5min',
                      f.var('CompStartRetryUntil',index=2+comp,width=8),start+timeout+300000)
                f=image(profile);f.p(45,15);f.p(1845,stop)
                f.field(True,1,'CompControl',comp,1)
                f.var('Systick_1ms',start);f.call('CompStartStateUpdate')
                f.field(False,1,'CompStatus',comp,3)
                f.var('Systick_1ms',start+timeout);f.call('CompStartStateUpdate')
                check(profile,f'comp{comp}/stop{stop}/feedback-at-boundary-wins',
                      [f.field(True,1,'CompControl',comp),f.var('CompStartConfirmed',index=2+comp,width=1),
                       f.var('CompStartRetryUntil',index=2+comp,width=8)],[1,1,0])
                f.field(True,1,'CompControl',comp,0);f.call('CompStartStateUpdate')
                check(profile,f'comp{comp}/stop{stop}/normal-off-clears-tracking',
                    [f.var('CompStartTracked',index=2+comp,width=1),f.var('CompStartConfirmed',index=2+comp,width=1)],[0,0])
    hashes={profile:hashlib.sha256((B/profile/f'PSC330_V10.60_{profile}.axf').read_bytes()).hexdigest()
            for profile in ('PRODUCTION','BENCH_ONLY_3S')}
    q=dict(total=len(ROWS),passed=sum(r['passed'] for r in ROWS),rows=ROWS,
           hardware_access=False,AXF_SHA256=hashes)
    D.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8')
    print(q['passed'],'restart guard ARM checks passed')


if __name__=='__main__':main()
