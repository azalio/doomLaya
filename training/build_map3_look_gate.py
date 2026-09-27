"""Synthetic, observation-only supervision for a separate neural look gate."""
import argparse,collections,hashlib,itertools,json,random
from pathlib import Path
from doomlib.look_questions import look_gate_input


def build(output,balance_no_hit=False):
    if output.exists():raise ValueError('Output exists')
    splits={'train':[],'validation':[]}
    for loss in (0,1,3,5,9,15,30,60):
        ages=(None,) if loss==0 else (0,.3,.7,1.2,1.9)
        for age,count,checked,status in itertools.product(ages,range(4),(False,) if loss==0 else (False,True),('inactive','executing','arrived')):
            facts=dict(hp_loss=loss,latest_age_seconds=age,known_enemy_count=count,looked_after_hit=checked,status=status)
            state,question=look_gate_input(facts)
            # Offline supervision only. This rule is not used by runtime inference.
            scan=count==0 and (status=='executing' or (loss>0 and not checked and status!='arrived'))
            label='look_back' if scan else 'normal'
            split='validation' if loss in (9,30) or (loss==0 and count==3) else 'train'
            splits[split].append(dict(kind='command',state=state,question=question,label=label,category="no_recent_hit" if balance_no_hit and loss==0 else label,synthetic=True,source_type='synthetic_observed_look_facts',source_run='synthetic_observed_look_facts',look_facts=facts))
    output.mkdir();rng=random.Random(9313);manifest=dict(note='Synthetic combinations of recent HP loss, known enemy count and completed/current look status. No attacker coordinates, map route, hidden actors or live action rule. Entire loss magnitudes 9 and 30 held out; zero-loss enemy-count 3 held out. Tests this compact observation domain, not gameplay survival or new-map generalization.',splits={})
    for split,rows in splits.items():
        rng.shuffle(rows);p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),labels=dict(collections.Counter(r['label'] for r in rows)))
    if balance_no_hit:manifest['note']+=' Category weighting separates no_recent_hit states to prevent rare zero-loss states being ignored; all source rows/splits unchanged.'
    manifest['builder_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--balance-no-hit',action='store_true');a=p.parse_args();build(a.output,a.balance_no_hit)
