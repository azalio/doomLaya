"""Compare movement labelers in the offline teacher, without neural inference."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training import map3_focused_teacher, map3_teacher
from training.lateral_movement import choose_lateral
from training.typed_movement import choose_typed


def substitute_movement(original, policy):
    def label(packet, state, controller, base, style):
        gold = original(packet, state, controller, base, style)
        if 'movement' in gold:
            gold['movement'] = policy(
                list(packet['targets']['enemy'].values()),
                controller.navigator.movement_clearance(state),
                (controller.directive or {}).get('movement', 'stationary'))
        return gold
    return label


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--policy', choices=('typed', 'lateral'), required=True)
    parser.add_argument('--seconds', type=int, default=1200)
    parser.add_argument('--max-deaths', type=int)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists')
    original = map3_focused_teacher.focused_labels
    policy = choose_typed if args.policy == 'typed' else choose_lateral
    map3_focused_teacher.focused_labels = substitute_movement(original, policy)
    try:
        map3_teacher.collect(args.output, 54, args.seconds, 16,
                            visible_threats=True, combat_style='focused-retreat',
                            max_deaths=args.max_deaths, attack_queue=True,
                            floor_facts=True)
    finally:
        map3_focused_teacher.focused_labels = original
        if args.output.exists():
            hashes = {}
            for name in ('diagnostics/probe_teacher_movement.py',
                         'training/typed_movement.py', 'training/lateral_movement.py',
                         'doomlib/typed_movement.py', 'doomlib/numeric_movement.py',
                         'doomlib/compact_movement.py'):
                content = Path(name).read_bytes()
                destination = args.output / 'source' / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                hashes[name] = hashlib.sha256(content).hexdigest()
            for name in ('config.json', 'summary.json'):
                path = args.output / name
                if path.exists():
                    value = json.loads(path.read_text())
                    value.update(diagnostic_policy='offline-teacher-movement-' + args.policy,
                                 model_inference=False)
                    value['source_sha256'].update(hashes)
                    path.write_text(json.dumps(value, indent=2) + '\n')
            (args.output / 'DIAGNOSTIC-ONLY.txt').write_text(
                'Every choice came from offline labels. This is not a Laya run.\n')


if __name__ == '__main__':
    main()
