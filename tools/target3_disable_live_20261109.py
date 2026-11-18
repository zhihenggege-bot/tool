"""Dynamic disable and replacement through the real gateway, normal config only."""
from remaining_serial_only_live_20261106 import *


def main():
    b=SerialHeatBench('target3_disable_replacement_20261109')
    gateway_before={}
    b.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def gateway(address,value):
        base=1830+((address-1830)//48)*48
        began=time.monotonic()
        while b.rd(base+43)[0]==1:
            assert time.monotonic()-began<45,('gateway busy',address)
            time.sleep(.2)
        gateway_before.setdefault(address,b.rd(address)[0])
        b.log['gateway_original']={str(a):v for a,v in gateway_before.items()};b.save()
        b.c.write_single_register(1,address,value)
        began=time.monotonic()
        while True:
            actual=b.rd(address)[0];state=b.rd(base+43)[0]
            if actual==value and state!=1:break
            assert time.monotonic()-began<45,('gateway readback not confirmed',address,value,actual,state)
            time.sleep(.2)
        b.log.setdefault('gateway_transactions',[]).append(dict(at=now(),address=address,requested=value,readback=actual,state=state));b.save()
    try:
        b.setup(0)
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
                  315:1,327:1,316:350,317:220,320:0,245:1,247:0,
                  329:2,330:0,331:0,346:0,335:0,336:0,337:0,338:0})
        b.temperature(0,250);b.temperature(2,300);b.reset_faults();b.start()
        def statuses(s):return [v for pair in s['outdoor_status'] for v in pair]
        before=b.wait('actual three cooling compressors',lambda s:
                      b.rd(881)[0]==3 and sum(v==2 for v in statuses(s))==3,160)
        prior=statuses(before);selected=next(i for i,v in enumerate(prior) if v==2)
        idle=next(i for i,v in enumerate(prior) if v==0)
        address=1830+(selected//2)*48+3+selected%2
        assert b.rd(address)[0]==0,('candidate already disabled',address)
        entry=dict(passed=False,target=3,installed_CN=b.rd(2678)[0],before=before,
                   disabled_index=selected,replacement_index=idle,gateway_register=address,samples=[])
        b.log['cases']['T10-014']=entry;b.save()
        gateway(address,1)
        began=time.monotonic();stable=None;last=None
        while True:
            s=b.snapshot('target3 dynamic disable replacement');st=statuses(s)
            s.update(target=b.rd(881)[0],installed_CN=b.rd(2678)[0]);entry['samples'].append(s)
            assert not any(s['faults']) and s['installed_CN']==4 and s['target']==3,s
            marker=tuple(st)
            if marker!=last:print('TARGET3 DISABLE',selected,'statuses',st,'target',s['target'],flush=True);last=marker;b.save()
            if st[selected] not in (2,3,4) and st[idle]==2 and sum(v==2 for v in st)==3:
                if stable is None:stable=time.monotonic()
                if time.monotonic()-stable>=5:entry['after']=s;break
            else:stable=None
            assert time.monotonic()-began<150,('replacement did not settle',selected,idle,s)
            time.sleep(.2)
        entry.update(passed=True,duration_s=time.monotonic()-began)
        b.record_local('T10-014',True,f'CN4、环境制冷目标3，先建立3台真实316制冷软件反馈；网关[{address}]=1动态禁用正在运行的第{selected+1}路，禁用回读/事务完成后该路停止，原空闲第{idle+1}路补位，目标仍3且安装CN仍4，3台反馈稳定5秒。未写需求/状态/累计/计时RAM；物理输出、正式最短开停、其它故障/化霜组合仍待验。',entry)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.stop()
            for a,v in list(gateway_before.items()):gateway(a,v)
            b.log['outdoor_configuration_restored']={str(a):b.rd(a)[0]==v for a,v in gateway_before.items()}
            assert all(b.log['outdoor_configuration_restored'].values())
        finally:
            b.finish();print('TARGET3 RESTORED',b.log.get('restored'),b.log.get('outdoor_configuration_restored'),flush=True)


if __name__=='__main__':main()
