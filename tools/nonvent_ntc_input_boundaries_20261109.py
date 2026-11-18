"""NTC ADC/filter INPUT simulation on the live BENCH, never output forcing.

Only ADbuffer, NTC_AD and NTC_Val_Filter of selected channels are written.
Sensor conversion, PID, output routing, protection and real time run normally.
"""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,paused
import threading,struct,math


class RawNtcInput:
    def __init__(self,b):
        self.b=b;self.values={};self.extra_inputs={};self.error=None;self.lock=threading.Lock();self.stop_event=threading.Event()
        self.ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        self.ss.open();self.t=self.ss.target;self.sy=b.sy
        self.table=list(struct.unpack('<201f',bytes(self.t.read_memory_block8(self.sy['NTCtable'][0],804))))
        self.stride=self.sy['NTC_Val_Filter'][1]//12
        assert self.stride==40,self.stride
        b.log['raw_ntc_input_fixture']=dict(symbols={k:self.sy[k] for k in ('ADbuffer','NTC_AD','NTC_Val_Filter','NTCtable')},
            scope='ADC acquisition/filter INPUT values only; no computed NTC/AI/diagnostic/PID/output/timer writes',events=[])
        b.save();self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()

    def set(self,ch,temp10):
        assert 0<=ch<12 and -400<=temp10<=1000
        i=int(math.floor(temp10/10))+50;f=temp10/10-(i-50)
        resistance=self.table[i]+f*(self.table[i+1]-self.table[i])
        raw=round((2.048*resistance/(5.1+resistance))/0.0000625)
        assert 5<raw<32760
        with self.lock:self.values[ch]=raw
        self.b.log['raw_ntc_input_fixture']['events'].append(dict(at=now(),channel=ch,requested_temp10=temp10,adc=raw))
        self.b.save();return raw

    def loop(self):
        try:
            while not self.stop_event.is_set():
                with self.lock:values=dict(self.values);extra=dict(self.extra_inputs)
                for ch,v in values.items():
                    self.t.write16(self.sy['ADbuffer'][0]+ch*2,v)
                    self.t.write_memory_block8(self.sy['NTC_Val_Filter'][0]+ch*self.stride,list(struct.pack('<20H',*([v]*20))))
                    self.t.write16(self.sy['NTC_AD'][0]+ch*2,v)
                for address,value in extra.items():
                    self.t.write_memory_block8(address,list(value))
                self.t.flush();self.stop_event.wait(.012)
        except BaseException:self.error=traceback.format_exc()

    def close(self):
        self.stop_event.set();self.thread.join(5)
        assert not self.thread.is_alive(),'ADC fixture did not stop'
        self.ss.close();self.b.log['raw_ntc_input_fixture']['stopped']=now()
        self.b.log['raw_ntc_input_fixture']['error']=self.error;self.b.save()
        assert not self.error,self.error


def base(b):
    b.setup(1);b.config({128:2,127:0,332:0,333:1,334:0,125:0,126:0,248:0,
        160:250,161:250,120:20,412:1,347:1,348:1000,349:0,
        374:0,356:-100,357:-200,346:200,315:0,320:0,245:1,247:0,
        329:2,330:0,331:0,493:0})
    b.temperature(0,250);b.reset_faults()


def winter():
    b=CheckedBench('winter_zero_demand_adc_inputs');fixture=None
    e=dict(passed=False,phases=[],scope='Accepted current electric minimum, not steam/water medium acceptance; ADC INPUT simulation; software AO/DO only')
    for cid in ('T06-001','T06-004'):b.log['cases'][cid]=e
    b.save()
    try:
        base(b);fixture=RawNtcInput(b);fixture.set(2,1)
        b.wait('fresh raw input at +0.1C',lambda s:signed16(b.rd(512)[0])==1,8)
        b.start()
        for temp in (1,0,-1,-10,1):
            # Each boundary starts from genuinely reset heat/preheat demand.
            # At neutral room temperature the specified PID Z=0 retains a
            # previous demand; warming fresh air alone need not erase it.
            # The first attempt incorrectly assumed that it must erase it;
            # that failed trace remains preserved, not called firmware failure.
            paused();b.config({128:0,333:0});time.sleep(.3);fixture.set(2,temp)
            b.wait('fresh ADC conversion '+str(temp),lambda s:signed16(b.rd(512)[0])==temp,8)
            b.config({128:2,333:1})
            want=200 if temp<0 else 0
            b.wait('winter AO settle '+str(temp),lambda s:s['ao'][0]==s['ao'][1]==want,8)
            p=dict(temp10=temp,wanted=want,samples=[]);e['phases'].append(p);began=time.monotonic()
            while time.monotonic()-began<4:
                paused();s=b.snapshot('winter minimum hold');s.update(fresh=signed16(b.rd(512)[0]),demands=b.rd(890,2),raw=b.rd(1376)[0]);p['samples'].append(s)
                assert s['fresh']==temp and s['ao'][0]==s['ao'][1]==want and s['demands']==[want,want] and not any(s['faults']),s
                time.sleep(.15)
            p['passed']=True;b.save();print('WINTER ZERO DEMAND',temp,'PASS',want,flush=True)
        fixture.set(2,-10);b.wait('winter negative before normal stop',lambda s:s['ao'][0]==s['ao'][1]==200,8)
        e['normal_stop']=b.stop();assert loads_off(e['normal_stop'])
        e['stopped_hold']=b.observe('negative fresh must not reopen after stop',4)
        assert all(loads_off(s) and s['state'][9]==0 for s in e['stopped_hold'])
        e['passed']=True;b.save()
        for cid in ('T06-001','T06-004'):
            b.record_local(cid,True,'V10.55新风NTC2原始ADC/滤波INPUT模拟+0.1/0/-0.1/-1/+0.1℃；每点正常禁用/重启主热预热清历史，主热室温等于WD25、预热端点临时设-10/-20℃使初始需求为零，[346]=200。负新风时DA0/DA1及显示需求均200，0℃及以上均0，各保持4s；负温下正常停机后保持4s无重开。首轮未清历史时暖回+0.1℃主热保留200，符合中性室温PID保持，不能据此要求强制归零。按用户接受的电热现状记录，非规格水/汽阀独立介质验收；未写需求/PID/输出/计时。',e)
        data=json.loads(RESULTS.read_text('utf8'))
        for cid in ('T06-001','T06-004'):data[cid]['inputs']='NTC2 ADC acquisition/filter INPUT simulation; normal configuration; no output forcing'
        dump(RESULTS,data)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:
        try:
            b.stop()
            if fixture:fixture.close();time.sleep(2)
        finally:b.finish()


def exact_boundaries():
    b=CheckedBench('heat_preheat_exact_adc_boundaries');fixture=None
    e=dict(passed=False,runs=[],scope='Raw NTC ADC/filter input simulation; downstream real conversion and controller, no terminal qualification')
    try:
        base(b);b.config({346:0,356:0,357:-50,493:0,495:0,347:1,348:1000})
        fixture=RawNtcInput(b);fixture.set(0,250);fixture.set(2,1)
        b.wait('ADC room25 fresh0.1',lambda s:signed16(b.rd(511)[0])==250 and signed16(b.rd(512)[0])==1,10)
        b.start()
        for temp,want,cid in ((-49,980,'T11-075'),(-50,1000,'T11-076'),(-51,1000,'T11-077')):
            r=dict(passed=False,fresh_temp10=temp,expected_demand=want,samples=[]);e['runs'].append(r);b.log['cases'][cid]=r;b.save()
            fixture.set(2,temp)
            b.wait('default preheat endpoint '+str(temp),lambda s:signed16(b.rd(512)[0])==temp and s['ao'][1]==want,10)
            began=time.monotonic()
            while time.monotonic()-began<4:
                paused();s=b.snapshot('default preheat endpoint hold');s.update(fresh=signed16(b.rd(512)[0]),demands=b.rd(890,2));r['samples'].append(s)
                assert s['fresh']==temp and s['demands'][1]==s['ao'][1]==want and not any(s['faults']),s
                time.sleep(.15)
            r['passed']=True;b.record_local(cid,True,f'V10.55预热默认开启0℃/满载-5℃，NTC2原始ADC/滤波INPUT模拟新风{temp/10:g}℃，真实转换显示精确一致，需求与DA1={want}连续4s；主热中性室温25℃，未写PID/需求/AO；非物理温度源和端子。',r)
        b.stop();b.setup(1)
        b.config({128:2,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:10,347:1,348:1000,349:0,
            346:0,315:0,320:0,245:1,247:0,329:2,330:0,331:0,495:0})
        fixture.set(2,1);fixture.set(0,250)
        b.wait('room neutral resets heat before strict WD boundary',lambda s:signed16(b.rd(511)[0])==250,10)
        b.start()
        # Ten-second PID period keeps the equal/above-boundary observations
        # inside the two-history startup window, instead of conflating a
        # normal integrated rise with the strict instantaneous force-on rule.
        for temp,forced,cid in ((126,False,'T11-066'),(125,False,'T11-065'),(124,True,'T11-064')):
            b.config({128:0});time.sleep(.3);fixture.set(0,temp)
            b.wait('raw room exact strict WD boundary '+str(temp),lambda s:signed16(b.rd(511)[0])==temp,10)
            b.config({128:2});r=dict(passed=False,room_temp10=temp,force_expected=forced,samples=[]);b.log['cases'][cid]=r;b.save()
            b.wait('strict heat force settles '+str(temp),lambda s:s['ao'][0]==(1000 if forced else 0),8)
            began=time.monotonic()
            while time.monotonic()-began<3:
                paused();s=b.snapshot('strict WD half boundary hold');s.update(room=signed16(b.rd(511)[0]),heat=b.rd(890)[0]);r['samples'].append(s)
                assert s['room']==temp and s['heat']==s['ao'][0]==(1000 if forced else 0) and not any(s['faults']),s
                time.sleep(.1)
            r['passed']=True;b.record_local(cid,True,f'V10.55 WD25，NTC0原始ADC/滤波INPUT模拟室温{temp/10:g}℃，转换精确一致；每次正常禁用/重启主热清历史，PID周期10s的初始历史窗口内观察3s，需求/DA0='+('1000，满足严格<12.5℃强制全开。' if forced else '0，等于/高于12.5℃未提前强制全开。')+'后续正常PID积分不由本项否定；未写PID/需求/输出或计时。',r)
        e['passed']=True;b.log['boundary_summary']=e;b.save()
    except BaseException:b.log['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.stop()
            if fixture:fixture.close();time.sleep(2)
        finally:b.finish()


if __name__=='__main__':
    import sys
    exact_boundaries() if '--exact' in sys.argv else winter()
