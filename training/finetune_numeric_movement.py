"""Train a movement residual on observed geometry with a frozen Laya head."""
import argparse
import collections
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
os.environ.update(USE_TF='0', USE_TORCH='1', TOKENIZERS_PARALLELISM='false')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doomlib.compact_movement import MOVEMENTS, compact_movement_input
from doomlib.numeric_movement import FORMAT, PROJECTION, FEATURES, TYPED_FORMAT, TYPED_FEATURES, features, semantic_logits, make_model
from doomlib.typed_movement import PROJECTION as TYPED_PROJECTION, semantic_state, typed_movement_input
from training.build_map3_retreat import choose_movement


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def synthetic(count, seed, labeler=choose_movement, typed=False):
    rng = random.Random(seed)
    rows = []
    for _ in range(count):
        nearest = rng.randint(1, 192) / 4
        known = rng.randint(1, 8)
        visible = rng.randint(0, known)
        current = rng.choice(MOVEMENTS)
        space = {side: rng.randint(0, 24 if rng.random() < .65 else 64) / 4 for side in ('left', 'right', 'back')}
        observed = [dict(name=rng.choice(('Demon', 'Spectre', 'DoomImp', 'ShotgunGuy')) if typed else 'DoomImp',
                         distance=nearest + i, visible=i < visible) for i in range(known)]
        enemies = '; '.join(e['name'] + '#' + str(i) + ' ' + str(e['distance']) + 'm (' + ('visible' if e['visible'] else 'last seen') + ')' for i, e in enumerate(observed))
        state = 'Movement: ' + current + '.\nEnemies: ' + enemies
        criteria = {'stationary': 'Stand still.'}
        for movement, side in [('strafe_left', 'left'), ('strafe_right', 'right'), ('backward', 'back')]:
            criteria[movement] = 'Move. Body clearance in this direction: ' + str(space[side]) + 'm.'
        projector = typed_movement_input if typed else compact_movement_input
        state, question = projector(state, dict(type='choice', instructions='Choose movement.', criteria=criteria))
        label = labeler(observed if typed else [dict(distance=nearest, visible=True)], space, current)
        rows.append(dict(state=state, question=question, label=label))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'data', 'cache', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--epochs', type=int, default=250)
    p.add_argument('--augmentation', type=int, default=40000)
    p.add_argument('--device', default='mps')
    p.add_argument('--lateral-priority', action='store_true')
    p.add_argument('--typed-retreat', action='store_true', help='Learn Demon/Spectre retreat with the original text branch and two extra observed features')
    a = p.parse_args()
    labeler = choose_movement
    labeler_path = 'training/build_map3_retreat.py'
    if a.lateral_priority:
        from training.lateral_movement import choose_lateral
        labeler = choose_lateral
        labeler_path = 'training/lateral_movement.py'
    if a.typed_retreat:
        if a.lateral_priority:
            p.error('Choose either --lateral-priority or --typed-retreat')
        from training.typed_movement import choose_typed
        labeler = choose_typed
        labeler_path = 'training/typed_movement.py'
    observe = lambda state: features(state, a.typed_retreat)
    text_state = semantic_state if a.typed_retreat else lambda state: state
    projection = TYPED_PROJECTION if a.typed_retreat else PROJECTION
    feature_schema = TYPED_FEATURES if a.typed_retreat else FEATURES
    if a.output.exists():
        raise ValueError('Output exists')
    import torch
    from safetensors.torch import save_file
    from laya import Agent
    from doomlib.laya_runtime import enable_single_option_padding
    torch.manual_seed(771)
    torch.set_num_threads(2)
    rows = {s: json.loads((a.data / (s + '.json')).read_text()) for s in ('train', 'validation')}
    identity = dict(semantic_weights=digest(a.base / 'model.safetensors'), config=digest(a.base / 'rl_agent_config.json'),
                    data={s: digest(a.data / (s + '.json')) for s in rows})
    cache = json.loads(a.cache.read_text()) if a.cache.exists() else dict(identity=identity, answers={})
    if cache['identity'] != identity:
        raise ValueError('Semantic cache identity differs')
    agent = Agent(str(a.base), device=a.device)
    enable_single_option_padding(agent.model)
    for split, group in rows.items():
        if split not in cache['answers']:
            cache['answers'][split] = [agent.predict(text_state(r['state']), {'movement': r['question']})['answers']['movement'] for r in group]
    differences = []
    for split, group in rows.items():
        for index in sorted({0, len(group)//4, len(group)//2, 3*len(group)//4, len(group)-1}):
            row = group[index]
            answer = agent.predict(text_state(row['state']), {'movement': row['question']})['answers']['movement']
            differences.append(max(abs(value - cache['answers'][split][index]['probabilities'][key]) for key, value in answer['probabilities'].items()))
    if max(differences) > .001:
        raise ValueError('Recorded semantic cache differs from fresh Agent.predict')
    cache.update(api_probability_max_difference=max(differences), requires_fresh_api_audit=False)
    a.cache.write_text(json.dumps(cache, indent=2) + '\n')
    print('CACHE_API_PARITY', max(differences), flush=True)
    del agent
    if a.device == 'mps':
        torch.mps.empty_cache()
    prepared = {}
    for split, group in rows.items():
        prepared[split] = (torch.tensor([observe(r['state']) for r in group], dtype=torch.float32),
                           torch.tensor([semantic_logits(answer) for answer in cache['answers'][split]], dtype=torch.float32),
                           torch.tensor([MOVEMENTS.index(r['label']) for r in group]))
    generated = {}
    for split, count, seed in [('train', a.augmentation, 272200), ('synthetic_validation', max(1000, a.augmentation//8), 272201)]:
        group = synthetic(count, seed, labeler, a.typed_retreat)
        generated[split] = (torch.tensor([observe(r['state']) for r in group], dtype=torch.float32),
                            prepared['train'][1][torch.randint(len(prepared['train'][1]), (len(group),))].clone(),
                            torch.tensor([MOVEMENTS.index(r['label']) for r in group]))
    original = prepared['train']
    prepared['train'] = tuple(torch.cat([real.repeat((6, 1) if real.ndim == 2 else (6,)), extra]) for real, extra in zip(original, generated['train']))
    prepared['synthetic_validation'] = generated['synthetic_validation']
    thresholds = {}
    for index in range(len(feature_schema)):
        unique = prepared['train'][0][:, index].unique().sort().values
        if len(unique) > 3:
            thresholds[str(index)] = torch.quantile(unique, torch.linspace(0, 1, min(65, len(unique)))).tolist()
    spec = dict(format=TYPED_FORMAT if a.typed_retreat else FORMAT, input_projection=projection, actions=list(MOVEMENTS), features=list(feature_schema),
                thresholds=thresholds, hidden_size=64, probability_floor=.0001)
    model = make_model(spec)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.002, weight_decay=.0001)
    def evaluate(split):
        model.eval()
        with torch.no_grad():
            x, b, y = prepared[split]
            correct = model(x, b).argmax(-1) == y
            return float(correct.float().mean()), correct.tolist()
    initial = evaluate('validation')[0]
    best, best_epoch, history = -1, None, []
    start = time.monotonic()
    for epoch in range(a.epochs):
        model.train()
        x, b, y = prepared['train']
        for indices in torch.randperm(len(x)).split(512):
            loss = torch.nn.functional.cross_entropy(model(x[indices], b[indices]), y[indices])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        accuracy, correct = evaluate('validation')
        synthetic_accuracy = evaluate('synthetic_validation')[0]
        selection = .8 * accuracy + .2 * synthetic_accuracy
        history.append(dict(epoch=epoch+1, accuracy=accuracy, synthetic_accuracy=synthetic_accuracy, selection=selection))
        if selection > best:
            best, best_epoch = selection, epoch+1
            best_state, best_correct = copy.deepcopy(model.state_dict()), correct
            best_accuracy, best_synthetic = accuracy, synthetic_accuracy
        if epoch % 25 == 0:
            print('EPOCH', epoch+1, 'validation', accuracy, 'synthetic', synthetic_accuracy, 'best', best, flush=True)
    if best_accuracy <= initial:
        raise ValueError('No improvement on recorded validation')
    def clone(source, target):
        if sys.platform == 'darwin':
            subprocess.run(['/bin/cp', '-c', str(source), str(target)], check=True)
        else:
            shutil.copyfile(source, target)
        return target
    shutil.copytree(a.base, a.output, copy_function=clone)
    (a.output / 'numeric-residual.json').write_text(json.dumps(spec, indent=2) + '\n')
    save_file(best_state, str(a.output / 'numeric-residual.safetensors'))
    config = json.loads((a.output / 'rl_agent_config.json').read_text())
    config['doom_adaptation']['input_projection'] = projection
    config['doom_adaptation']['question_format'] = projection
    config['doom_adaptation']['numeric_residual'] = dict(format=spec['format'], spec_sha256=digest(a.output / 'numeric-residual.json'),
        weights_sha256=digest(a.output / 'numeric-residual.safetensors'), semantic_parent=a.base.name, identity=identity,
        seed=771, epochs=a.epochs, learning_rate=.002, augmentation=a.augmentation, training_seed=272200, validation_seed=272201,
        real_train_repeat=6, trainer_sha256=digest(__file__), inference_sha256=digest('doomlib/numeric_movement.py'),
        labeler_sha256=digest(labeler_path), labeler=labeler_path, threshold_fit='training observations only',
        typed_enemy_geometry=a.typed_retreat, semantic_projection=PROJECTION,
        typed_projection_sha256=digest('doomlib/typed_movement.py') if a.typed_retreat else None,
        note='Frozen Laya semantic scores plus a learned geometric residual. Synthetic priors are random augmentation noise. Same-map development validation; no live labeler.')
    (a.output / 'rl_agent_config.json').write_text(json.dumps(config, indent=2) + '\n')
    total, correct_counts = collections.Counter(), collections.Counter()
    for row, matched in zip(rows['validation'], best_correct):
        total[row['category']] += 1
        correct_counts[row['category']] += matched
    metrics = dict(base_accuracy=initial, best_accuracy=best_accuracy, best_synthetic_accuracy=best_synthetic, best_epoch=best_epoch,
        semantic_scale=float(best_state['semantic_scale']), seconds=time.monotonic()-start, epochs=history,
        cache_probability_max_difference=max(differences), identity=identity,
        categories={key: dict(correct=correct_counts[key], total=count) for key,count in total.items()})
    (a.output / 'training-metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
    (a.output / 'best-epoch.json').write_text(json.dumps(dict(epoch=best_epoch, validation={'movement': best_accuracy}, numeric_residual=True), indent=2) + '\n')
    print('CHECKPOINT', a.output, 'accuracy', best_accuracy, 'synthetic', best_synthetic, 'epoch', best_epoch, flush=True)


if __name__ == '__main__':
    main()
