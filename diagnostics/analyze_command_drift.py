"""Compare numeric command checkpoints on recorded, frozen semantic answers."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.update(USE_TF='0', USE_TORCH='1', TOKENIZERS_PARALLELISM='false')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doomlib.command_facts import stable_command_facts_input
from doomlib.numeric_command import ACTIONS, features, make_residual_model, semantic_logits
from training.route_finish import labels


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output exists')
    import torch
    from safetensors.torch import load_file
    torch.set_num_threads(2)
    models = []
    spec = json.loads((a.base / 'numeric-residual.json').read_text())
    for root in (a.base, a.candidate):
        if json.loads((root / 'numeric-residual.json').read_text()) != spec:
            raise ValueError('Different feature specifications')
        model = make_residual_model(spec)
        model.load_state_dict(load_file(str(root / 'numeric-residual.safetensors')))
        model.eval()
        models.append(model)
    report = dict(note='Offline counterfactual using recorded semantic scores; no gameplay or runtime teacher.',
                  base=a.base.name, candidate=a.candidate.name, run=str(a.run),
                  rows=0, replay_mismatches=0, changes=[], semantic_scales=[float(m.semantic_scale) for m in models])
    for d in map(json.loads, (a.run / 'decisions.jsonl').open()):
        packet = d['packet']
        answer = d['answers']['command']
        answer = answer.get('look_gate', {}).get('base_answer', answer)
        state, question = stable_command_facts_input(packet['state'], packet['questions']['command'])
        x = torch.tensor([features(dict(state=state, question=question), spec['item_names'])])
        b = torch.tensor([semantic_logits(answer['numeric_residual']['semantic_answer'])])
        mask = torch.tensor([[k in question['criteria'] for k in ACTIONS]])
        with torch.no_grad():
            logits = [m(x, b).masked_fill(~mask, -1e4)[0] for m in models]
        choices = [ACTIONS[int(z.argmax())] for z in logits]
        report['rows'] += 1
        report['replay_mismatches'] += int(choices[1] != answer['choice'])
        if choices[0] != choices[1]:
            report['changes'].append(dict(tick=d['tick'], episode=d['episode'], seconds=round(d['tick']/35,3),
                base=choices[0], candidate=choices[1], gold=labels(packet)[0],
                hp=packet['observation']['hp'], state=packet['state']))
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k!='changes'}))
    print('changed', len(report['changes']))
    for row in report['changes'][:12]:
        print(json.dumps({k:v for k,v in row.items() if k!='state'}))


if __name__ == '__main__':
    main()
