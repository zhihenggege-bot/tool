"""Normal protocol starts/stops; never writes runtime count [119] or RAM."""
import time
import traceback
from run_indoor_bench_20261105 import ControlBench, signed16, loads_off, now


def main(modes=(0,1,2,3,4,5)):
    b=ControlBench('runtime_count')

    def sample(label):
        s=b.snapshot(label)
        s['count_119']=b.rd(119)[0]
        s['target_881']=b.rd(881)[0]
        s['expected_from_status']=sum(x in (2,3,4) for unit in s['outdoor_status'] for x in unit)
        b.save()
        return s

    def wait(label,predicate,seconds):
        end=time.monotonic()+seconds;last=None
        while True:
            s=sample(label)
            key=(s['state'][9],s['count_119'],tuple(x for u in s['outdoor_status'] for x in u))
            if key!=last:print(label,key,'target',s['target_881'],flush=True);last=key
            assert not any(s['faults']),(label,s)
            if predicate(s):return s
            assert time.monotonic()<end,(label,'timeout',s)
            time.sleep(.2)

    def ntc(ch,value):
        reg=495-ch;disp={0:511,2:512}[ch]
        current=signed16(b.rd(disp)[0])
        offset=signed16(b.rd(reg)[0])+value-current
        assert -100<=offset<=100,(ch,current,value,offset)
        b.wr(reg,offset)
        end=time.monotonic()+10
        while abs(signed16(b.rd(disp)[0])-value)>3:
            assert time.monotonic()<end
            time.sleep(.2)

    def verify_stopped(label):
        wait(label,lambda s:s['state'][9]==0 and loads_off(s) and
             s['expected_from_status']==0 and s['count_119']==0,40)
        rows=[];end=time.monotonic()+6
        while time.monotonic()<end:
            s=sample(label+' hold');rows.append(s)
            assert s['count_119']==0 and s['expected_from_status']==0 and loads_off(s),s
            time.sleep(.25)
        return rows

    try:
        # Two real outdoor boards respond to ordinary compressor commands.
        for mode in (m for m in modes if m in (0,1)):
            entry={'mode':mode,'started':now()};b.log['cases'][f'normal_{mode}']=entry
            b.baseline(mode)
            b.config({30:0,42:3,43:3,214:3,250:1,251:1,252:1,253:1,
                      128:1 if mode else 0,160:250,161:250,120:20,
                      412:5,416:5,417:100,418:0,426:5,427:100,428:0})
            ntc(0,280 if mode==0 else 220)
            ntc(2,160 if mode==0 else 100)
            b.wr(524,1);time.sleep(.3);b.wr(524,0)
            b.wr(398,1)
            entry['running']=wait(f'mode{mode} actual compressors',
                lambda s:s['state'][9]==2 and s['count_119']>=2 and
                    s['count_119']==s['expected_from_status'],120)
            # Hold long enough for normal PID scans and communication refresh.
            end=time.monotonic()+6;entry['running_hold']=[]
            while time.monotonic()<end:
                s=sample(f'mode{mode} running hold');entry['running_hold'].append(s)
                assert s['count_119']==s['expected_from_status'] and s['count_119']>=2,s
                time.sleep(.25)
            b.wr(398,0)
            # Heating retains its existing 30s humidifier + outdoor fan rundown
            # + 60s cooling period. Do not shorten firmware timing for this test.
            entry['shutdown']=[];end=time.monotonic()+240
            while True:
                s=sample(f'mode{mode} shutdown');entry['shutdown'].append(s)
                if s['state'][9]==0:break
                assert time.monotonic()<end,('shutdown timeout',s)
                time.sleep(.2)
            entry['stopped_hold']=verify_stopped(f'mode{mode} stopped')
            entry['passed']=True;b.save()
            print('PASS count real start/run/stop',mode,flush=True)

        # Exercise the bypass modes after the nonzero->zero real transition.
        for mode in (m for m in modes if m in (2,3,4,5)):
            b.baseline(mode);b.config({323:1,324:1,325:0})
            b.wr(398,1)
            first=wait(f'bypass{mode} running',lambda s:s['state'][9]==2,40)
            assert first['count_119']==0 and first['expected_from_status']==0,first
            b.stop()
            rows=verify_stopped(f'bypass{mode} stopped')
            b.log['cases'][f'bypass_{mode}']={'running':first,'stopped':rows,'passed':True}
            b.save();print('PASS count bypass mode',mode,flush=True)
        assert all(w['address']!=119 for w in b.log['writes'])
        b.log['no_manual_count_restore']=True
        b.log['passed']=True
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--modes',default='0,1,2,3,4,5')
    main(tuple(map(int,parser.parse_args().modes.split(','))))
