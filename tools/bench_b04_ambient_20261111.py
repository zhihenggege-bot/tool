"""Observe 316 ambient permission and actual software outputs with normal 330 demand."""
from joint_v1058_context_20261111 import *
from bench_b01_ntc_20261111 import fixture
import multiprocessing as mp
import math
import queue
import struct

PAIRS=((0,1),(1,3),(2,4))


def run(typ):
    b=current_bench_class()(f'B04_ambient_type{typ}')
    e=b.log['ambient']=dict(type=typ,points=[],scope='1# raw NTC0; normal 330 cooling demand; software output and BENCH timing only')
    proc=None
    try:
        assert b.rd(398)==[0] and b.rd(709)==[0] and not any(b.rd(2598,2))
        b.setup(0);b.gateway(1830,typ);b.gateway(1831,PAIRS[typ][1]);b.gateway(1835,150)
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
                  160:250,161:250,120:20,412:1,416:100,417:1,418:0,
                  315:0,320:0,346:0,245:1,247:0,329:2,330:0,331:0,
                  365:1,411:200,10:500,12:500})
        b.temperature(0,290)
        table=struct.unpack('<201f',bytes(b.ot.read_memory_block8(b.outsy['NTCtable'][0],804)))
        cal=signed16(b.ot.read16(b.outsy['Parameter'][0]+986))
        e['outdoor_timing']=b.ot.read16(b.outsy['Parameter'][0]+2596)
        b.outss.close();b.outss=None
        ctx=mp.get_context('spawn'); values=ctx.Array('i',[-1]*8); stop=ctx.Event(); stream=ctx.Queue()
        proc=ctx.Process(target=fixture,args=(BOARDS[0],b.outsy,values,stop,stream),daemon=True);proc.start()
        kind,data=stream.get(timeout=25); assert kind=='ready',(kind,data)

        def set_input(temp):
            value=temp-cal;idx=math.floor(value/10)+50; frac=value/10-(idx-50)
            resistance=table[idx]+frac*(table[idx+1]-table[idx]); raw=round(2.048*resistance/(5.1+resistance)/.0000625)
            with values.get_lock():values[0]=raw
            return time.monotonic(),raw

        def point(label,temp,seconds,expect,case,require_running=False,hold_running=False):
            issued,raw=set_input(temp)
            row=dict(label=label,id=case,temp10=temp,raw=raw,expect=expect,samples=[]);e['points'].append(row); b.save()
            end=issued+seconds+25; exact=None
            try:
                while time.monotonic()<end:
                    try: kind,s=stream.get(timeout=1)
                    except queue.Empty:
                        if not proc.is_alive():raise RuntimeError('NTC fixture exited')
                        continue
                    if kind=='error':raise RuntimeError(s)
                    if kind!='sample' or s['t']<issued or time.monotonic()-s['t']>1.5:continue
                    s.update(temp10=signed16(s['params']['1422']),lock=bool(s['params']['1501']&32),
                             layer330=b.rd(2598,2),status330=b.rd(1555,2),global_environment_off=b.rd(737)[0])
                    row['samples'].append(s)
                    if any(s['alarms']):raise RuntimeError(('unexpected alarm',s['alarms']))
                    if s['temp10']==temp:
                        if require_running and (exact is None or hold_running):
                            if s['output'][:2]!=[1,1] or any(s['params'][str(a)]!=1 for a in (1400,1403)):
                                row['coverage']='running_precondition_lost'
                                raise RuntimeError('running ambient case lost compressor request/output precondition')
                        if exact is None:exact=s['t']
                        if s['t']-exact>=seconds:
                            row.update(final=s,observed_s=s['t']-exact,matches=None if expect is None else s['lock']==expect)
                            return row
                    else:exact=None
                raise TimeoutError('exact input did not hold for requested duration')
            except Exception as exc:
                row['error']=repr(exc);row['matches']=None;return row
            finally:
                row['finished']=now();b.save();print('AMBIENT',typ,label,row.get('matches'),row.get('error',''),flush=True)

        lower_start=(150,0,-140)[typ]
        lower_stop=(130,-20,-150)[typ]
        low_id=('O-AMBIENT-001','O-AMBIENT-004','O-AMBIENT-005')[typ]
        high_id=f'O-AMBIENT-{10+typ:03d}'
        set_input(lower_start)
        b.start()
        point('equal_lower_start',lower_start,9,True,low_id)
        point('above_lower_start',lower_start+1,9,False,low_id)
        b.wait('both 1# cooling outputs available',lambda s:s['outdoor_status'][0]==[2,2],160)
        point('running_equal_lower_stop',lower_stop,8,False,low_id)
        # A lower-bound test may have withdrawn requests through another gate.
        # Reestablish a safe ambient and actual running state before high tests.
        point('high_test_safe_ambient',200,8,False,high_id)
        b.wait('both 1# requests/outputs restored before43',lambda s:s['outdoor_status'][0]==[2,2],180)
        point('high_test_running_confirm',200,3,False,high_id,True,True)
        point('running_43_first_short',430,20,False,high_id,True,True)
        point('42_9_break_high_hold',429,4,False,high_id)
        point('running_43_full',430,66,True,high_id,True)
        point('below_43_recovery',429,8,False,high_id)
        e['status']='executed'
    except BaseException:
        e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if proc is not None:
                with values.get_lock():values[:]=[-1]*8
                stop.set();proc.join(8)
                if proc.is_alive():proc.terminate();proc.join(3)
                e['fixture_exitcode']=proc.exitcode;stream.close()
        finally:
            try:
                if b.outss is None:
                    b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
                        options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
                    b.outss.open();b.ot=b.outss.target
                b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('type',type=int,choices=(0,1,2));run(parser.parse_args().type)
