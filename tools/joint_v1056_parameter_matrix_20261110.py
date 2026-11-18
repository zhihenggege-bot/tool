"""Stopped-board parameter acceptance, using normal 330 protocol only.

No demand, output, timer, state or firmware writes. Preserve shared sources as
well as the outdoor gateway values. A protocol exception alone is not a pass.
"""
from joint_v1056_context_20261110 import *
CurrentBench = current_bench_class()

# Parameter, default, minimum, maximum: user outdoor specification 4.1..4.5.
PLAN = [(170,150,150,250),(171,180,50,200),(172,300,200,350),
        (173,150,100,200),(174,70,50,100),(175,50,30,80),
        (176,50,30,50),(177,5,0,30),(178,10,1,20),
        (179,30,10,300),(180,30,10,300),(181,60,0,300),
        (182,100,50,150),(183,30,20,50),(184,4,2,8),
        (185,10,5,30),(186,-20,-40,-10),(187,100,50,150),
        (188,30,15,60),(189,35,15,70),(190,400,300,600),
        (191,4,2,8),(192,3,2,8),(193,30,20,120)]
SHARED = {**{a:1331+a-170 for a in range(170,176)},
          **{a:1337+a-179 for a in range(179,182)},
          **{a:1389+a-182 for a in range(182,193)},193:41}


def main():
    settled='--settled' in sys.argv[1:]
    b=CurrentBench('outdoor24_settled_parameter_boundaries' if settled else 'outdoor24_gateway_parameter_boundaries')
    e=dict(started=now(),status='running',cases=[],
           scope='Stopped boards: initialized parameter tables and normal 330 protocol/gateway boundary writes. First-boot EEPROM default and use in operating algorithms remain separate.')
    e['wait_for_full_propagation']=settled
    b.log['parameter_matrix']=e;b.save()
    try:
        s=b.snapshot('stopped before parameter matrix')
        assert s['state'][9]==0 and loads_off(s)
        for index,(p,default,low,high) in enumerate(PLAN,1):
            gateway=1830+p-165;shared=SHARED.get(p)
            b.gateway_original.setdefault(gateway,b.rd(gateway)[0])
            r=dict(id=f'O-PARAM-{index:03d}',parameter=p,gateway=gateway,
                   shared_source=shared,expected=[default,low,high],points=[])
            e['cases'].append(r)
            r['initialized_table']=[signed16(b.ot.read16(b.outsy[n][0]+2*p))
                for n in ('Parameter_def','Parameter_min','Parameter_max')]
            r['table_matches_spec']=r['initialized_table']==r['expected']
            for value in dict.fromkeys((low,default,high,low-1,high+1)):
                point=dict(requested=value,legal=low<=value<=high,
                           started=now(),samples=[],protocol_errors=[])
                r['points'].append(point);b.save()
                if shared is not None:
                    # Save the source before writing, including rejected writes.
                    if shared not in b.touched:
                        b.original[str(shared)]=b.rd(shared)[0];b.touched.add(shared)
                    try:b.c.write_single_register(1,shared,value&65535)
                    except Exception as ex:point['protocol_errors'].append(dict(path='shared',error=repr(ex)))
                began=time.monotonic()
                while b.rd(1873)[0]==1:
                    assert time.monotonic()-began<45,'gateway never became idle';time.sleep(.2)
                if shared is None or not settled:
                    try:b.c.write_single_register(1,gateway,value&65535)
                    except Exception as ex:point['protocol_errors'].append(dict(path='gateway',error=repr(ex)))
                began=time.monotonic();matched_since=None
                while True:
                    z=dict(at=now(),elapsed=time.monotonic()-began,
                           mirror=signed16(b.rd(gateway)[0]),
                           destination=signed16(b.ot.read16(b.outsy['Parameter'][0]+2*p)),
                           diagnosis=b.rd(1872,6))
                    if shared is not None:z['source']=signed16(b.rd(shared)[0])
                    point['samples'].append(z)
                    good=(z['destination']==z['mirror']==value and (shared is None or z['source']==value)) if point['legal'] else (low<=z['destination']<=high and low<=z['mirror']<=high)
                    if good:
                        if matched_since is None:matched_since=z['elapsed']
                    else:matched_since=None
                    if settled:
                        if matched_since is not None and z['elapsed']-matched_since>=3:break
                    elif z['elapsed']>=4 and z['diagnosis'][1]!=1:break
                    assert z['elapsed']<60,('boundary write did not settle',p,value,z)
                    time.sleep(.35)
                stable=[x for x in point['samples'] if x['elapsed']>=(matched_since if settled else 2)]
                point['accepted_safely']=(all(x['destination']==value and x['mirror']==value for x in stable)
                    if point['legal'] else all(low<=x['destination']<=high and low<=x['mirror']<=high for x in stable))
                b.save()
            r['software_scope_passed']=r['table_matches_spec'] and all(x['accepted_safely'] for x in r['points'])
            print('PARAMETER MATRIX',p,'PASS' if r['software_scope_passed'] else 'OBSERVATION REQUIRES REVIEW',flush=True)
        e['status']='completed_see_each_parameter';b.save()
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            # Restore sources before gateway helpers, preventing broadcasts
            # from undoing a gateway restoration in the middle of cleanup.
            for a in sorted(set(SHARED.values())&b.touched):
                b.c.write_single_register(1,a,b.original[str(a)])
            time.sleep(2)
            b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':main()
