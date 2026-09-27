"""Project recorded firing-order labels to a learned listwise target ranker."""
import argparse,collections,copy,hashlib,json
from pathlib import Path
from doomlib.enemy_ranking import FORMAT,STOP,ranking_input


def build(source,output):
    if output.exists():raise ValueError('Output exists')
    result={};seen={};removed=collections.Counter();sources={}
    for split in ('train','validation'):
        p=source/(split+'.json');sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();result[split]=[]
        for original in json.loads(p.read_text()):
            row=copy.deepcopy(original);row['raw_state']=row.get('raw_state',row['state']);row['sequence_question']=copy.deepcopy(row['question']);row['sequence_label']=row['label']
            row['state'],row['question'],orders=ranking_input(row['raw_state'],row['question'])
            if orders!=row['enemy_sequences']:raise ValueError('Sequence mapping differs')
            row['target_ranking']=orders[row['label']]+[STOP];row['label']=row['target_ranking'][0]
            key=json.dumps([row['state'],row['question']])
            if key in seen:
                if seen[key]!=row['target_ranking']:raise ValueError('Conflicting effective rankings')
                removed[split]+=1;continue
            seen[key]=row['target_ranking'];result[split].append(row)
    output.mkdir();manifest=dict(question_format='enemy-sequence-v1',input_projection=FORMAT,training_objective='nonempty-listwise-v1',note='Same observed targets and offline sequence labels. The neural head scores individual targets plus an end-of-sequence option. A Plackett-Luce decoder maps those scores to probabilities of all original nonempty firing sequences. No distance ranking or live teacher rule in decoding. Different recorded source runs held out; same-map development only.',sources=sources,splits={},removed=dict(removed),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),projection_sha256=hashlib.sha256(Path('doomlib/enemy_ranking.py').read_bytes()).hexdigest())
    for split,rows in result.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.data,a.output)
