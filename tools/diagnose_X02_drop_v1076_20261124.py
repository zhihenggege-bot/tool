"""Reproduce short X02 stop in unchanged V10.75 and V10.76 ARM images."""
import json
from pathlib import Path
from check_local_remote_arm_20261117 import fixture,snap
from build_di_faults_v1076_20261124 import OLD,OUT
from board_all_DI_v1076_20261124 import DAY


def main():
    rows=[]
    for version,path in (('10.75',OLD/'PSC330_V10.75_PRODUCTION.axf'),
                         ('10.76',OUT/'PRODUCTION/PSC330_V10.76_PRODUCTION.axf')):
        for polarity in (0,1):
            f=fixture(path,source=1)
            f.call('InputStartCheck');f.p(157,polarity)
            f.var('uc100ms',1);f.var('uc1s',0)
            f.var('input',polarity,index=2,width=1)
            for _ in range(32):f.call('DI_Points_Process');f.call('SwitchStatusProcess')
            assert f.p(398)==1
            f.p(709,2)
            before=snap(f)
            f.var('input',1-polarity,index=2,width=1)
            snapshots=[]
            for count in (1,2):
                f.call('DI_Points_Process');f.call('SwitchStatusProcess')
                snapshots.append(dict(tick100ms=count,state=snap(f),raw=f.var('X_02'),filtered=f.var('X02_En')))
            assert snapshots[-1]['state']['398']==0
            rows.append(dict(version=version,polarity=polarity,before=before,after=snapshots,
                stop_request_by_200ms=True))
    assert rows[0]['after']==rows[2]['after'] and rows[1]['after']==rows[3]['after']
    report=dict(passed=True,hardware_access=False,rows=rows,
        cause='DI_Points_Process qualifies assertion for3s but drops X02_En after deassertion without a3s off filter. SwitchStatusProcess consumes FarSwitchX02=X02_En and immediately clears the maintained remote run request. The separate BoardErrAction3s remote-interlock counter does not gate this direct stop path.',
        unchanged_from_previous_version=True,
        classification='Existing remote command behavior, not introduced by new DI960/962/964 or polarity inversion; original spec external-interlock3s differs, while later user requirement says remote X02 maintained on/off without specifying an off delay. Retain discrepancy; no firmware edit.')
    (DAY/'X02_ARM原因复核.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('X02 ARM ROOT CAUSE VERIFIED in V10.75 and V10.76, both polarities; direct stop without3s off qualification',flush=True)


if __name__=='__main__':main()
