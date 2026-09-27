"""Keep sequence labels and all target facts, remove unrelated route context offline."""
import argparse,collections,copy,hashlib,json
from pathlib import Path
from doomlib.compact_enemy import FORMAT,compact_enemy_input
from doomlib.enemy_sequences import QUESTION_FORMAT


def build(source,output):
    if output.exists():raise ValueError('Output exists')
    seen={};result={};removed=collections.Counter();sources={}
    for split in ('train','validation'):
        path=source/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();result[split]=[]
        for original in json.loads(path.read_text()):
            row=copy.deepcopy(original);row['raw_state']=row['state'];row['state'],row['question']=compact_enemy_input(row['state'],row['question'])
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key][1]!=row['label']:raise ValueError('Conflicting projected inputs')
                removed[split]+=1;continue
            seen[key]=(split,row['label']);result[split].append(row)
    output.mkdir();manifest=dict(question_format=QUESTION_FORMAT,input_projection=FORMAT,note='Same offline sequence labels and complete target question; only state projection changes to HP and inventory. Raw state retained for HTTP validation. Repeated projected inputs removed train-first. Same-map development, not live performance proof.',sources=sources,splits={},removed=dict(removed),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),projection_sha256=hashlib.sha256(Path('doomlib/compact_enemy.py').read_bytes()).hexdigest())
    for split,rows in result.items():
        path=output/(split+'.json');path.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),categories=dict(collections.Counter(row['category'] for row in rows)))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.data,a.output)
