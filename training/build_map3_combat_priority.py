"""Offline command corrections: finish nearby fights before route errands."""
import argparse, collections, copy, hashlib, json, random, re
from pathlib import Path


def normal_input(row):
    row = copy.deepcopy(row)
    row['state'] = '\n'.join(line for line in row['state'].splitlines() if not line.startswith('Current command:'))
    q = row['question']
    q.pop('look_observation', None)
    q['criteria'].pop('look_back', None)
    q['instructions'] = q['instructions'][q['instructions'].index('Finish the level alive.'):]
    return row


def correction(packet):
    enemies = list(packet.get('targets', {}).get('enemy', {}).values())
    if not enemies or 'attack' not in packet['questions']['command']['criteria']:
        return None
    visible = [enemy for enemy in enemies if enemy.get('visible', True)]
    nearest = min(enemy['distance'] for enemy in (visible or enemies))
    if not visible and nearest >= 20:
        return None
    hp = float(re.search(r'^HP ([0-9.]+);', packet['state'], re.M)[1])
    items = list(packet.get('targets', {}).get('item', {}).values())
    if any(item.get('category') == 'Health' and item['distance'] < 2 for item in items) and hp < 25:
        return 'pickup', 'urgent_health_near_threat'
    armed = re.search(r'\b(?:shotgun|super_shotgun|chaingun|rocket_launcher|plasma_rifle|bfg) ([1-9][0-9]*) ammo', packet['state'])
    if not armed and nearest > 3 and any(item.get('category') == 'Weapon' and item['distance'] < 6 for item in items):
        return 'pickup', 'close_weapon_near_threat'
    return 'attack', 'fight_near_door' if 'open_door' in packet['questions']['command']['criteria'] else 'finish_fight'


def build(train_runs, validation_runs, teacher, replay, output):
    if output.exists(): raise ValueError('Output exists')
    if set(train_runs) & set(validation_runs) or teacher in validation_runs:
        raise ValueError('Source runs overlap')
    sources = {}; result = {}; seen = {}; rng = random.Random(8217); removed = collections.Counter()
    for split, runs in [('train', train_runs), ('validation', validation_runs)]:
        rows = []
        for run in runs:
            path = run / 'decisions.jsonl'; sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            for line in path.open():
                d = json.loads(line); packet = d['packet']; value = correction(packet)
                if value is None: continue
                label, category = value
                rows.append(normal_input(dict(kind='command', state=packet['state'], question=packet['questions']['command'],
                    label=label, category=category, source_run=run.name, source_tick=d['tick'], source_episode=d['episode'],
                    source_type='offline_relabel', synthetic=False)))
        if split == 'train':
            path = teacher / 'examples.jsonl'; sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            for line in path.open():
                row = json.loads(line)
                if row['kind'] != 'command' or row['label'] == 'look_back': continue
                row = normal_input(row); row['category'] = 'teacher_' + row['label']; rows.append(row)
        path = replay / (split + '.json'); sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for row in json.loads(path.read_text()):
            # Keep route/resource behavior only where no enemies were observed.
            if row['kind'] != 'command' or re.search(r'^Enemies:', row['state'], re.M): continue
            rows.append(normal_input(row))
        groups = collections.defaultdict(list)
        for row in rows: groups[row['category']].append(row)
        rows = []
        for category, values in groups.items():
            rng.shuffle(values)
            cap = (350 if category in ('fight_near_door', 'finish_fight') else 100) if split == 'train' else 100
            if category == 'reachable_red_key_contrast': cap = 300
            rows.extend(values[:cap])
        clean = []
        for row in rows:
            if row['label'] not in row['question']['criteria']: raise ValueError('Unavailable label')
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key in seen:
                if seen[key][1] != row['label']: raise ValueError('Conflicting identical input')
                removed[split] += 1; continue
            seen[key] = (split, row['label']); clean.append(row)
        rng.shuffle(clean); result[split] = clean
    output.mkdir(); manifest = dict(note='Offline command corrections on known threats, preserving nearby emergency health/weapon pickups. Includes a complete scripted teacher run and no-enemy route replay. Different live runs held out for development; older replay was used by the base checkpoint and is a retention check. No runtime rule or gameplay success claim.', sources=sources, splits={}, removed=dict(removed))
    for split, rows in result.items():
        path = output / (split + '.json'); path.write_text(json.dumps(rows, indent=2))
        manifest['splits'][split] = dict(rows=len(rows), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), categories=dict(collections.Counter(row['category'] for row in rows)))
    manifest['builder_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2)); print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--train-runs', nargs='+', type=Path, required=True)
    p.add_argument('--validation-runs', nargs='+', type=Path, required=True)
    p.add_argument('--teacher', type=Path, required=True)
    p.add_argument('--replay', type=Path, default=Path('training/map3-command-key-v2'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); build(a.train_runs, a.validation_runs, a.teacher, a.replay, a.output)
