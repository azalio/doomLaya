"""Ask the real model about recorded teacher observations; never drive gameplay."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def cases(run):
    from doomlib.enemy_sequences import with_enemy_sequences
    from doomlib.look_questions import with_look_gate
    from doomlib.movement_questions import with_movement_obstacle_facts
    from training.build_map3_enemy_sequences import order_for
    summary = json.loads((run / 'summary.json').read_text())
    if summary.get('model_inference') is not False:
        raise ValueError('Expected a finalized offline teacher')
    groups = {}
    for row in map(json.loads, (run / 'examples.jsonl').open()):
        groups.setdefault(row['source_tick'], {})[row['kind']] = row
    timeline = sorted(groups)
    index, latest, last_episode = 0, None, None
    for state in map(json.loads, (run / 'telemetry.jsonl').open()):
        tick = state['tick']
        if tick not in groups:
            continue
        group = groups[tick]
        if state['episode'] != last_episode:
            latest, last_episode = None, state['episode']
        while index < len(timeline) and timeline[index] + summary['latency_ticks'] <= tick:
            prior = groups[timeline[index]]
            if prior['command']['source_episode'] == state['episode']:
                latest = prior['enemy']['label'] if prior['command']['label'] == 'attack' else None
            index += 1
        packet = dict(state=group['command']['state'],
                      questions={kind: copy.deepcopy(row['question']) for kind, row in group.items()},
                      observation=state, commands={}, targets={})
        expected = {kind: row['label'] for kind, row in group.items()}
        # The old collector asked a direct look question; production uses the
        # same observed damage facts through a separate learned gate.
        enemies = {str(enemy['id']): enemy for enemy in state['enemies'][:3]}
        packet['targets']['enemy'] = enemies
        facts = dict(state['recent_damage'], standing_on_damaging_floor=
                     state.get('floor_hazard', {}).get('mapped_damaging_floor', False))
        packet = with_look_gate(packet, facts)
        instruction = packet['questions']['command']['instructions']
        packet['questions']['command']['instructions'] = re.sub(
            r'^Recent health loss .*?Look back status: [^.]+\. ', '', instruction)
        if 'enemy' in group:
            keys = group['enemy']['question']['criteria']
            packet['targets']['enemy'] = {key: enemies[key] for key in keys}
            packet['enemy_commitment'] = {'target_id': latest}
            packet = with_enemy_sequences(packet)
            order = order_for(packet, group['enemy']['label'])
            expected['enemy'] = next(key for key, value in packet['enemy_sequences'].items() if value == order)
        if 'movement' in group:
            question = packet['questions']['movement']
            packet['movement_clearance'] = {
                side: float(re.search(r'Body clearance in this direction: ([0-9.]+)m', question['criteria'][choice])[1])
                for side, choice in [('left', 'strafe_left'), ('right', 'strafe_right'), ('back', 'backward')]}
            packet = with_movement_obstacle_facts(packet)
        yield dict(tick=tick, episode=state['episode'], packet=packet, expected=expected)


def main():
    from agent import LayaClient
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:8003/predict')
    parser.add_argument('--every', type=int, default=1)
    args = parser.parse_args()
    if args.output.exists() or args.every < 1:
        parser.error('Output exists or invalid sampling interval')
    client = LayaClient(args.endpoint, 'doom-adapted')
    health = client.health()
    results, counts = [], collections.defaultdict(collections.Counter)
    completed = False
    try:
        for index, case in enumerate(cases(args.run)):
            if index % args.every:
                continue
            packet = case['packet']
            response = client.predict(packet['state'], packet['questions'])
            if response['routing']['weights_sha256'] != health['weights_sha256']:
                raise ValueError('Model changed during replay')
            for kind, expected in case['expected'].items():
                actual = response['answers'][kind]['choice']
                counts[kind]['total'] += 1
                counts[kind]['correct'] += actual == expected
                if kind == 'enemy':
                    counts[kind]['first_correct'] += packet['enemy_sequences'][actual][0] == packet['enemy_sequences'][expected][0]
            results.append(dict(case, answers=response['answers']))
            if len(results) % 50 == 0:
                print(json.dumps(dict(processed=len(results), counts=counts)), flush=True)
        completed = True
    finally:
        client.session.close()
        sources = {name: hashlib.sha256((args.run / name).read_bytes()).hexdigest()
                   for name in ('summary.json', 'examples.jsonl', 'telemetry.jsonl')}
        args.output.write_text(json.dumps(dict(
            note='Recorded successful teacher observations, queried through the actual API. Same-map development; not a model gameplay result.',
            source_run=str(args.run), sources=sources, routing=health, counts=counts, completed=completed,
            results=results), indent=2) + '\n')
    print(json.dumps(dict(counts=counts)), flush=True)


if __name__ == '__main__':
    main()
