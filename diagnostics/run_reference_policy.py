"""Diagnostic upper bound: offline command/item labels plus real Laya subheads.

This is explicitly NOT a Laya gameplay result. The authority verifier rejects it.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent
from doomlib import decision_questions
from doomlib.look_questions import mix_look_answer
from training.route_priority import labels
from tools.regression_suite import FLAGS

POLICY = 'diagnostic-offline-command-item-reference-v1'
REFERENCE_ITEMS = True
REFERENCE_COMMANDS = True
REFERENCE_ENEMIES = False
NEAREST_ENEMY = False
KEY_HEALTH_ONLY = False
SNAPSHOT = None
ORIGINAL_CLIENT = agent.LayaClient
ORIGINAL_DEPENDENCIES = decision_questions.dependencies
ORIGINAL_OVERLAY = agent.Overlay


def capture(packet):
    global SNAPSHOT
    SNAPSHOT = copy.deepcopy(packet)
    return ORIGINAL_DEPENDENCIES(packet)


def one_hot(question, selected):
    if selected not in question['criteria']:
        raise ValueError('Reference selected an unavailable action')
    return dict(type='choice', choice=selected, probabilities={key: float(key == selected) for key in question['criteria']},
                confidence=1.0, action={'act_probability': 1.0})


class ReferenceClient(ORIGINAL_CLIENT):
    def health(self):
        result = super().health()
        result['diagnostic_policy'] = POLICY
        labeler_path = Path(sys.modules[labels.__module__].__file__)
        result['diagnostic_labeler_sha256'] = hashlib.sha256(labeler_path.read_bytes()).hexdigest()
        result['diagnostic_labeler'] = labels.__module__
        return result

    def predict(self, text, questions=None, dependencies=None):
        if dependencies is not None:
            return self.predict_conditional(text, questions, dependencies)
        if SNAPSHOT is None or SNAPSHOT['state'] != text:
            raise ValueError('Reference observation is stale')
        expected = {kind: label for kind, label, _ in labels(SNAPSHOT)}
        result = super().predict(text, questions)
        result['routing'] = dict(result['routing'], diagnostic_policy=POLICY, checkpoint='DIAGNOSTIC REFERENCE')
        selected = (['command'] if REFERENCE_COMMANDS else []) + (['item'] if REFERENCE_ITEMS else []) + (['enemy'] if REFERENCE_ENEMIES else [])
        if REFERENCE_ENEMIES and 'enemy' in questions:
            from training.build_map3_enemy_sequences import order_for
            if NEAREST_ENEMY:
                enemies = SNAPSHOT['targets']['enemy']
                visible = {key:enemy for key,enemy in enemies.items() if enemy.get('visible',True)}
                first = min(visible or enemies,key=lambda key:enemies[key]['distance'])
                order = [first] + sorted((key for key in enemies if key!=first),key=lambda key:enemies[key]['distance'])
            else:
                order = order_for(SNAPSHOT)
            expected['enemy'] = next(key for key, sequence in SNAPSHOT['enemy_sequences'].items() if sequence == order)
        for name in selected:
            if name not in questions or name not in expected:
                continue
            original = copy.deepcopy(result['answers'][name])
            if name == 'item' and KEY_HEALTH_ONLY:
                items = SNAPSHOT['targets'].get('item', {})
                if items.get(original['choice'], {}).get('category') != 'Key' or items.get(expected[name], {}).get('category') != 'Health':
                    continue
            question = copy.deepcopy(questions[name])
            if name == 'command' and 'look_back' in question['criteria']:
                question['criteria'].pop('look_back')
                base = one_hot(question, expected[name])
                answer = mix_look_answer(base, original['look_gate']['answer'], list(questions[name]['criteria']))
            else:
                answer = one_hot(question, expected[name])
            answer['diagnostic_reference'] = dict(policy=POLICY, original_model_answer=original)
            result['answers'][name] = answer
            result['raw_probabilities'][name] = dict(answer['probabilities'])
        if 'command' in questions:
            result['choice'] = result['answers']['command']['choice']
            result['probabilities'] = result['answers']['command']['probabilities']
        return result


class ReferenceOverlay(ORIGINAL_OVERLAY):
    def __init__(self, tactics, model):
        super().__init__(tactics, 'REFERENCE POLICY')


def main():
    global POLICY, REFERENCE_ITEMS, REFERENCE_COMMANDS, REFERENCE_ENEMIES, NEAREST_ENEMY, KEY_HEALTH_ONLY, labels
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map', default='MAP01')
    parser.add_argument('--seed', type=int, default=48)
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--endpoint', default='http://127.0.0.1:8003/predict')
    parser.add_argument('--tag', default='v031-reference-policy')
    parser.add_argument('--command-only', action='store_true')
    parser.add_argument('--item-only', action='store_true')
    parser.add_argument('--balanced-resupply', action='store_true')
    parser.add_argument('--key-health-only', action='store_true')
    parser.add_argument('--safe-fight', action='store_true')
    parser.add_argument('--resupply', action='store_true')
    parser.add_argument('--enemy-only', action='store_true')
    parser.add_argument('--nearest-enemy', action='store_true')
    args = parser.parse_args()
    if args.command_only:
        REFERENCE_ITEMS = False
        POLICY = 'diagnostic-offline-command-reference-v1'
    if args.item_only:
        if args.command_only or args.enemy_only: parser.error('--item-only conflicts with other head-only modes')
        REFERENCE_COMMANDS = False
        POLICY = 'diagnostic-offline-item-reference-v1'
    if args.balanced_resupply:
        if args.resupply or args.safe_fight: parser.error('Choose one rubric')
        from training.route_resupply_balanced import labels
        POLICY += '-balanced-resupply'
    if args.key_health_only:
        if not args.item_only or not args.balanced_resupply: parser.error('--key-health-only requires --item-only --balanced-resupply')
        KEY_HEALTH_ONLY = True
        POLICY += '-key-health-only'
    if args.safe_fight:
        from training.route_survival import labels
        POLICY += '-safe-fight'
    if args.resupply:
        from training.route_resupply import labels
        POLICY += '-resupply'
    if args.enemy_only:
        REFERENCE_COMMANDS = False
        REFERENCE_ITEMS = False
        REFERENCE_ENEMIES = True
        POLICY = 'diagnostic-offline-enemy-reference-v1'
    if args.nearest_enemy:
        if not args.enemy_only: parser.error('--nearest-enemy requires --enemy-only')
        NEAREST_ENEMY = True
        POLICY = 'diagnostic-nearest-visible-enemy-reference-v1'
    before = set(Path('runs').glob('*'))
    agent.LayaClient = ReferenceClient
    agent.Overlay = ReferenceOverlay
    decision_questions.dependencies = capture
    sys.argv = ['agent.py', '--model', 'doom-adapted', '--endpoint', args.endpoint, *FLAGS,
                '--map', args.map, '--seed', str(args.seed), '--seconds', str(args.seconds), '--tag', args.tag]
    result = agent.main()
    created = set(Path('runs').glob('*')) - before
    runs = [path for path in created if path.is_dir() and (path / 'config.json').exists()]
    if len(runs) != 1:
        raise ValueError('Cannot identify reference run')
    run = runs[0]
    config_path = run / 'config.json'
    config = json.loads(config_path.read_text())
    config['diagnostic_policy'] = POLICY
    for name in ('diagnostics/run_reference_policy.py', 'training/route_priority.py', 'training/route_survival.py', 'training/route_resupply.py', 'training/route_resupply_balanced.py', 'training/build_map3_resources.py', 'training/build_map3_enemy_sequences.py', 'tools/regression_suite.py'):
        content = Path(name).read_bytes()
        destination = run / 'source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        config['source_sha256'][name] = hashlib.sha256(content).hexdigest()
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    summary_path = run / 'summary.json'
    summary = json.loads(summary_path.read_text())
    summary.update(model='REFERENCE POLICY + Laya subheads', diagnostic_policy=POLICY)
    summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    (run / 'DIAGNOSTIC-ONLY.txt').write_text(('Enemy choices' if REFERENCE_ENEMIES else 'Command and item choices' if REFERENCE_ITEMS and REFERENCE_COMMANDS else 'Item choices' if REFERENCE_ITEMS else 'Command choices') + ' came from an offline rule labeler. Other heads used Laya. This run is not an accepted Laya completion.\n')
    from doomlib.report import build_report
    build_report(run)
    print('DIAGNOSTIC_RUN', run, flush=True)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
