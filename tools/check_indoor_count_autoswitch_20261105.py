"""V10.50: real QHS60 holds in both cool->heat reheat branches."""
import time
import traceback
from run_indoor_bench_20261105 import ControlBench, now, signed16


def main():
    b=ControlBench('runtime_count_autoswitch')
    # Auto-switch legitimately changes these without a direct script write.
    # Include them in cleanup even when baseline() finds mode already correct.
    for address in (1,236,326):
        b.original[str(address)]=b.rd(address)[0]
        b.touched.add(address)
    b.save()
    try:
        for humidity in (0,1):
            entry={'humidity_control':humidity,'started':now()}
            b.log['cases'][str(humidity)]=entry
            b.baseline(0)
            b.config({30:0,42:3,43:3,214:3,125:humidity,126:humidity,248:1,
                      128:2,127:1,129:1,332:1,334:0,160:250,161:250,
                      320:0,321:50,322:60,412:1,347:100,348:1,349:0,
                      1241:1,1245:299,1246:301,1247:299,1248:301,1249:0})
            offset=signed16(b.rd(495)[0])+220-signed16(b.rd(511)[0])
            assert -100<=offset<=100
            b.wr(495,offset)
            time.sleep(4);b.wr(524,1);time.sleep(.3);b.wr(524,0)
            b.wr(398,1)
            b.wait('autoswitch reheat established',lambda s:s['state'][9]==2 and
                   b.rd(890)[0]>500 and b.rd(119)[0]<=1,60)
            b.wr(320,1)
            entry['hold_samples']=[];start=time.monotonic();last=-15
            while True:
                s=b.snapshot('auto hold humidity'+str(humidity))
                s['count_119']=b.rd(119)[0]
                s['switch_diag_883_884']=b.rd(883,2)
                s['reheat_890']=b.rd(890)[0]
                s['elapsed_s']=round(time.monotonic()-start,3)
                entry['hold_samples'].append(s)
                assert not any(s['faults']),s
                if s['elapsed_s']-last>=10:
                    print('AUTO',humidity,s['elapsed_s'],'step',s['state'][9],
                          'count',s['count_119'],'hold',s['switch_diag_883_884'],flush=True)
                    b.save();last=s['elapsed_s']
                if s['state'][9]!=2:
                    assert s['elapsed_s']>=58,('early transition',s)
                    entry['transition_start_elapsed_s']=s['elapsed_s'];break
                assert s['count_119']<=1 and s['reheat_890']>500,s
                assert time.monotonic()-start<70,('no transition',s)
                time.sleep(.3)
            entry['heat_running']=b.wait('auto mode transition completed',
                lambda s:s['state'][9]==2 and s['mode_1_236'][1]==1,90)
            entry['heat_count']=b.rd(119)[0]
            assert entry['heat_count']==0 and not any(x in (2,3,4)
                    for u in entry['heat_running']['outdoor_status'] for x in u)
            b.stop();assert b.rd(119)==[0]
            entry['passed']=True;entry['finished']=now();b.save()
            print('PASS real auto-switch humidity',humidity,flush=True)
        assert not any(w['address']==119 for w in b.log['writes'])
        b.log['passed']=True
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()


if __name__=='__main__':main()
