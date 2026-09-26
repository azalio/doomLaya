"""Регрессия навигации по реальной телеметрии: стены и повторение маршрута."""
import argparse
from collections import deque
import json
import math
from pathlib import Path
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()


def objective_progress(rows):
    """Detect repeated routes without mistaking a return to a selected goal for a loop."""
    seen=set();best={};doors=set();switches=set();old_episode=None;last=0;maximum=0;keys=()
    for row in rows:
        tick=row['tick']
        if row['episode']!=old_episode:
            seen.clear();best.clear();doors.clear();switches.clear();keys=();last=tick;old_episode=row['episode']
        cell=tuple(math.floor(row.get(axis,0)/64) for axis in ('x','y','z'))
        current_keys=tuple(sorted(row.get('keys',())))
        active={switch['id'] for switch in row.get('switches',()) if switch.get('activated')}
        opened=set(row.get('opened_doors',()))
        progress=(cell not in seen or current_keys!=keys or bool(active-switches) or bool(opened-doors)
                  or any(value>0 for value in row.get('resource',{}).get('gains',{}).values()))
        seen.add(cell);keys=current_keys;switches.update(active);doors.update(opened)
        execution=row.get('execution',{});nav=row.get('navigation',{})
        target=(execution.get('action'),execution.get('target_id'),keys)
        distance=nav.get('remaining_distance')
        if execution.get('action') in ('pickup','open_door','use_switch','exit') and execution.get('status')=='executing' and distance is not None:
            if target not in best:best[target]=distance
            elif distance<=best[target]-1:
                progress=True;best[target]=distance
        if progress or row['enemies']:last=tick
        elif not row['enemies']:maximum=max(maximum,(tick-last)/35)
    return round(maximum,2)


def analyze(rows):
    rows=list(rows)
    seen = set()
    regions = set()
    last_region = 0
    no_region = 0
    aim_conflicts = 0
    anchor = None
    anchor_tick = last_new = 0
    frozen = no_novelty = 0
    old_episode = None
    turn_window=deque(maxlen=35)
    max_jitter=0
    for row in rows:
        tick = row['tick']
        xy = (row['x'], row['y'])
        position = (*xy, row.get('z', 0))
        if row['episode'] != old_episode:
            anchor, anchor_tick, last_new = position, tick, tick
            seen.clear()
            regions.clear()
            last_region = tick
            old_episode = row['episode']
            turn_window.clear()
        region = (math.floor(xy[0]/256), math.floor(xy[1]/256), math.floor(position[2]/64))
        if region not in regions:
            regions.add(region)
            last_region = tick
        cell = (math.floor(xy[0]/64), math.floor(xy[1]/64), math.floor(position[2]/64))
        if cell not in seen:
            seen.add(cell)
            last_new = tick
        if math.dist(position, anchor) >= 32:
            anchor, anchor_tick = position, tick
        if not row['enemies']:
            frozen = max(frozen, (tick-anchor_tick)/35)
            no_novelty = max(no_novelty, (tick-last_new)/35)
            no_region = max(no_region, (tick-last_region)/35)
            turn_window.append((position,row['buttons'][4]))
            if len(turn_window)==35 and all(math.dist(point,position)<32 for point,_ in turn_window):
                signs=[1 if turn>0 else -1 for _,turn in turn_window if abs(turn)>2]
                max_jitter=max(max_jitter,sum(a!=b for a,b in zip(signs,signs[1:])))
        else:
            # Combat time does not become navigation inactivity when an enemy disappears.
            anchor,anchor_tick=position,tick
            last_new=last_region=tick
            turn_window.clear()
        if row['enemies'] and row['ammo'] > 0:
            target = min(row['enemies'], key=lambda e: abs(e['bearing']))
            turn = max(-9, min(9, target['bearing']))
            if 'combat' not in row and abs(row['buttons'][4]-turn) > 5:
                aim_conflicts += 1
    return {'max_no_objective_progress_seconds':objective_progress(rows),
            'max_stationary_seconds': round(frozen, 2),
            'max_stationary_turn_reversals_per_second':max_jitter,
            'max_no_new_cell_seconds': round(no_novelty, 2),
            'max_no_new_region_seconds': round(no_region, 2),
            'aim_overridden_ticks': aim_conflicts, 'unique_cells_last_episode': len(seen)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run')
    parser.add_argument('--max-stationary', type=float, default=4)
    parser.add_argument('--max-no-novelty', type=float, default=25)
    args = parser.parse_args()
    rows = [json.loads(line) for line in (Path(args.run)/'telemetry.jsonl').read_text().splitlines()]
    metrics = analyze(rows)
    errors = []
    if metrics['max_stationary_seconds'] > args.max_stationary:
        errors.append('Player stayed within 32 map units too long during patrol')
    if metrics['max_no_new_cell_seconds'] > args.max_no_novelty:
        errors.append('Patrol revisited old territory too long without discovering a new 64-unit cell')
    if metrics['max_no_new_region_seconds'] > 25:
        errors.append('Patrol repeated the same 256-unit regions for over 25 seconds')
    if metrics['max_stationary_turn_reversals_per_second']>5:
        errors.append('Rapid alternating turns without movement')
    result = {'passed': not errors, 'errors': errors, **metrics}
    print(json.dumps(result, indent=2))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
