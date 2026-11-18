"""Hold only DI polarity input settings; downstream input/fault/state are read-only."""
from joint_v1058_context_20261111 import *
import multiprocessing as mp
import queue
import struct
from continuous_special_stages_v1055_20261109 import paused


def worker(board,sy,values,stop,out):
    out.cancel_join_thread();ss=None
    try:
        ss=ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target;p=sy['Parameter'][0];out.put(('ready',True));began=time.monotonic();next_read=0
        while not stop.is_set():
            assert time.monotonic()-began<7000,'contact fixture duration limit'
            with values.get_lock():want=list(values[:])
            for ch,v in enumerate(want):
                assert v in (0,1);t.write16(p+2*(ch+2),v)
            t.flush();nt=time.monotonic()
            if nt>=next_read:
                row=dict(at=now(),t=nt,inputs=[t.read8(sy[f'X_{ch:02d}'][0]) for ch in range(8)],
                    qualified_inputs=[t.read8(sy[f'X{ch:02d}_En'][0]) for ch in range(8)],
                    polarities=[t.read16(p+2*(ch+2)) for ch in range(8)],
                    alarms=list(struct.unpack('<28H',bytes(t.read_memory_block8(p+1200,56)))),
                    output=list(t.read_memory_block8(*sy['output'])),layer=t.read16(p+3002),
                    phase=[t.read16(p+2*a) for a in (1420,1421)],
                    lp_start_delay=t.read16(p+54),
                    manual_inputs=[t.read16(p+2*a) for a in range(1300,1310)])
                for name in ('CompRunTime','EnableCheckLow','PSC316DefrostRunTime',
                             'PSC316DefrostState','PSC316DefrostEligible','PSC316DefrostEnded','PSC316DefrostStarted','SysHaveDef'):
                    raw=bytes(t.read_memory_block8(*sy[name]))
                    row[name]=list(struct.unpack('<'+'I'*(len(raw)//4),raw)) if name in ('CompRunTime','EnableCheckLow','PSC316DefrostRunTime','SysHaveDef') else list(raw)
                out.put(('sample',row));next_read=nt+.15
            stop.wait(.002)
    except BaseException:out.put(('error',traceback.format_exc()))
    finally:
        if ss:ss.close()


class ContactInputs:
    def __init__(self,b,original):
        self.b=b;self.original=original
        b.outss.close();b.outss=None
        ctx=mp.get_context('spawn');self.values=ctx.Array('i',[original[ch] for ch in range(8)])
        self.stop=ctx.Event();self.out=ctx.Queue()
        self.proc=ctx.Process(target=worker,args=(BOARDS[0],b.outsy,self.values,self.stop,self.out),daemon=True)
        self.proc.start();kind,data=self.out.get(timeout=25);assert kind=='ready',(kind,data)

    def set(self,ch,value):
        assert value in (0,1)
        with self.values.get_lock():self.values[ch]=value
        return time.monotonic()

    def sample(self,after=0):
        if not getattr(self.b,'_cleaning_up',False):paused()
        end=time.monotonic()+8
        while time.monotonic()<end:
            try:kind,s=self.out.get(timeout=1)
            except queue.Empty:
                assert self.proc.is_alive(),'contact fixture exited';continue
            if kind=='error':raise RuntimeError(s)
            if kind=='sample' and s['t']>=after and time.monotonic()-s['t']<1:return s
        raise TimeoutError('fresh contact input sample')

    def close(self):
        with self.values.get_lock():self.values[:]=[self.original[ch] for ch in range(8)]
        time.sleep(.2);self.stop.set();self.proc.join(10)
        if self.proc.is_alive():self.proc.terminate();self.proc.join(3)
        self.out.close();b=self.b
        b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        b.outss.open();b.ot=b.outss.target
        for ch,v in self.original.items():b.ot.write16(b.outsy['Parameter'][0]+2*(ch+2),v)
        b.ot.flush();assert self.proc.exitcode==0,'contact fixture forced exit'
