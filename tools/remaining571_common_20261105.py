"""Common journal for the user's remaining 571 BENCH cases.

Uses normal Modbus configuration only; outputs and runtime states are never poked.
Each case retains explicit limitations and the actual subset of acceptance run.
"""
import json
import time
import traceback
from pathlib import Path
from run_indoor_bench_20261105 import ControlBench, D, R, now, dump, result, signed16, loads_off

PENDING=json.loads((D/'remaining_571_manifest.json').read_text('utf-8'))['cases']
CASES={r['用例编号']:r for r in PENDING}


class Bench(ControlBench):
    def __init__(self,name):
        super().__init__('remaining571_'+name)
        self.full_before={}
        for a,n in [(0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)]:
            self.full_before.update({str(a+i):v for i,v in enumerate(self.rd(a,n))})
        self.log['full_configuration_before']=self.full_before
        for a in (1,236,326):
            self.original[str(a)]=self.rd(a)[0];self.touched.add(a)
        # DI_Points_Process uses 155..159 for X00..X04, then
        # 389..397 for X05..X15. 386 is pressure configuration, not DI polarity.
        self.polarities={a:self.rd(a)[0] for a in (*range(155,160),*range(389,398))}
        self.save()

    def sample(self,label):
        s=self.snapshot(label)
        s['diag']=self.rd(872,61)
        s['room_fresh_post']=self.rd(510,4)
        s['humidity']=self.rd(501)[0]
        s['count_119']=self.rd(119)[0]
        s['ntc_raw']=self.rd(1374,12)
        return s

    def observe(self,label,seconds,period=.3):
        end=time.monotonic()+seconds;rows=[]
        while True:
            s=self.sample(label);rows.append(s)
            if time.monotonic()>=end:break
            time.sleep(min(period,max(.01,end-time.monotonic())))
        self.save();return rows

    def reset_faults(self):
        self.wr(524,1);time.sleep(.2);self.wr(524,0)

    def ntc(self,ch,value):
        reg=495-ch;disp={0:511,1:510,2:512,3:513}.get(ch)
        assert disp is not None,'No arbitrary NTC offsets for extended channels'
        offset=signed16(self.rd(reg)[0])+value-signed16(self.rd(disp)[0])
        assert -100<=offset<=100,('legal NTC calibration cannot reach target',ch,value,offset)
        self.wr(reg,offset)
        self.wait(f'NTC{ch}={value}',lambda s:abs(signed16(self.rd(disp)[0])-value)<=3,10,True)

    def ai(self,ch,value,secondary=None):
        base=1229+12*ch
        second=value if secondary is None else secondary
        # A nonzero engineering span avoids equal-endpoint validation effects.
        self.config({base:1,base+4:value-1,base+5:value+1,
                     base+6:second-1,base+7:second+1,base+8:0})
        time.sleep(.6)

    def setup(self,mode=2,thermal=False):
        self.stop()
        for a,v in self.polarities.items():
            if a in self.touched:self.config({a:v})
        self.baseline(mode)
        self.config({30:0,42:3,43:3,320:0,323:5,324:5,325:0,
                     214:3,412:1,164:0,168:0,169:0})
        if thermal:
            self.config({125:1,126:1,127:1,128:2,129:1,332:1,333:0,
                         334:1,248:1,160:250,161:250,347:100,348:1,349:0,
                         353:100,354:1,355:0})
            self.ntc(0,220);self.ai(1,300)
        time.sleep(3.3);self.reset_faults()

    def start(self,special_ready=False):
        self.wr(398,1)
        if special_ready:
            mode=self.rd(236)[0]
            return self.wait('special actuators established',
                lambda s:s['state'][9]==2 and (s['do'][10]==1 if mode in (3,5)
                                              else s['do'][3]==1 and s['do'][8]==1),200)
        return self.wait('start step2',lambda s:s['state'][9]==2,50)

    def record(self,cid,status,actual,limitations,entry=None):
        assert cid in CASES,cid
        if entry is not None:self.log['cases'][cid]=entry
        self.save()
        result(cid,status,actual,self.path,limitations,
               'BENCH软件回读；正常协议参数/极性/工程映射刺激；不等同端子或物理输入')

    def finish(self):
        # Return fault inputs before requesting an ordinary stop.
        try:
            for a,v in self.polarities.items():
                if a in self.touched:self.c.write_single_register(1,a,v)
            time.sleep(3.3)
            self.reset_faults()
        finally:
            super().finish()


def case_error(b,cid,exc,limitations='原始异常与恢复留证；未自动修改固件'):
    entry=b.log['cases'].setdefault(cid,{})
    entry['error']=traceback.format_exc();entry['exception_type']=type(exc).__name__
    b.record(cid,'环境受限' if 'legal NTC calibration cannot reach' in str(exc) else '失败',
             str(exc)[-1400:],limitations,entry)
