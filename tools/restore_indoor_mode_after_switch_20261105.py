"""Restore only normal mode after the first auto-switch test cleanup omission."""
import json
import time
import traceback
from run_indoor_bench_20261105 import D,client,snap,loads_off,dump,now


def main():
    original=json.loads((D/'preflight.json').read_text('utf-8'))['config']
    c=client();p=D/('mode_restore_'+time.strftime('%H%M%S')+'.json')
    report={'started':now(),'kind':'Normal HMI mode request only; no RAM writes; no [119] writes'}
    def config():
        values={}
        for a,n in [(0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)]:
            values.update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        return values
    try:
        report['before_snapshot']=snap(c)
        assert report['before_snapshot']['state'][9]==0 and loads_off(report['before_snapshot'])
        before=config();report['before_differences']={a:[v,before[a]] for a,v in original.items() if before[a]!=v}
        assert set(report['before_differences']).issubset({'1','236','326'}),report
        assert c.read_holding_registers(1,398,1)==[0]
        # Normalization updates legacy mode and last-normal mode itself.
        c.write_single_register(1,236,original['236'])
        report['writes']=[{'address':236,'value':original['236'],'at':now()}]
        end=time.monotonic()+10
        while True:
            after=config()
            differences={a:[v,after[a]] for a,v in original.items() if after[a]!=v}
            if not differences:break
            assert time.monotonic()<end,differences
            time.sleep(.3)
        report['after_differences']=differences
        report['after_config']=after;report['after_snapshot']=snap(c)
        assert report['after_snapshot']['state'][9]==0 and loads_off(report['after_snapshot'])
        report['restored']=True;report['finished']=now();dump(p,report)
        print('MODE RESTORED: 236 request normalized 1/236/326; all preflight fields match',p.name)
    except BaseException:
        report['error']=traceback.format_exc();dump(p,report);raise
    finally:c.close()


if __name__=='__main__':main()
