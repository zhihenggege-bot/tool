"""Resume prior inconclusive coil tests with independent acquisition-input writer."""
from joint_priority_20261110 import TodayBench,DAY,now,dump
from nonvent_coil_process_input_20261109 import ProcessNtcInput
import nonvent_coil_real_time_20261109 as matrix

class CoilBench(TodayBench):
    def record_local(self,cid,passed,actual,entry):
        self.log.setdefault('today_case_records',{})[cid]=dict(status='软件子范围通过' if passed else '失败',actual=actual,evidence=entry)
        self.save()

def main():
    matrix.CheckedBench=CoilBench
    matrix.RawNtcInput=ProcessNtcInput
    # The older matrix writes its global result ledger after cleanup-sensitive
    # assertions. Route those aggregate writes to today's isolated ledger.
    matrix.RESULTS=DAY/'coil_case_results.json'
    dump(matrix.RESULTS,{f'T15-{i:03d}':{} for i in range(1,5)})
    matrix.run()

if __name__=='__main__':main()
