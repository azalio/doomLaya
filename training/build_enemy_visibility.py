"""Offline visible-first corrections; retain the existing enemy-ranking replay."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
import random
from doomlib.enemy_ranking import FORMAT, STOP, ranking_input
from doomlib.enemy_sequences import with_enemy_sequences
from training.build_map3_enemy_sequences import order_for


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def example(packet, provenance):
    packet = with_enemy_sequences(packet)
    order = order_for(packet)
    label = next(key for key, value in packet['enemy_sequences'].items() if value == order)
    state, question, orders = ranking_input(packet['state'], packet['questions']['enemy'])
    return dict(provenance, kind='enemy', state=state, raw_state=packet['state'],
                question=question, label=order[0], target_ranking=order + [STOP],
                sequence_question=copy.deepcopy(packet['questions']['enemy']),
                sequence_label=label, enemy_sequences=orders)


def synthetic(count, seed):
    rng = random.Random(seed)
    names = ('ShotgunGuy', 'Zombieman', 'ChaingunGuy', 'DoomImp', 'Demon', 'Cacodemon')
    for index in range(count):
        size = rng.choice((2, 3))
        visible = set(rng.sample(range(size), rng.randint(1, size-1)))
        targets = {str(100+i): dict(id=100+i, name=rng.choice(names),
                   distance=rng.randint(5, 300)/10, bearing=rng.randint(-120, 120),
                   visible=i in visible) for i in range(size)}
        # Include nearby remembered targets competing with more distant visible ones.
        if index % 2 == 0:
            for i in range(size):
                if i not in visible:
                    targets[str(100+i)]['distance'] = rng.randint(5, 50)/10
        hp = rng.choice((20, 45, 75, 100))
        state = f'HP {hp}; armor 0.\nInventory: melee 0 ammo; pistol 80 ammo; shotgun 12 ammo.'
        packet = dict(state=state, questions={'enemy': {}}, targets={'enemy': targets},
                      enemy_commitment={'target_id': rng.choice([None] + list(targets))})
        yield example(packet, dict(category='mixed_visibility_synthetic', synthetic=True,
                      source_type='offline_mixed_visibility', generator_seed=seed, source_index=index))


def build(source, runs, output, cases):
    if output.exists() or cases.exists():
        raise ValueError('Output exists')
    result = {s: json.loads((source/(s+'.json')).read_text()) for s in ('train', 'validation')}
    sources = {str(source/(s+'.json')): digest(source/(s+'.json')) for s in result}
    seen = {json.dumps([r['state'], r['question']], sort_keys=True) for group in result.values() for r in group}
    fixture = []
    added = collections.Counter()
    for run in runs:
        path = run/'decisions.jsonl'
        sources[str(path)] = digest(path)
        for line in path.open():
            d = json.loads(line)
            packet = d['packet']
            enemies = packet.get('targets', {}).get('enemy', {})
            if d['choice'] != 'attack' or len(enemies) < 2:
                continue
            visible = {key for key, enemy in enemies.items() if enemy.get('visible', True)}
            if not visible or len(visible) == len(enemies):
                continue
            selected = packet['enemy_sequences'][d['answers']['enemy']['choice']][0]
            if selected in visible:
                continue
            row = example(packet, dict(category='recorded_invisible_first', synthetic=False,
                          source_run=run.name, source_tick=d['tick'], source_episode=d['episode'],
                          source_type='offline_visible_target_correction'))
            split = 'validation' if d['episode'] % 3 == 0 else 'train'
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key not in seen:
                seen.add(key)
                result[split].append(row)
                added[split] += 1
            if len(fixture) < 16:
                fixture.append(dict(source_run=run.name, tick=d['tick'], packet=packet,
                                    check='visible_enemy_first', expected_visible_targets=sorted(visible)))
    for split, count, seed in [('train', 256, 272400), ('validation', 96, 272401)]:
        for row in synthetic(count, seed):
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key in seen:
                raise ValueError('Synthetic input overlaps an existing input')
            seen.add(key)
            result[split].append(row)
    output.mkdir()
    manifest = dict(input_projection=FORMAT, question_format='enemy-sequence-v1',
                    training_objective='nonempty-listwise-v1', sources=sources,
                    builder_sha256=digest(__file__), labeler_sha256=digest('training/build_map3_enemy_sequences.py'),
                    added_recorded=dict(added), splits={},
                    note='Original replay labels and allocation retained. New recorded corrections only when the model chose a remembered enemy while a visible enemy was offered. Episode modulo 3=0 held out; same-map development, not independent gameplay validation. Synthetic mixed-visibility examples use separate seeds. No live teacher.')
    for split, rows in result.items():
        random.Random(771).shuffle(rows)
        path = output/(split+'.json')
        path.write_text(json.dumps(rows, indent=2)+'\n')
        manifest['splits'][split] = dict(rows=len(rows), sha256=digest(path),
                                        categories=dict(collections.Counter(r['category'] for r in rows)))
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    cases.write_text(json.dumps(dict(note='Recorded development failures included in correction data; not independent validation.', sources=sources, cases=fixture), indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--replay', type=Path, default=Path('training/map3-ranked-enemy-v3'))
    p.add_argument('--runs', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cases', type=Path, required=True)
    a = p.parse_args()
    build(a.replay, a.runs, a.output, a.cases)
