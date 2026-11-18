"""Current-image adapters for additional queued input-only bench procedures."""
from joint_v1058_context_20261111 import *


def run(action):
    bench=current_bench_class()
    if action.startswith('dispatch'):
        import joint_outdoor_disable_20261110 as test
        pair=((0,0),(0,1),(1,2),(1,3),(2,2),(2,4))[int(action[-1])]
        class PairBench(bench):
            def __init__(self,name):
                super().__init__(name)
                assert self.rd(398)==self.rd(709)==[0]
                self.gateway(1830,pair[0]);self.gateway(1831,pair[1])
        test.TodayBench=PairBench
        test.run()
    elif action=='heatfans':
        import joint_outdoor_heatfans_20261110 as test
        test.TodayBench=bench
        test.run()
    elif action=='emergency':
        import joint_priority_20261110 as test
        test.TodayBench=bench
        test.emergency()
    elif action=='allocation':
        import joint_indoor_followups_20261110 as test
        test.TodayBench=bench
        test.allocation()
    elif action.startswith('contact'):
        import bench_b01_contacts_20261111 as test
        test.CONTACTS=[test.CONTACTS[int(action[-1])]]
        test.run()
    else:
        raise ValueError(action)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=tuple('dispatch'+str(n) for n in range(6))+tuple('contact'+str(n) for n in range(1,8))+('heatfans','emergency','allocation'))
    run(p.parse_args().action)
