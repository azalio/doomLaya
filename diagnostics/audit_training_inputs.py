"""Check the exact tokenizer inputs for lost facts and conflicting supervision."""
import argparse
import collections
import hashlib
import json
import os
import sys
from pathlib import Path
os.environ['USE_TF']='0';os.environ['USE_TORCH']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from transformers import AutoTokenizer
from laya.common import build_sequence


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    cfg=json.loads((a.checkpoint/'rl_agent_config.json').read_text())
    tok=AutoTokenizer.from_pretrained(a.checkpoint/'tokenizer',local_files_only=True)
    counts=collections.Counter();groups=collections.defaultdict(list);lost=[]
    for split in ('train','validation'):
        for i,row in enumerate(json.loads((a.data/(split+'.json')).read_text())):
            q=row['question'];keys=list(q['criteria'])
            ids,markers=build_sequence(tok,row['state'],dict(t='choice',ins=q['instructions'],crit=q['criteria']),cfg['max_len'],cfg['head_max_len'])
            key=hashlib.sha256(json.dumps([ids,markers]).encode()).hexdigest()
            groups[key].append(dict(split=split,index=i,kind=row['kind'],label=keys.index(row['label'])))
            counts[split+':'+row['kind']+':rows']+=1
            seps=[j for j,v in enumerate(ids) if v==tok.sep_token_id]
            retained=tok.decode(ids[seps[-2]+1:seps[-1]],skip_special_tokens=True)
            missing=[]
            for prefix in ('HP ','Inventory:','Collected keys:','Enemies:','Items:','Available mechanisms:','Reachable items:'):
                fact=next((line for line in row['state'].splitlines() if line.startswith(prefix)),None)
                if fact is None:continue
                counts[split+':'+row['kind']+':'+prefix+':present']+=1
                normalized=tok.decode(tok(fact,add_special_tokens=False)['input_ids'],skip_special_tokens=True)
                if normalized not in retained:
                    missing.append(prefix);counts[split+':'+row['kind']+':'+prefix+':truncated']+=1
            if missing:lost.append(dict(split=split,index=i,kind=row['kind'],missing=missing,retained=retained))
    collisions=[g for g in groups.values() if len({r['label'] for r in g})>1]
    overlaps=[g for g in groups.values() if {r['split'] for r in g}=={'train','validation'}]
    report=dict(note='Tokenizer-only check of exact effective inputs; no model or GPU inference.',data=str(a.data),counts=dict(counts),conflicting_inputs=collisions,split_overlaps=overlaps,lost=lost)
    a.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(rows=sum(v for k,v in counts.items() if k.endswith(':rows')),conflicting_inputs=len(collisions),split_overlaps=len(overlaps),truncated=dict((k,v) for k,v in counts.items() if k.endswith(':truncated'))),indent=2))


if __name__=='__main__':main()
