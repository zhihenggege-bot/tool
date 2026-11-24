"""Authorized 330-only DI diagnostic firmware programming and full readback."""
import build_di_faults_v1076_20261124 as build
import deploy_da8_manual_v1074_20261124 as dep
from deploy_da8_standby_v1075_20261124 import standby


def configure():
    dep.DAY=build.DAY
    dep.OUT=build.OUT/'PRODUCTION'
    dep.NEW=dep.OUT/'PSC330_V10.76_PRODUCTION.hex'
    boards=list(dep.BOARDS)
    boards[2]=(*boards[2][:6],build.OLD/'PSC330_V10.75_PRODUCTION.hex')
    dep.BOARDS=tuple(boards)
    dep.PREVIOUS_EXPECTED=[330,10,75,2026,11,24]+dep.EXPECTED[6:]
    dep.EXPECTED=[330,10,76,2026,11,24]+dep.EXPECTED[6:]
    dep.ARM_REPORT='DI_ARM_regression.json'
    dep.AUTHORIZATION='用户明确要求：烧录测试；330 DI独立故障960/962/964'
    dep.POSTBOOT_STOPPED=standby
    dep.PREBOOT_STOPPED=standby
    return dep


if __name__=='__main__':configure().main()
