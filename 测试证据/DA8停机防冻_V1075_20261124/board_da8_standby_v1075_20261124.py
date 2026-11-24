"""Production DA8 standby frost verification, raw NTC input and normal commands."""
import time
import traceback
import sys
import build_da8_standby_v1075_20261124 as build
import deploy_da8_standby_v1075_20261124 as deploy
import board_da8_manual_v1074_20261124 as base


class Bench(base.Bench):
    record_name='board_standby'

    def __init__(self):
        super().__init__()
        self.log['image_sha256']=base.d.sha(base.dep.NEW.with_suffix('.axf'))
        self.save()

    def stopped_snapshot(self,s):return deploy.standby(s)

    def capture(self,label):
        # UserAction clears a stopped load before the final frost guard restores
        # it in the same scan. Preserve every raw observation, but compare only
        # coherent DA/display/final/PWM tuples; never infer a PWM drop from a
        # single intermediate RAM value read at a different point in the scan.
        for attempt in range(16):
            z=super().capture(label)
            if z['display']==z['final']==z['da'][8] and z['pwm']==z['final']*98//100:
                z['coherent_water_attempts']=attempt+1
                return z
        raise AssertionError(('No coherent water output tuple',z))

    def normal_stop(self,label):
        row=self.row(label);row['command_t']=time.monotonic();self.wr(398,0)
        def expected(z):
            minimum=z['minimum'] if z['fresh10']<0 else 0
            return z['step']==0 and z['command']==0 and self.output(z,minimum) and \
                not any(v for i,v in enumerate(z['da']) if i!=8) and \
                not any(v for o in z['outdoor'] for v in o['gpio'])
        return self.wait(row,expected,timeout=200,hold=3)

    def standby_check(self,name,manual,minimum,fresh,mode):
        self.config({247:manual,346:minimum,236:mode});self.temperature(2,fresh)
        target=minimum if fresh<0 else 0
        row=self.row(name)
        row.update(expected=target,manual=manual,minimum=minimum,fresh10=fresh,mode=mode)
        return self.wait(row,lambda z:z['step']==0 and z['command']==0 and z['mode']==mode
            and z['fresh10']==fresh and self.output(z,target) and z['manual']==manual
            and all(z['da'][i]==0 for i in (0,1,9)),hold=4)


def configure():
    dep=deploy.configure()
    base.dep=dep;base.DAY=build.DAY
    return dep


def main():
    if sys.argv[1:]:Bench.record_name=sys.argv[1]
    configure();b=Bench()
    try:
        # Preserve the user's physical cold-air reading before any simulation.
        row=b.row('physical fresh air below0; stopped water minimum already active')
        b.wait(row,lambda z:z['step']==0 and z['fresh10']<0 and z['minimum']==200
            and b.output(z,200),hold=5)
        b.temperature(0,250);b.temperature(1,250)
        b.config({163:0,164:0,165:0,236:0,127:0,128:0,129:1,125:0,126:0,
            248:0,315:0,320:0,332:0,333:0,334:0,335:0,336:0,337:0,338:0,
            160:320,161:150})
        for args in (
            ('cold stopped manual0 still minimum200',0,200,-1,0),
            ('cold stopped manual1000 uses only minimum200',1000,200,-1,0),
            ('exact0 releases previously active minimum',1000,200,0,0),
            ('positive0.1 remains off while stopped',500,200,1,0),
            ('cold disabling minimum releases previous output',500,0,-1,0),
            ('cold stopped full minimum1000',0,1000,-1,0),
            ('cold stopped heating mode minimum300',500,300,-1,1),
            ('cold stopped ventilation mode minimum200',500,200,-1,2),
            ('ventilation exact0 releases minimum',500,200,0,2),
            ('cooling cold preparation minimum200',500,200,-1,0)):
            b.standby_check(*args)
        # Legacy mask does not suppress a probe required for standby frost.
        b.config({377:2})
        b.wr(398,1);row=b.row('normal cooling start: manual500 exceeds cold minimum200')
        b.wait(row,lambda z:z['step']==2 and z['mode']==0 and z['fresh10']==-1
            and b.output(z,500),timeout=150,hold=5)
        b.check('running manual0 keeps minimum200',0,200,-1,200,0)
        b.check('running exactly0 releases minimum',0,200,0,0,0)
        b.check('running manual500 remains500',500,200,-1,500,0)
        b.normal_stop('ordinary cold cooling shutdown ends with minimum200')
        with b.lock:b.raw[2]=32767
        row=b.row('standby required fresh probe failure closes water and alarms')
        row['raw_stimulus']=32767
        b.wait(row,lambda z:z['fresh10']==9999 and z['indoor_faults'][6]==1
            and z['sensor_partial_stop']==1 and b.output(z,0)
            and z['indoor_do'][5]==1,healthy=False,hold=4)
        b.temperature(2,-1)
        # Restore the valid acquisition before ordinary alarm reset.
        row=b.row('standby valid probe returns; normal reset restores frost minimum')
        b.wr(524,1);time.sleep(.3);b.wr(524,0)
        b.wait(row,lambda z:z['fresh10']==-1 and not any(z['indoor_faults'])
            and not z['sensor_partial_stop'] and b.output(z,200),healthy=False,hold=4)
        b.log['sequence_completed']=True;b.save()
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    b.log['passed']=all(r['passed'] for r in b.log['cases']) and b.log.get('restored',False)
    b.save();assert b.log['passed']
    print('BOARD STANDBY PASS',len(b.log['cases']),'checks; baseline restored',flush=True)


if __name__=='__main__':main()
