"""Continue reviewed board procedures against the current, unchanged images."""
import sys
import joint_v1058_context_20261111 as context
from joint_v1058_context_20261111 import *

# Bind before importing helpers; their older selector must not change artifacts.
sys.modules['joint_v1056_context_20261110'] = context


class RecordingBench(current_bench_class()):
    def record_local(self, cid, passed, actual, entry):
        self.log.setdefault('current_records', {})[cid] = dict(
            passed=passed, detail=actual, current_versions=self.rd(2622,18))
        self.save()


def run(action):
    if action == 'parameters':
        import joint_v1056_parameter_matrix_20261110 as test
        test.CurrentBench = RecordingBench
        test.SHARED.update({176:1340,177:1341,178:1342})
        sys.argv = [sys.argv[0], '--settled']
        test.main()
    elif action == 'contacts':
        import bench_b01_contacts_20261111 as test
        test.run(recheck=True)
    elif action == 'manual-contacts':
        import bench_b01_contacts_20261111 as test
        test.run(recheck=True,manual=True)
    elif action == 'prestart':
        import joint_priority_20261110 as test
        test.TodayBench = RecordingBench
        test.fans(restart_observation=36,minimum_run=30)
    elif action == 'coils':
        import nonvent_coil_real_time_20261109 as test
        from nonvent_coil_process_input_20261109 import ProcessNtcInput
        test.CheckedBench = RecordingBench
        test.RawNtcInput = ProcessNtcInput
        test.RESULTS = DAY/'coil_case_results_continuation.json'
        dump(test.RESULTS,{f'T15-{i:03d}':{} for i in range(1,5)})
        test.run()
    elif action == 'winter':
        import nonvent_ntc_input_boundaries_20261109 as test
        test.CheckedBench = RecordingBench
        test.RESULTS = DAY/'winter_case_results_continuation.json'
        dump(test.RESULTS,{'T06-001':{},'T06-004':{}})
        test.winter()
    elif action.startswith('defrost-'):
        import nonvent_defrost_v1055_20261109 as test
        test.DefrostBench = RecordingBench
        test.RESULTS = DAY/'defrost_case_results_continuation.json'
        if not test.RESULTS.exists(): dump(test.RESULTS,{})
        test.run(action.removeprefix('defrost-'))
    else:
        raise ValueError(action)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('parameters','contacts','manual-contacts','prestart','coils','winter',
        'defrost-raw-hp1','defrost-recovery-stop','defrost-demand'))
    run(parser.parse_args().action)
