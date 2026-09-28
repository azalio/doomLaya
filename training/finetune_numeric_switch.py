"""Fit a mechanism score residual while freezing the complete original Laya head."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

os.environ.update(USE_TF='0', USE_TORCH='1', TOKENIZERS_PARALLELISM='false')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doomlib.numeric_switch import FORMAT, PROJECTION, FEATURES, observations, make_model


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'data', 'cache', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=500)
    parser.add_argument('--device', default='mps')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Output exists')
    import torch
    from safetensors.torch import save_file
    from laya import Agent
    from laya.common import build_sequence, collate_items, temp_bucket
    from doomlib.laya_runtime import enable_single_option_padding
    torch.manual_seed(771)
    torch.set_num_threads(2)
    rows = {split: json.loads((args.data / (split + '.json')).read_text()) for split in ('train', 'validation')}
    identity = dict(semantic_weights=digest(args.base / 'model.safetensors'), config=digest(args.base / 'rl_agent_config.json'),
                    data={split: digest(args.data / (split + '.json')) for split in rows})
    cache = json.loads(args.cache.read_text()) if args.cache.exists() else dict(identity=identity, answers={})
    if cache['identity'] != identity:
        raise ValueError('Semantic cache identity differs')
    agent = Agent(str(args.base), device=args.device)
    enable_single_option_padding(agent.model)
    for split, group in rows.items():
        if split in cache['answers']:
            continue
        answers = []
        for offset in range(0, len(group), 4):
            chunk = group[offset:offset + 4]
            items = []
            for row in chunk:
                question = agent._to_internal(row['question'])
                ids, markers = build_sequence(agent.tok, row['state'], question, agent.cfg['max_len'], agent.cfg['head_max_len'])
                if len(markers) != len(question['crit']):
                    raise ValueError('Truncated mechanism choices')
                items.append([dict(ids=ids, markers=markers, qtype=0)])
            batch = collate_items(items, agent.tok.pad_token_id)
            with torch.no_grad():
                logits = agent.model(*(batch[key].to(agent.device) for key in ('input_ids', 'attention_mask', 'marker_pos', 'marker_mask', 'qtype')))[0].float().cpu().double()
            for row, values in zip(chunk, logits):
                keys = list(row['question']['criteria'])
                temperature = agent.temperature_by_options.get(temp_bucket(0, len(keys)), agent.temperature[0])
                probabilities = (values[:len(keys)] / max(.001, float(temperature))).softmax(-1).tolist()
                answers.append(dict(probabilities={key: round(value, 4) for key, value in zip(keys, probabilities)}))
            if offset % 100 == 0:
                print('CACHE', split, offset, len(group), flush=True)
        cache['answers'][split] = answers
    differences = []
    for split, group in rows.items():
        for index in sorted({0, len(group) // 4, len(group) // 2, 3 * len(group) // 4, len(group) - 1}):
            row = group[index]
            actual = agent.predict(row['state'], {'switch': row['question']})['answers']['switch']
            differences.append(max(abs(value - cache['answers'][split][index]['probabilities'][key]) for key, value in actual['probabilities'].items()))
    if max(differences) > .001:
        raise ValueError('Frozen semantic cache differs from public inference')
    cache['api_probability_max_difference'] = max(differences)
    args.cache.write_text(json.dumps(cache, indent=2) + '\n')
    del agent
    if args.device == 'mps':
        torch.mps.empty_cache()
    maximum = max(len(row['question']['criteria']) for group in rows.values() for row in group)
    prepared, real_features = {}, []
    for split, group in rows.items():
        x = torch.zeros(len(group), maximum, len(FEATURES))
        b = torch.zeros(len(group), maximum)
        mask = torch.zeros(len(group), maximum, dtype=torch.bool)
        target = torch.zeros(len(group), dtype=torch.long)
        for index, row in enumerate(group):
            keys = list(row['question']['criteria'])
            values = observations(row['state'], row['question'])
            x[index, :len(keys)] = torch.tensor(values)
            b[index, :len(keys)] = torch.tensor([math.log(max(cache['answers'][split][index]['probabilities'][key], .0001)) for key in keys])
            mask[index, :len(keys)] = True
            target[index] = keys.index(row['label'])
            if split == 'train':
                real_features.extend(values)
        prepared[split] = x, b, mask, target
    values = torch.tensor(real_features)
    thresholds = {}
    for index in range(len(FEATURES)):
        unique = values[:, index].unique().sort().values
        if len(unique) > 3:
            thresholds[str(index)] = torch.quantile(unique, torch.linspace(0, 1, min(65, len(unique)))).tolist()
    spec = dict(format=FORMAT, input_projection=PROJECTION, features=list(FEATURES), thresholds=thresholds,
                hidden_size=96, probability_floor=.0001)
    model = make_model(spec)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.002, weight_decay=.0001)

    def evaluate(split):
        model.eval()
        with torch.no_grad():
            x, b, mask, y = prepared[split]
            correct = model(x, b).masked_fill(~mask, -1e4).argmax(-1) == y
            return float(correct.float().mean()), correct.tolist()

    initial = evaluate('validation')[0]
    best, best_epoch, history = initial, None, []
    start = time.monotonic()
    for epoch in range(args.epochs):
        model.train()
        x, b, mask, y = prepared['train']
        for indices in torch.randperm(len(x)).split(128):
            logits = model(x[indices], b[indices]).masked_fill(~mask[indices], -1e4)
            loss = torch.nn.functional.cross_entropy(logits, y[indices])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        accuracy, matched = evaluate('validation')
        history.append(dict(epoch=epoch + 1, accuracy=accuracy))
        if accuracy > best:
            best, best_epoch, best_correct = accuracy, epoch + 1, matched
            best_state = copy.deepcopy(model.state_dict())
        if epoch % 25 == 0:
            print('EPOCH', epoch + 1, 'validation', accuracy, 'best', best, flush=True)
    if best_epoch is None:
        raise ValueError('No improvement on unchanged validation')

    def clone(source, target):
        if sys.platform == 'darwin':
            subprocess.run(['/bin/cp', '-c', str(source), str(target)], check=True)
        else:
            shutil.copyfile(source, target)
        return target

    shutil.copytree(args.base, args.output, copy_function=clone)
    (args.output / 'numeric-residual.json').write_text(json.dumps(spec, indent=2) + '\n')
    save_file(best_state, str(args.output / 'numeric-residual.safetensors'))
    config = json.loads((args.output / 'rl_agent_config.json').read_text())
    config['doom_adaptation']['input_projection'] = PROJECTION
    config['doom_adaptation']['numeric_residual'] = dict(format=FORMAT,
        spec_sha256=digest(args.output / 'numeric-residual.json'), weights_sha256=digest(args.output / 'numeric-residual.safetensors'),
        semantic_parent=args.base.name, identity=identity, seed=771, epochs=args.epochs,
        learning_rate=.002, trainer_sha256=digest(__file__), inference_sha256=digest('doomlib/numeric_switch.py'),
        note='Frozen Laya text branch plus a learned mechanism score residual. No actor IDs in numeric features, no runtime teacher, no synthetic action scores. Same-map development validation.')
    (args.output / 'rl_agent_config.json').write_text(json.dumps(config, indent=2) + '\n')
    metrics = dict(base_accuracy=initial, best_accuracy=best, best_epoch=best_epoch,
                   correct=sum(best_correct), total=len(best_correct), semantic_scale=float(best_state['semantic_scale']),
                   seconds=time.monotonic() - start, cache_probability_max_difference=max(differences),
                   identity=identity, epochs=history)
    (args.output / 'training-metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
    (args.output / 'best-epoch.json').write_text(json.dumps(dict(
        epoch=best_epoch, validation={'switch': best}, numeric_residual=True), indent=2) + '\n')
    archived = args.output / 'source' / 'training' / Path(__file__).name
    archived.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(__file__, archived)
    print('CHECKPOINT', args.output, 'accuracy', best, 'epoch', best_epoch, flush=True)


if __name__ == '__main__':
    main()
