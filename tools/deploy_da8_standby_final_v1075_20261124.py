"""Deploy the final narrow compatibility correction after the preliminary trial."""
import build_da8_standby_v1075_20261124 as build
import deploy_da8_standby_v1075_20261124 as deploy


def main():
    dep=deploy.configure()
    dep.PREVIOUS_EXPECTED=dep.EXPECTED[:]
    dep.PREBOOT_STOPPED=deploy.standby
    dep.DEPLOYMENT_RECORD='deployment_final.json'
    dep.BACKUP_STEM='330_before_final'
    boards=list(dep.BOARDS)
    boards[2]=(*boards[2][:6],build.OUT/'initial_board_build/PSC330_V10.75_PRODUCTION.hex')
    dep.BOARDS=tuple(boards)
    dep.main()


if __name__=='__main__':main()
