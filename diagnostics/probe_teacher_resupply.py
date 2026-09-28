"""Isolate current command/item labels within the successful offline MAP03 teacher."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from training import map3_teacher, map3_focused_teacher
from training.route_resupply_close_health import labels as command_labels
from training.route_resupply_balanced import labels as item_labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=1200)
    parser.add_argument('--max-deaths', type=int)
    parser.add_argument('--visible-fights', action='store_true',
                        help='Test the original focused teacher fight priority while retaining current resupply labels')
    parser.add_argument('--visible-labeler', action='store_true',
                        help='Use the independent packet-only labeler intended for training')
    parser.add_argument('--finish-labeler', action='store_true',
                        help='Use offline finish-priority labels after collecting all keys')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists')
    original = map3_focused_teacher.focused_labels
    if sum((args.visible_fights, args.visible_labeler, args.finish_labeler)) > 1:
        parser.error('Choose one command labeler')
    labeler = command_labels
    if args.visible_labeler:
        if args.visible_fights:
            parser.error('Choose one visible-fight variant')
        from training.route_visible_resupply import labels as labeler
    if args.finish_labeler:
        from training.route_finish import labels as labeler

    def choose(packet, state, controller, base, style):
        full = map3_teacher.labels(packet, state, controller, 20, True, all_labels=True)
        full = original(packet, state, controller, full, style, all_labels=True)
        old_command = full['command']
        current = {kind: label for kind, label, _ in labeler(packet)}
        if old_command != 'look_back':
            full['command'] = current['command']
        if args.visible_fights and old_command == 'attack':
            full['command'] = 'attack'
        if full['command'] == 'pickup':
            items = {kind: label for kind, label, _ in item_labels(packet)}
            if 'item' not in items:
                raise ValueError('Current item label is missing for pickup')
            full['item'] = items['item']
        required = ['command', 'weapon'] + {
            'attack': ['enemy', 'movement'], 'pickup': ['item'], 'use_switch': ['switch']
        }.get(full['command'], [])
        if full['command'] in packet.get('combat_actions', ()) and 'combat' in packet['questions']:
            required.append('combat')
            # The teacher computes this label only for navigation. Its original
            # target choice remains the same when changing the command mode.
            target_id = packet['targets'].get('enemy', {}).get(full.get('enemy'), {}).get('id')
            full['combat'] = next((key for key, value in packet.get('combat_targets', {}).items()
                                   if value['id'] == target_id), 'hold')
        for kind in required:
            if full.get(kind) not in packet['questions'][kind]['criteria']:
                raise ValueError('Unavailable teacher label: ' + kind)
        return {kind: full[kind] for kind in required}

    map3_focused_teacher.focused_labels = choose
    try:
        map3_teacher.collect(args.output, 54, args.seconds, 16, visible_threats=True,
                            combat_style='focused-retreat', max_deaths=args.max_deaths,
                            attack_queue=True, floor_facts=True)
    finally:
        map3_focused_teacher.focused_labels = original
        if args.output.exists():
            hashes = {}
            for name in ('diagnostics/probe_teacher_resupply.py', 'training/route_resupply.py',
                         'training/route_resupply_close_health.py', 'training/route_resupply_balanced.py',
                         'training/build_map3_resources.py', 'training/route_visible_resupply.py',
                         'training/route_finish.py'):
                content = Path(name).read_bytes()
                target = args.output / 'source' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                hashes[name] = hashlib.sha256(content).hexdigest()
            for name in ('config.json', 'summary.json'):
                path = args.output / name
                if path.exists():
                    value = json.loads(path.read_text())
                    value.update(diagnostic_policy='offline-teacher-current-resupply',
                                 visible_fights=args.visible_fights, visible_labeler=args.visible_labeler,
                                 finish_labeler=args.finish_labeler,
                                 model_inference=False)
                    value['source_sha256'].update(hashes)
                    path.write_text(json.dumps(value, indent=2) + '\n')
            (args.output / 'DIAGNOSTIC-ONLY.txt').write_text(
                'Every decision came from offline labels. This is not a Laya run.\n')


if __name__ == '__main__':
    main()
