"""Check that Laya receives every token of every offered choice, without inference."""
import argparse,collections,json,os,sys
from pathlib import Path
os.environ.setdefault('USE_TF','0');os.environ.setdefault('USE_TORCH','1');os.environ.setdefault('TOKENIZERS_PARALLELISM','false')


def audit(data,checkpoint,output):
    from transformers import AutoTokenizer
    from laya.common import build_sequence,render_options
    cfg=json.loads((checkpoint/'rl_agent_config.json').read_text());tok=AutoTokenizer.from_pretrained(checkpoint/'tokenizer',local_files_only=True);counts=collections.Counter();cases=[]
    for split in ('train','validation'):
        for index,row in enumerate(json.loads((data/(split+'.json')).read_text())):
            q=row['question'];internal=dict(t='choice',ins=q['instructions'],crit=q['criteria']);ids,markers=build_sequence(tok,row['state'],internal,cfg['max_len'],cfg['head_max_len']);options=render_options(internal)
            if len(markers)!=len(options):raise ValueError('Missing choice marker')
            for i,(key,option) in enumerate(zip(q['criteria'],options)):
                stop=markers[i+1] if i+1<len(markers) else ids.index(tok.sep_token_id,markers[i]);encoded=ids[markers[i]+1:stop];full=tok(' '+option,add_special_tokens=False)['input_ids'];counts[split+'_choices']+=1
                if encoded!=full:
                    counts[split+'_truncated']+=1
                    if len(cases)<10:cases.append(dict(split=split,index=index,key=key,full=option,retained=tok.decode(encoded)))
    report=dict(note=__doc__,data=str(data),checkpoint=str(checkpoint),counts=dict(counts),examples=cases,passed=not any(v for k,v in counts.items() if k.endswith('_truncated')))
    output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));return report['passed']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    raise SystemExit(not audit(a.data,a.checkpoint,a.output))
