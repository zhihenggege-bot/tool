"""Execute both compiled profiles; never accesses a serial port or debug probe."""
import json
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware,ROOT

P=ROOT/'.codex-tmp/vfd_scale_v1242_20261112'
D=ROOT/'测试证据/四项复核_20261112'

def main():
    D.mkdir(exist_ok=True);rows=[]
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        f=Firmware(P/profile/f'PSC316_V12.42_{profile}.axf')
        for maximum in (30,40,50):
            f.p(176,maximum)
            for hz in (-1,0,1,5,20,30,40,50,60):
                result=f.call('OutdoorFanSpeedToDA',hz)
                expected=min(1000,max(0,hz*20))
                rows.append(dict(profile=profile,kind='integer_hz',maximum=maximum,target=hz,actual=result,expected=expected))
                assert result==expected,rows[-1]
            for minimum in (0,5,30):
                f.p(177,minimum)
                for speed in (-1,0,1,49,50,51,125,200,299,300,399,400,499,500,501,600):
                    direct=f.call('OutdoorFanSpeed10ToDA',speed)
                    expected=min(1000,max(0,speed*2))
                    rows.append(dict(profile=profile,kind='deci_hz',maximum=maximum,minimum=minimum,target=speed,actual=direct,expected=expected))
                    assert direct==expected,rows[-1]
                    f.call('OutdoorFanSetSpeed',speed)
                    limited=max(minimum*10,min(maximum*10,speed)) if speed>0 else 0
                    actual=[f.p(a) for a in (1468,1469)]
                    rows.append(dict(profile=profile,kind='target_limit_and_AO',maximum=maximum,minimum=minimum,target=speed,actual=actual,expected=[limited*2,0]))
                    assert actual==[limited*2,0],rows[-1]
    result=dict(total=len(rows),passed=len(rows),hardware_access=False,rows=rows)
    (D/'fixed50Hz_ARM_results.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print('ARM SCALING',len(rows),'passed',flush=True)

if __name__=='__main__':main()
