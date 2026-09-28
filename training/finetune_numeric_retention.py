"""Repair selected command labels while retaining recorded model decisions."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

os.environ.update(USE_TF='0', USE_TORCH='1', TOKENIZERS_PARALLELISM='false')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doomlib.numeric_command import ACTIONS, features, semantic_logits, make_residual_model
from doomlib.command_facts import stable_command_facts_input
from training.build_regression_replay import project
from training.numeric_augmentation import examples
from training.route_finish import labels


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def all_keys_observed(packet):
    # The public packet's observation is compact and omits the keys field.
    # Use the same explicit observed line that feeds the model projection.
    line = re.search(r'^Collected keys: ([^\n]+)', packet['state'], re.M)
    if line is None:
        raise ValueError('Missing collected-key observation')
    return set(re.findall(r'\b(red|blue|yellow)\b', line[1])) == {'red', 'blue', 'yellow'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'data', 'cache', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--retention-run', type=Path, action='append', required=True)
    p.add_argument('--retain-all-observations', action='store_true')
    p.add_argument('--repair-category', action='append', help='Category prefix to repair; default route_finish_')
    p.add_argument('--epochs', type=int, default=500)
    p.add_argument('--learning-rate', type=float, default=.0003)
    p.add_argument('--retention-weight', type=float, default=1)
    p.add_argument('--margin-weight', type=float, default=100)
    p.add_argument('--trainable-block', choices=('output', 'hidden'), default='output')
    a = p.parse_args()
    if a.output.exists():
        p.error('Output exists')
    import torch
    from safetensors.torch import load_file, save_file
    torch.set_num_threads(2)
    torch.manual_seed(771)
    spec = json.loads((a.base / 'numeric-residual.json').read_text())
    model = make_residual_model(spec)
    model.load_state_dict(load_file(str(a.base / 'numeric-residual.safetensors')))
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    layer_start = 4 if a.trainable_block == 'output' else 2
    for parameter in model.network[layer_start:].parameters():
        parameter.requires_grad_(True)
    cache = json.loads(a.cache.read_text())
    if cache['identity']['semantic_weights'] != digest(a.base / 'model.safetensors'):
        raise ValueError('Frozen semantic weights differ')
    groups = {split: json.loads((a.data / (split + '.json')).read_text()) for split in ('train', 'validation')}
    for split in groups:
        if cache['identity']['data'][split] != digest(a.data / (split + '.json')):
            raise ValueError('Semantic cache data differs')
    bases = {split: [semantic_logits(answer) for answer in cache['answers'][split]] for split in groups}
    prefix, prefix_b = [], []
    run_paths = [run / 'decisions.jsonl' for run in a.retention_run]
    for run_path in run_paths:
        for d in map(json.loads, run_path.open()):
            packet = d['packet']
            if not a.retain_all_observations and all_keys_observed(packet):
                continue
            answer = d['answers']['command']
            answer = answer.get('look_gate', {}).get('base_answer', answer)
            row = project(dict(kind='command', state=packet['state'], question=copy.deepcopy(packet['questions']['command']),
                               label=answer['choice'], category='retention_prefix', source_tick=d['tick']))
            row['state'], row['question'] = stable_command_facts_input(row['raw_state'], row['question'])
            prefix.append(row)
            prefix_b.append(semantic_logits(answer['numeric_residual']['semantic_answer']))
    groups['prefix'], bases['prefix'] = prefix, prefix_b
    categories = {name: line.split()[1] for row in groups['train'] for line in row['state'].splitlines()
                  if line.startswith('Reachable ') and ' items:' in line
                  for name in __import__('doomlib.numeric_command', fromlist=['item_distances']).item_distances(line)}
    for split, count, seed in [('synthetic_train', 12000, 272810), ('synthetic_validation', 3000, 272811)]:
        rows = list(examples(categories, count, seed, labels, include_items=True, broad_inventory=True, broad_mechanisms=True))
        for row in rows:
            row['category'] = labels(row.pop('packet'))[0][2]
        groups[split] = rows
        indices = torch.randint(len(bases['train']), (len(rows),)).tolist()
        bases[split] = [bases['train'][index] for index in indices]
    prepared = {}
    for split, rows in groups.items():
        x = torch.tensor([features(row, spec['item_names']) for row in rows])
        b = torch.tensor(bases[split])
        mask = torch.tensor([[action in row['question']['criteria'] for action in ACTIONS] for row in rows])
        y = torch.tensor([ACTIONS.index(row['label']) for row in rows])
        repair = torch.tensor([row['category'].startswith(tuple(a.repair_category or ['route_finish_'])) for row in rows])
        hidden, old = [], []
        with torch.no_grad():
            for indices in torch.arange(len(x)).split(512):
                observed = x[indices]
                basis = (observed[:, model.basis_indices] >= model.basis_thresholds).float()
                inputs = torch.cat([observed, basis, b[indices] / 10], -1)
                h = model.network[:layer_start](inputs)
                z = model.semantic_scale * b[indices] + model.network[layer_start:](h)
                hidden.append(h)
                old.append(z)
        h, z = torch.cat(hidden), torch.cat(old)
        if split == 'prefix' and not torch.equal(z.masked_fill(~mask, -1e4).argmax(-1), y):
            raise ValueError('CPU replay does not reproduce the recorded parent decisions')
        prepared[split] = h, b, mask, y, repair, z
    training = tuple(torch.cat([real.repeat((4, 1) if real.ndim == 2 else (4,)),
                                kept.repeat((12, 1) if kept.ndim == 2 else (12,)), synthetic])
                     for real, kept, synthetic in zip(prepared['train'], prepared['prefix'], prepared['synthetic_train']))
    optimizer = torch.optim.AdamW(model.network[layer_start:].parameters(), lr=a.learning_rate, weight_decay=0)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, a.epochs, eta_min=a.learning_rate / 100)

    def evaluate(split):
        h, b, mask, y, repair, old = prepared[split]
        with torch.no_grad():
            z = model.semantic_scale * b + model.network[layer_start:](h)
            choice = z.masked_fill(~mask, -1e4).argmax(-1)
            old_choice = old.masked_fill(~mask, -1e4).argmax(-1)
            return dict(total=len(y), gold_correct=int((choice == y).sum()),
                        repairs=int(repair.sum()), repaired=int(((choice == y) & repair).sum()),
                        preserved=int(((choice == old_choice) & ~repair).sum()), retained=int((~repair).sum()))

    initial = {split: evaluate(split) for split in ('validation', 'prefix', 'synthetic_validation')}
    best, state, best_epoch, history = None, None, None, []
    start = time.monotonic()
    for epoch in range(a.epochs):
        for indices in torch.randperm(len(training[0])).split(512):
            h, b, mask, y, repair, old = (value[indices] for value in training)
            z = model.semantic_scale * b + model.network[layer_start:](h)
            ce = torch.nn.functional.cross_entropy(z.masked_fill(~mask, -1e4), y, reduction='none')
            preservation = ((z - old).square() * mask).sum(-1) / mask.sum(-1)
            old_choice = old.masked_fill(~mask, -1e4).argmax(-1)
            others = mask.clone().scatter_(1, old_choice[:, None], False)
            old_margin = old.gather(1, old_choice[:, None]).squeeze(1) - old.masked_fill(~others, -1e4).max(-1).values
            margin = (z.masked_fill(~others, -1e4).max(-1).values - z.gather(1, old_choice[:, None]).squeeze(1)
                      + (old_margin / 2).clamp(0, .1)).clamp_min(0)
            loss = (20 * ce * repair + (a.retention_weight * preservation + a.margin_weight * margin) * ~repair).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        scheduler.step()
        if (epoch + 1) % 5:
            continue
        metrics = {split: evaluate(split) for split in initial}
        valid, kept, synthetic = (metrics[split] for split in initial)
        score = (valid['repaired'], synthetic['repaired'], valid['preserved'])
        eligible = kept['preserved'] == kept['retained'] and valid['preserved'] >= valid['retained'] - 1
        history.append(dict(epoch=epoch + 1, eligible=eligible, metrics=metrics))
        if eligible and (best is None or score > best):
            best, state, best_epoch = score, copy.deepcopy(model.state_dict()), epoch + 1
        if (epoch + 1) % 25 == 0:
            print(json.dumps(history[-1]), 'best', best, flush=True)
    if state is None or best[0] == 0:
        raise RuntimeError('No repair preserved the required old behavior; no checkpoint exported')
    model.load_state_dict(state)

    def clone(source, target):
        if sys.platform == 'darwin':
            subprocess.run(['/bin/cp', '-c', str(source), str(target)], check=True)
        else:
            shutil.copyfile(source, target)
        return target
    shutil.copytree(a.base, a.output, copy_function=clone)
    save_file({key: value.cpu() for key, value in state.items()}, str(a.output / 'numeric-residual.safetensors'))
    config = json.loads((a.output / 'rl_agent_config.json').read_text())
    metadata = config['doom_adaptation']['numeric_residual']
    metadata['weights_sha256'] = digest(a.output / 'numeric-residual.safetensors')
    metadata['data_sha256'] = cache['identity']['data']
    metadata['retention_finetune'] = dict(parent=a.base.name, parent_weights_sha256=digest(a.base / 'numeric-residual.safetensors'),
        retention_traces={str(path): digest(path) for path in run_paths}, trainer_sha256=digest(__file__),
        retain_all_observations=a.retain_all_observations, repair_categories=a.repair_category or ['route_finish_'],
        seed=771, epochs=a.epochs, best_epoch=best_epoch, learning_rate=a.learning_rate, retention_weight=a.retention_weight,
        margin_weight=a.margin_weight,trainable_block=a.trainable_block,
        trainable='existing numeric network from layer '+str(layer_start), targets='selected repair labels; frozen parent scores elsewhere',
        note='Same-map development with behavior cloning of the prior model outside corrected finish states. No runtime teacher.')
    (a.output / 'rl_agent_config.json').write_text(json.dumps(config, indent=2) + '\n')
    report = dict(initial=initial, best_epoch=best_epoch, final={split: evaluate(split) for split in initial},
                  seconds=time.monotonic() - start, history=history)
    (a.output / 'training-metrics.json').write_text(json.dumps(report, indent=2) + '\n')
    (a.output / 'best-epoch.json').write_text(json.dumps(dict(epoch=best_epoch, retention_finetune=True), indent=2) + '\n')
    archive = a.output / 'source' / 'training' / Path(__file__).name
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(__file__, archive)
    print('CHECKPOINT', a.output, json.dumps(report['final']), flush=True)


if __name__ == '__main__':
    main()
