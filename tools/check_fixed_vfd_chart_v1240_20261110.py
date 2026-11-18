"""Run current ARM fan function against the supplied fixed/VFD chart.

OFFLINE ONLY. Condensing-temperature function is replaced by a specified input;
fan state/timers are initialized fixtures, not a live whole-board acceptance.
"""
from test_defrost_lifecycle_arm import Firmware, ROOT
import hashlib
import json
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR

PACKAGE = ROOT / '.codex-tmp/four_outdoor_fixes_20261110'
DEST = ROOT / '测试证据/修复后内外机联合实测_20261110/fixed_vfd_chart_ARM_v1240.json'


def main():
    results=[]
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        folder=PACKAGE/profile
        manifest=json.loads((folder/'manifest.json').read_text('utf8'))
        path=folder/f'PSC316_V12.40_{profile}.axf'
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest==manifest['artifacts'][path.name]
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
                   for p,h in manifest['source_inventory'].items())
        scenarios=[
            ('both33.9_unload',339,200,1,0,[1,0,190]),
            ('both34_hold',340,200,1,0,[1,0,200]),
            ('both35_hold',350,200,1,0,[1,0,200]),
            ('both36_load',360,200,1,0,[1,0,210]),
            ('both36.1_load',361,200,1,0,[1,0,210]),
            ('fixed_off_vfd_max_add_fixed',400,500,1,0,[1,1,50]),
            ('fixed_on_vfd_min_remove_fixed',330,50,1,1,[1,0,500]),
            ('fixed_off_vfd_min_stop',330,50,1,0,[0,0,0]),
            ('all_fans_off_cold_remain_off',330,0,0,0,[0,0,0]),
            ('off_at45_start_min',450,0,0,0,[1,0,60]),
            ('off_above45_start_max',451,0,0,0,[1,1,50]),
        ]
        for label,temp,speed,vfd,fixed,want in scenarios:
            f=Firmware(path)
            for a,v in {1:0,107:1,165:2,166:4,176:50,177:5,178:10,179:30,180:30,1400:0,1403:0}.items():f.p(a,v)
            for name,value in [('OutdoorVfdOn',vfd),('OutdoorFixedOn',fixed),
                               ('OutdoorVfdSpeed',speed),('OutdoorFanChangeSeconds',100)]:f.var(name,value)
            for index in range(2):
                f.var('OutdoorFanRunSeconds',100,index,4)
                f.var('OutdoorFanStopSeconds',100,index,4)
            def input_temp(uc,address,size,data):
                uc.reg_write(UC_ARM_REG_R0,temp)
                uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
            addr=f.symbols['OutdoorCondTempMax'][0]&~1
            f.uc.hook_add(UC_HOOK_CODE,input_temp,begin=addr,end=addr)
            # uc1s marks each real controller second, while the function is
            # called only once per second here: this is a local ARM fixture.
            history=[]
            for second in range(1,31):
                f.var('uc1s',1)
                f.var('Systick_1ms',second*1000)
                f.call('OutdoorFanTypeIII')
                history.append([f.var(n) for n in ('OutdoorVfdOn','OutdoorFixedOn','OutdoorVfdSpeed')])
            got=history[-1]
            row=dict(profile=profile,artifact_sha256=digest,case=label,temp10=temp,
                     initial=[vfd,fixed,speed],observed=got,expected=want,
                     matches_chart=got==want,history=history)
            results.append(row)
            print(profile,label,'MATCH' if row['matches_chart'] else 'DIFFERENCE',got,'expected',want,flush=True)
    DEST.write_text(json.dumps(dict(scope='Offline current ARM local fan-function fixtures; temperature-conversion stub; initialized state/timers. Not board/transport/terminal or full elapsed-time acceptance.',results=results),ensure_ascii=False,indent=2),encoding='utf8')
    print('EVIDENCE',DEST)


if __name__=='__main__':main()
