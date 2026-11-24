"""330-only V10.75 deployment: normal standby may correctly energize DA8."""
import copy
import build_da8_standby_v1075_20261124 as build
import deploy_da8_manual_v1074_20261124 as dep


def standby(s):
    # Every actuator except the water frost output must be off. Water expected
    # value is checked separately with live fresh/minimum/settings after boot.
    value=copy.deepcopy(s);value['914'][8]=0
    return dep.d.stopped(value)


def configure():
    dep.DAY=build.DAY;dep.OUT=build.OUT/'PRODUCTION'
    dep.NEW=dep.OUT/'PSC330_V10.75_PRODUCTION.hex'
    boards=list(dep.BOARDS)
    boards[2]=(*boards[2][:6],build.OLD/'PSC330_V10.74_PRODUCTION.hex')
    dep.BOARDS=tuple(boards)
    dep.PREVIOUS_EXPECTED=[330,10,74,2026,11,24]+dep.EXPECTED[6:]
    dep.EXPECTED=[330,10,75,2026,11,24]+dep.EXPECTED[6:]
    dep.ARM_REPORT='standby_ARM_regression.json'
    dep.AUTHORIZATION='要求低于0℃时停机也保持最低开度；修改、烧录并复测'
    dep.POSTBOOT_STOPPED=standby
    return dep


if __name__=='__main__':configure().main()
