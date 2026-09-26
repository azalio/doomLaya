"""Проверка артефактов настоящего E2E: игра → Laya → действия → видео."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import struct
import vizdoom
import sys

from tools.check_navigation import analyze
from tools.check_behavior import analyze as analyze_behavior
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()


def verify(root, expected_seconds=None):
    root = Path(root).resolve()
    def read(name):
        return json.loads((root / name).read_text())
    def rows(name):
        return [json.loads(line) for line in (root / name).read_text().splitlines()]
    summary, config = read('summary.json'), read('config.json')
    if config.get('protocol')=='model-authority-v1':
        from diagnostics.verify_model_run import verify as verify_model
        result=verify_model(root)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['passed'] else 1
    decisions, telemetry = rows('decisions.jsonl'), rows('telemetry.jsonl')
    events=rows('events.jsonl')
    if expected_seconds is None:expected_seconds=summary['game_seconds']
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
    model = config['args']['model']
    check(not config['args']['dry'] and summary['model'] == model, 'Run must use a real model')
    check(summary['status'] == 'completed' and summary['error'] is None, 'Run must complete')
    check(summary['errors'] == 0, 'Model API errors must be zero')
    check(math.isclose(summary['game_seconds'], expected_seconds, abs_tol=.03), 'Unexpected game duration')
    check(len(telemetry) == round(expected_seconds*35), 'Missing game ticks')
    check([r['tick'] for r in telemetry] == list(range(len(telemetry))), 'Non-contiguous game ticks')
    check(len(decisions) == summary['decisions'] and len(decisions) > 0, 'Decision count mismatch')
    check(any(d['reason'] in ('same', 'margin', 'danger', 'max_hold') for d in decisions), 'No model decisions controlled the game')
    check(all(d['routing']['model'] == model and d['tokens'] > 0 for d in decisions), 'Missing real inference evidence')
    check(sum(d['tokens'] for d in decisions) == summary['input_tokens_total'], 'Token count mismatch')
    tactics = set(config['questions']['tactic']['criteria'])
    for d in decisions:
        probs = d['probabilities']
        check(set(probs) == tactics and all(math.isfinite(p) and 0 <= p <= 1 for p in probs.values())
              and math.isclose(sum(probs.values()), 1, abs_tol=.002), 'Invalid probability table')
        if d['applied']:
            tick = d['tick']
            applied_tick = round(d['game_seconds']*35)
            matches = [r for r in telemetry[max(0,applied_tick-1):applied_tick+2]
                       if r['tactic'] == d['choice'] and r['episode'] == d['episode']]
            check(bool(matches), f'Model action not found in telemetry near tick {tick}')
    check(dict(Counter(r['tactic'] for r in telemetry)) == summary['action_ticks'], 'Action distribution mismatch')
    for name, digest in config['source_sha256'].items():
        check(hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() == digest,
              f'Current source differs from run: {name}')
    completions=[e for e in events if e['event']=='level_finished']
    starts=[e for e in events if e['event']=='episode_started']
    check(bool(completions), 'The player did not finish a level')
    check(not config['args']['give'], 'Acceptance must not use granted items')
    check(summary['game_seconds']<=config['args']['seconds']+.03, 'Game exceeded time budget')
    for completion in completions:
        check(completion.get('alive') and completion.get('engine_finished'), 'Missing engine completion proof')
        after=next((e for e in starts if e['game_seconds']==completion['game_seconds']),None)
        next_map=f"MAP{int(completion['map'][3:])+1:02d}"
        check(after and after['map']==next_map and after['engine_map'].upper()==next_map, 'Next map did not start')
        played=[r for r in telemetry if r.get('map')==next_map]
        check(len(played)>=105, 'Next level was not played for three seconds')
        check(bool(played) and played[0]['engine_tic']<100, 'Next map did not reset engine time')
        if after and played:
            check(math.dist((after['x'],after['y']),(played[0]['x'],played[0]['y']))<1, 'Spawn telemetry mismatch')
            wad=(Path(vizdoom.__file__).parent/'freedoom2.wad').read_bytes()
            count,offset=struct.unpack_from('<ii',wad,4)
            directory=[struct.unpack_from('<ii8s',wad,offset+i*16) for i in range(count)]
            index=next(i for i,(_,_,name) in enumerate(directory) if name.rstrip(b'\0').decode()==next_map)
            pos,size,_=next(e for e in directory[index+1:index+11] if e[2].rstrip(b'\0')==b'THINGS')
            spawn=next(t for t in struct.iter_unpack('<hhhhh',wad[pos:pos+size]) if t[3]==1)
            check(math.dist((after['x'],after['y']),spawn[:2])<1, 'Spawn does not match next map WAD')
    check(summary.get('levels_completed')==len(completions), 'Level counter mismatch')
    video = root / 'video.mp4'
    check(video.is_file(), 'Video is missing')
    info = {}
    if video.is_file():
        info = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name,width,height,nb_frames,r_frame_rate',
            '-show_entries', 'format=duration,size', '-of', 'json', str(video)], text=True))
        stream = info['streams'][0]
        check((stream['width'], stream['height'], stream['r_frame_rate']) == (1920,1080,'35/1'), 'Wrong video format')
        check(int(stream['nb_frames']) == len(telemetry) == summary['video_frames'], 'Video frame count mismatch')
        check(math.isclose(float(info['format']['duration']), expected_seconds, abs_tol=.05), 'Wrong video duration')
    check((root / 'report.html').is_file(), 'HTML report is missing')
    navigation = analyze(telemetry)
    check(navigation['max_stationary_seconds'] <= 4, 'Patrol remained stationary too long')
    check(navigation['max_no_new_cell_seconds'] <= 25, 'Patrol repeated explored territory too long')
    check(navigation['max_no_new_region_seconds'] <= 25, 'Patrol repeated the same large regions too long')
    check(navigation['max_stationary_turn_reversals_per_second']<=5, 'Rapid alternating turns without movement')
    behavior=analyze_behavior(telemetry)
    for field in ('aim_overridden_ticks','abandoned_visible_target_ticks','useless_pickup_target_ticks'):
        check(behavior[field]==0, field)
    check(behavior['max_upgrade_delay_seconds']<=1.5, 'Better weapon remained unused')
    check(behavior['actual_hits']>0, 'No actual hits')
    check(behavior['strong_weapon_attack_ticks']>0, 'No attacks with a stronger weapon')
    check(bool(behavior['resource_gains']), 'No useful resource pickups')
    check(all(b.get('engine_tic', 0) > a.get('engine_tic', -1) for a,b in zip(telemetry, telemetry[1:])
              if a['episode'] == b['episode']), 'Engine stopped advancing')
    result = {'passed': not errors, 'errors': errors, 'run': str(root), 'model': model,
              'decisions': len(decisions), 'model_choice_counts': dict(Counter(d['choice'] for d in decisions)),
              'applied_switches': sum(d['applied'] for d in decisions), 'telemetry_ticks': len(telemetry),
              'video': info, 'navigation': navigation, 'behavior': behavior,
              'level_completions':completions, 'final_map':summary.get('final_map')}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run')
    parser.add_argument('--seconds', type=float)
    args = parser.parse_args()
    sys.exit(verify(args.run, args.seconds))
