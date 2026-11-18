"""User-requested persistent setting change through330, with two316 readback."""
import time
import traceback
import vfd_min30_fix_context_20261117 as ctx
from joint_precondition_20261110 import symbols

g=ctx.g


def main():
    path=ctx.DAY/('user_set_min30_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=g.now(),authorization='设置为30',address=1341,value=30,
           intentional_setting_change=True,restore_to_previous=False,boards=[])
    c=g.runtime.client()
    def rd(a,n=1):return c.read_holding_registers(1,a,n)
    try:
        q['versions']=rd(2622,18);assert q['versions']==g.runtime.EXPECTED
        q['snapshot_before']=g.runtime.snap(c)
        assert q['snapshot_before']['state'][9]==0 and g.loads_off(q['snapshot_before'])
        assert rd(398)==[0] and rd(1319)==[1]
        q['before']={str(a):rd(a)[0] for a in (1340,1341,1342,1842,1890)}
        g.dump(path,q)
        c.write_single_register(1,1341,30)
        deadline=time.monotonic()+75;stable=None
        while True:
            q['after']={str(a):rd(a)[0] for a in (1340,1341,1342,1842,1890)}
            if all(q['after'][str(a)]==30 for a in (1341,1842,1890)):
                if stable is None:stable=time.monotonic()
                if time.monotonic()-stable>=3:break
            else:stable=None
            assert time.monotonic()<deadline,q['after']
            time.sleep(.3)
        assert all(q['before'][str(a)]==q['after'][str(a)] for a in (1340,1342))
        for board in g.BOARDS:
            if board[0]=='330':continue
            sy=symbols(board)
            with g.ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
                t=ss.target;p=sy['Parameter'][0]
                row=dict(board=board[0],minimum_Hz=t.read16(p+2*177),maximum_Hz=t.read16(p+2*176),
                         output=list(t.read_memory_block8(*sy['output'])))
                assert row['minimum_Hz']==30
                assert not any(row['output'][i] for i in (0,1,2,3,4,5,7))
                q['boards'].append(row);g.dump(path,q)
        q.update(verified=True,finished=g.now(),note='Intentional new setting baseline:330[1341] and both316[177]=30. No reset/powercycle or terminal-voltage measurement performed.')
        g.dump(path,q);print('SETTING VERIFIED',q['after'],q['boards'],str(path),flush=True)
    except BaseException:
        q.update(error=traceback.format_exc(),finished=g.now());g.dump(path,q);raise
    finally:c.close()


if __name__=='__main__':main()
