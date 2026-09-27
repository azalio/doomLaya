"""Offline resource/combat corrections on exact MAP03 inputs; no runtime policy."""
import argparse
import collections
import copy
import hashlib
import json
import random
from pathlib import Path
from training.build_goal_invariant_commands import change_goal, goal_headers


def label(packet):
    """Conservative local supervision; leave navigation decisions unlabelled."""
    options = packet['questions']['command']['criteria']
    inventory = packet['observation']['inventory']
    hp = packet['observation']['hp']
    targets = packet.get('targets', {})
    enemies = targets.get('enemy', {}).values()
    distance = min((e['distance'] for e in enemies), default=float('inf'))
    items = [i for i in targets.get('item', {}).values() if i.get('reachable')]
    loaded = {int(k) for k,v in inventory.items() if v['owned'] and v['ammo'] >= (2 if k == '8' else 1)}
    upgrades = [i for i in items if i['name'] in ('Shotgun','SuperShotgun','Chaingun','PlasmaRifle') and i['distance'] <= 10]
    health = [i for i in items if i['category'] == 'Health' and 'Bonus' not in i['name']]
    if 'open_door' in options:
        door = packet.get('commands', {}).get('open_door', {}).get('target') or {}
        if door.get('distance',999) < 2.5 and not door.get('locked') and distance >= 3:
            return 'open_door', 'blocking_door'
    if 'pickup' in options:
        if hp < 35 and any(i['distance'] <= 6 for i in health):
            return 'pickup', 'urgent_health'
        if not loaded.intersection({3,4,5,6,7,8}) and upgrades and distance >= 3:
            return 'pickup', 'loaded_weapon_before_route'
    if 'attack' in options and distance < 20:
        return 'attack', 'nearby_enemy'
    if 'pickup' in options:
        if hp < 75 and any(i['distance'] < 20 for i in health):
            return 'pickup', 'health_before_route'
        for item in items:
            if item['distance'] >= 12:
                continue
            shells = item['name'] in ('Shotgun','SuperShotgun','Shell','ShellBox')
            bullets = item['name'] in ('Clip','ClipBox','Chaingun')
            if shells and (inventory['3']['owned'] or inventory['8']['owned']) and inventory['3']['ammo'] < 8:
                return 'pickup', 'shells_before_route'
            if bullets and inventory['2']['ammo'] < 20:
                return 'pickup', 'bullets_before_route'
    return None


def build(run, replay, output):
    if output.exists():
        raise ValueError('Output exists')
    decisions = [json.loads(l) for l in (run/'decisions.jsonl').read_text().splitlines()]
    pools = {'train': [], 'validation': []}
    sources = {str(run/name): hashlib.sha256((run/name).read_bytes()).hexdigest() for name in ('config.json','decisions.jsonl','summary.json')}
    pairs = collections.Counter()
    for decision in decisions:
        gold = label(decision['packet'])
        if not gold:
            continue
        action, reason = gold
        split = 'train' if decision['episode'] % 2 == 0 else 'validation'
        row = dict(kind='command', category=reason, label=action, state=decision['packet']['state'], question=copy.deepcopy(decision['packet']['questions']['command']), source_run=run.name, source_tick=decision['tick'], source_episode=decision['episode'], source_type='offline_map03_survival_correction', model_choice=decision['choice'])
        pairs[decision['choice']+' -> '+action] += 1
        pools[split].append(row)
        if action == 'pickup':
            pools[split].append(change_goal(row, None))
            for goals in goal_headers(row).values():
                pools[split].append(change_goal(row, goals[0]))
    rng = random.Random(9301)
    seen = {}
    manifest = dict(note='Offline labels on exact recorded MAP03 questions. Local resource/combat conditions only; no scripted navigation labels. MAP03 episodes split by parity; goal variants remain in their original split. MAP02 retention preserves its original split. Same-map validation, not unseen-level evaluation. Runtime never imports this module.', sources=sources, action_pairs=dict(pairs), splits={})
    result = {}
    for split in ('train','validation'):
        groups = collections.defaultdict(list)
        for row in pools[split]:
            groups[row['label']].append(row)
        rows = []
        for values in groups.values():
            rng.shuffle(values)
            rows.extend(values[:300 if split == 'train' else 150])
        path = replay/(split+'.json')
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        old = collections.defaultdict(list)
        for row in json.loads(path.read_text()):
            if row['kind'] == 'command':
                old[row['label']].append(row)
        for values in old.values():
            rng.shuffle(values)
            rows.extend(values[:100 if split == 'train' else 40])
        clean = []
        for row in rows:
            key = json.dumps([row['state'],row['question']], sort_keys=True)
            if key in seen:
                if seen[key] != row['label']:
                    raise ValueError('Conflicting labels')
                continue
            seen[key] = row['label']
            assert row['label'] in row['question']['criteria']
            clean.append(row)
        rng.shuffle(clean)
        result[split] = clean
        manifest['splits'][split] = dict(rows=len(clean), labels=dict(collections.Counter(r['label'] for r in clean)), categories=dict(collections.Counter(r['category'] for r in clean)))
    output.mkdir()
    for split, rows in result.items():
        path = output/(split+'.json')
        path.write_text(json.dumps(rows,ensure_ascii=False,indent=2))
        manifest['splits'][split]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest['builder_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run',type=Path)
    p.add_argument('--replay',type=Path,default=Path('training/map2-root-goals-v1'))
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    build(a.run,a.replay,a.output)
