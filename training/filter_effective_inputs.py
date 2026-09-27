"""Remove missing critical facts and duplicate effective tokenizer inputs offline."""
import argparse,collections,hashlib,json,os
from pathlib import Path
os.environ.setdefault('USE_TF','0');os.environ.setdefault('USE_TORCH','1');os.environ.setdefault('TOKENIZERS_PARALLELISM','false')


def filter_data(source,checkpoint,output):
    from transformers import AutoTokenizer
    from laya.common import build_sequence
    if output.exists():raise ValueError('Output exists')
    cfg=json.loads((checkpoint/'rl_agent_config.json').read_text());tok=AutoTokenizer.from_pretrained(checkpoint/'tokenizer',local_files_only=True)
    seen={};result={};removed=[];sources={}
    for split in ('train','validation'):
        path=source/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();result[split]=[]
        for index,row in enumerate(json.loads(path.read_text())):
            question=row['question'];ids,markers=build_sequence(tok,row['state'],dict(t='choice',ins=question['instructions'],crit=question['criteria']),cfg['max_len'],cfg['head_max_len'])
            separators=[i for i,value in enumerate(ids) if value==tok.sep_token_id];retained=tok.decode(ids[separators[-2]+1:separators[-1]],skip_special_tokens=True)
            missing=[]
            for prefix in ('HP ','Inventory:','Collected keys:'):
                fact=next((line for line in row['state'].splitlines() if line.startswith(prefix)),None)
                if fact and tok.decode(tok(fact,add_special_tokens=False)['input_ids'],skip_special_tokens=True) not in retained:missing.append(prefix)
            if missing:
                removed.append(dict(split=split,index=index,reason='critical_fact_truncated',facts=missing));continue
            key=hashlib.sha256(json.dumps([ids,markers]).encode()).hexdigest();label=tuple(list(question['criteria']).index(k) for k in row['target_ranking']) if 'target_ranking' in row else list(question['criteria']).index(row['label'])
            if key in seen:
                if seen[key][1]!=label:raise ValueError('Conflicting effective inputs: '+str((seen[key],split,index)))
                removed.append(dict(split=split,index=index,reason='effective_duplicate',original_split=seen[key][0]));continue
            seen[key]=(split,label);result[split].append(row)
    output.mkdir();manifest=dict(note='Tokenizer-only filtering, train before validation: remove incomplete HP/inventory/keys lines and repeated effective inputs. No relabeling. Development split limitations of the source dataset still apply.',source_manifest=json.loads((source/'manifest.json').read_text()),sources=sources,checkpoint_config_sha256=hashlib.sha256((checkpoint/'rl_agent_config.json').read_bytes()).hexdigest(),filter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),removed=removed,splits={})
    for split,rows in result.items():
        path=output/(split+'.json');path.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(dict(splits=manifest['splits'],removed=dict(collections.Counter(row['reason'] for row in removed))),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();filter_data(a.data,a.checkpoint,a.output)
