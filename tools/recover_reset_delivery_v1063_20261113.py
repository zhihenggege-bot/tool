"""Resume an interrupted 330 upgrade; preserve the original failure journal."""
import json
import time
import traceback
import manual_delivery_fix_context_20261113 as ctx
import deploy_reset_retrigger_v1062_20261113 as deploy
from deploy_manual_gate_v1244_20261113 import verify
from pyocd.flash.file_programmer import FileProgrammer

g = ctx.g
deploy.ctx = ctx
deploy.g = g


def main():
    original = ctx.DAY / 'deployment.json'
    prior = json.loads(original.read_text('utf8'))
    assert not prior.get('verified'), 'Upgrade already complete; use the audit action.'
    manifest = json.loads((ctx.I / 'manifest.json').read_text('utf8'))
    assert all(g.runtime.sha(ctx.R / n) == v for n, v in manifest['source_inventory'].items())
    assert all(g.runtime.sha(ctx.I / n) == v for n, v in manifest['artifacts'].items())
    arm = json.loads((ctx.I.parent / 'reset_delivery_ARM_regression.json').read_text('utf8'))
    assert all(r['passed'] for r in arm)
    old330 = next(r for r in prior['boards'] if r['board'] == '330')
    for name in ('flash_backup', 'sram_backup'):
        backup = old330[name]
        assert g.runtime.sha(ctx.DAY / backup['path']) == backup['sha256']
    path = ctx.DAY / ('deployment_recovery_' + time.strftime('%Y%m%d_%H%M%S') + '.json')
    q = dict(started=g.now(), recovery_source=original.name,
             config_before=prior['config_before'], boards=[],
             source_inventory=manifest['source_inventory'], artifacts=manifest['artifacts'])
    g.dump(path, q)
    try:
        # The failed image cannot provide a trustworthy protocol/version preflight.
        # Verify the two unchanged boards and physical MCU identity before recovery.
        for board in g.BOARDS:
            label, uid, target, device, flash_size, ram_size, stem = board
            row = dict(board=label, programmed=False)
            q['boards'].append(row)
            with g.ConnectHelper.session_with_chosen_probe(
                unique_id=uid, target_override=target,
                options={'connect_mode': 'halt' if label == '330' else 'attach',
                         'resume_on_disconnect': label != '330', 'frequency': 500000}) as ss:
                t = ss.target
                assert t.read32(0xE0042000) & 0xfff == device
                if label == '330':
                    t.halt()
                    debug = t.read32(0xE0042008)
                    try:
                        t.write32(0xE0042008, debug | 0x1800)
                        t.reset_and_halt()
                        t.write32(0xE0042008, t.read32(0xE0042008) | 0x1800)
                        row['programming_started'] = True
                        g.dump(path, q)
                        FileProgrammer(ss, chip_erase='sector', trust_crc=False).program(str(ctx.I / (stem + '.hex')))
                        row['programmed'] = True
                        row['verified_bytes'] = verify(t, ctx.I / (stem + '.hex'))
                        row['flash_verified'] = True
                        t.write32(0xE0042008, debug)
                        t.reset()
                    except BaseException:
                        # Do not resume or reset a partially programmed image.
                        row['recovery_required'] = True
                        raise
                else:
                    row['verified_bytes'] = verify(t, ctx.I / (stem + '.hex'))
                    row['flash_verified'] = True
                g.dump(path, q)
        deploy.finalize(path, q)
    except BaseException:
        q.update(error=traceback.format_exc(), finished=g.now())
        g.dump(path, q)
        raise


if __name__ == '__main__':
    main()
