"""Reuse previously reviewed indoor procedures with the exact current artifacts."""
from joint_v1058_context_20261111 import *


def run(action):
    bench=current_bench_class()
    if action=='coil':
        import joint_coil_continuity_20261110 as test
        test.TodayBench=bench
        test.run(False)
    elif action=='soak':
        import continuous_followups_v1055_20261109 as test
        test.D=DAY

        class SoakBench(bench):
            def record_local(self,cid,passed,actual,entry):
                entry['observed_current_artifacts']=self.rd(2622,18)
                entry['summary']=actual.replace('V10.55','V10.58')
                self.save()

        test.CheckedBench=SoakBench
        test.soak()
    else:
        import joint_indoor_followups_20261110 as test
        test.TodayBench=bench
        getattr(test,action)()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('refrigerant','da8','coil','soak'));run(parser.parse_args().action)
