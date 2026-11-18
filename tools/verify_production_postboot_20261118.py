"""Read-only completion after the formal ambient-permission startup wait."""
import json
import time
import traceback

import deploy_production_v1064_v1246_20261118 as d


def main():
    path = d.D / 'postboot_verification.json'
    assert not path.exists(), 'Preserve previous verification evidence'
    original = json.loads(d.P.read_text('utf8'))
    result = dict(started=d.now(), passed=False, samples=[],
                  initial_deployment_error=original.get('error'))
    c = d.client()
    try:
        deadline = time.monotonic() + 40
        while True:
            snapshot = d.snap(c)
            result['samples'].append(dict(at=d.now(), snapshot=snapshot))
            # Alarm is expected while formal ambient permission is accumulating.
            # The final condition still requires it to clear without suppression.
            if (snapshot['2622'] == d.EXPECTED
                    and snapshot['1298'] == [300, 0]
                    and d.stopped(snapshot)
                    and not any(snapshot['594'])
                    and snapshot['700'][3] == 0):
                break
            assert time.monotonic() < deadline, 'Final stopped/alarm-clear verification timeout'
            time.sleep(2)
        result['config_after'] = d.config(c)
        result['changes'] = {
            a: [v, result['config_after'][a]]
            for a, v in original['config_before'].items()
            if result['config_after'][a] != v
        }
        allowed = {42, 43, 1298, 1299, 167, 373, 1875, 1923}
        assert all(int(a) in allowed for a in result['changes']), result['changes']
        assert snapshot['163'] == original['before']['163']
        assert snapshot['1352'] == [0] and snapshot['1388'] == [0]
        assert snapshot['1300'] == [0]
        assert result['config_after']['1341'] == original['config_before']['1341'] == 30
        assert result['config_after']['1319'] == original['config_before']['1319'] == 1
        direct = json.loads((d.D / 'direct_board_postboot.json').read_text('utf8'))
        assert len(direct['boards']) == 3
        for row in direct['boards']:
            assert row['runtime_profile'] == dict(recovery=300, profile=0,
                                                  minimum_stop=120, minimum_run=180)
        result['direct_board_verification'] = direct
        result['passed'] = True
    except BaseException:
        result['error'] = traceback.format_exc()
        raise
    finally:
        c.close()
        result['finished'] = d.now()
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
        print(json.dumps({k: v for k, v in result.items()
                          if k in ('passed', 'changes', 'error', 'finished')},
                         ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
