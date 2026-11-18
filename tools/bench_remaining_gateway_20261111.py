"""Stopped-board gateway contention; one HMI writer, no control-state writes."""
from joint_v1058_context_20261111 import *


def run():
    b=current_bench_class()('remaining_gateway_busy')
    e=b.log['remaining_functional']=dict(kind='gateway_contention',cases=[],
        scope='Normal330 HMI writes while stopped; both316 settings, mirrors and error3 read back; physical serial waveform separate')
    originals={a:b.rd(a)[0] for a in (1832,1880)}
    b.attach_extra()
    targets={1832:(b.ot,b.outsy),1880:(b.extra[0][1].target,b.extra[0][2])}

    def actual(address):
        t,sy=targets[address]
        return t.read16(sy['Parameter'][0]+2*167)

    def state():
        return dict(at=now(),t=time.monotonic(),
            active=b.extra[1][1].target.read8(b.sy['PSC316WriteJob'][0]),
            diagnosis=[b.rd(1872,6),b.rd(1920,6)],
            destinations={str(a):actual(a) for a in originals},
            mirrors={str(a):b.rd(a)[0] for a in originals})

    def idle():
        end=time.monotonic()+70
        while True:
            s=state()
            if not s['active']:return s
            assert time.monotonic()<end,('gateway did not finish',s)
            time.sleep(.2)

    def settled_write(address,value):
        idle()
        if actual(address)==b.rd(address)[0]==value:return
        b.c.write_single_register(1,address,value)
        end=time.monotonic()+70
        while True:
            s=state()
            if not s['active'] and actual(address)==b.rd(address)[0]==value:return s
            assert time.monotonic()<end,('setting did not settle',address,value,s)
            time.sleep(.2)

    try:
        assert b.rd(398)==[0] and b.rd(709)==[0] and loads_off(b.snapshot('stopped gateway contention'))
        for label,second in (('different_unit',1880),('same_parameter_repeat',1832)):
            for a in originals:settled_write(a,0)
            row=dict(id='O-LINK-003',label=label,samples=[])
            e['cases'].append(row);b.save()
            b.c.write_single_register(1,1832,1)
            row['before_second']=state()
            try:
                b.c.write_single_register(1,second,1)
                row['second_protocol_response']='normal response'
            except Exception as exc:row['second_protocol_response']=repr(exc)
            row['immediate_after_second']=state()
            end=time.monotonic()+70
            while True:
                s=state();row['samples'].append(s)
                if not s['active']:break
                assert time.monotonic()<end,'contention job timeout'
                time.sleep(.2)
            diag=row['immediate_after_second']['diagnosis'][int(second==1880)]
            # Record failure to establish contention separately from device behavior.
            row['contention_established']=bool(row['before_second']['active'])
            row['busy_visible']=diag[1:3]==[3,3]
            if second==1832:
                # Current single-register API coalesces an identical pending
                # command; it need not report a busy error for the same value.
                row['identical_request_coalesced']=diag[1] in (1,2) and diag[2]==0
            row['first_destination_verified']=actual(1832)==b.rd(1832)[0]==1
            row['rejected_second_unchanged']=(actual(1880)==b.rd(1880)[0]==0) if second==1880 else True
            settled_write(second,1)
            row['retry_after_idle_verified']=actual(second)==b.rd(second)[0]==1
            row.update(final=state(),finished=now())
            if row['contention_established']:
                row['passed']=bool(row['busy_visible'] if second==1880 else row.get('identical_request_coalesced')) and all(
                    row[k] for k in ('first_destination_verified','rejected_second_unchanged','retry_after_idle_verified'))
            b.save();print('GATEWAY BUSY',label,row.get('passed','precondition not established'),flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            for a,v in originals.items():settled_write(a,v)
            e['restored_destinations']={str(a):actual(a) for a in originals}
            assert all(actual(a)==b.rd(a)[0]==v for a,v in originals.items())
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
