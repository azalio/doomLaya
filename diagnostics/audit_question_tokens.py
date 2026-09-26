"""Audit retained facts in real Laya inputs without loading model weights."""
import argparse
import collections
import json
import os
import sys
from pathlib import Path
os.environ['USE_TF']='0';os.environ['USE_TORCH']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from transformers import AutoTokenizer
from laya.common import build_sequence

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('run',type=Path);p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--resource-facts',action='store_true')
a=p.parse_args()
if a.output.exists():p.error('output exists')
cfg=json.loads((a.checkpoint/'rl_agent_config.json').read_text())
tok=AutoTokenizer.from_pretrained(a.checkpoint/'tokenizer',local_files_only=True)
counts=collections.Counter();rows=[]
for line in (a.run/'decisions.jsonl').open():
 try:d=json.loads(line)
 except json.JSONDecodeError:continue
 packet=d['packet']
 if a.resource_facts:
  from doomlib.resource_questions import with_resource_facts
  packet=with_resource_facts(packet)
 for kind,q in packet['questions'].items():
  ids,markers=build_sequence(tok,packet['state'],{'t':'choice','ins':q['instructions'],'crit':q['criteria']},cfg['max_len'],cfg['head_max_len'])
  separators=[i for i,x in enumerate(ids) if x==tok.sep_token_id]
  retained=tok.decode(ids[separators[-2]+1:separators[-1]],skip_special_tokens=True)
  missing=[]
  for prefix in ('HP ','Inventory:','Collected keys:'):
   fact=next((v for v in packet['state'].splitlines() if v.startswith(prefix)),None)
   if fact and fact not in retained:missing.append(prefix)
  lost=[]
  for index,(key,value) in enumerate(q['criteria'].items()):
   start=markers[index]+1;end=markers[index+1] if index+1<len(markers) else separators[-2]
   actual=tok.decode(ids[start:end],skip_special_tokens=True)
   expected=tok.decode(tok(key+': '+value,add_special_tokens=False)['input_ids'],skip_special_tokens=True)
   if actual.strip()!=expected.strip():lost.append(dict(option=key,expected=expected,retained=actual))
  counts[kind+':questions']+=1
  if missing:counts[kind+':state_truncated']+=1
  if lost:counts[kind+':options_truncated']+=1
  if missing or lost:rows.append(dict(tick=d['tick'],episode=d['episode'],kind=kind,missing=missing,options=lost,retained_state=retained))
report=dict(note='Tokenizer-only audit; no model weights or GPU work.',run=str(a.run),max_len=cfg['max_len'],head_max_len=cfg['head_max_len'],counts=dict(counts),rows=rows)
a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
