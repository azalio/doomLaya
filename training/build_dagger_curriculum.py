"""Mix offline corrections from a real rollout with earlier supervised examples."""
import argparse,collections,hashlib,json,random
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corrections',type=Path,required=True);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(exist_ok=False);manifest=dict(source_type='offline DAgger-style corrections; no runtime teacher',source_sha256={},correction_split='Every fifth 30-second block is validation; correlated development data, not an independent benchmark')
    source=a.corrections/'examples.json';corrections=json.loads(source.read_text());manifest['source_sha256'][str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
    training=set()
    for split in ('train','validation'):
        path=a.replay/(split+'.json');manifest['source_sha256'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();rows=json.loads(path.read_text());rng=random.Random(9718)
        if split=='train':
            groups=collections.defaultdict(list)
            for row in rows:groups[row['kind']].append(row)
            rows=[]
            for kind,limit in dict(command=450,item=300,weapon=300,movement=220,switch=100,enemy=100).items():
                rng.shuffle(groups[kind]);rows+=groups[kind][:limit]
        rows += [row for row in corrections if (((row['source_tick']//1050)%5==4)==(split=='validation'))]
        rng.shuffle(rows);seen=set();unique=[]
        for row in rows:
            key=json.dumps({k:row[k] for k in ('state','question')},sort_keys=True)
            if key in seen or (split=='validation' and key in training):continue
            seen.add(key);unique.append(row)
        if split=='train':training=seen
        path=a.output/(split+'.json');path.write_text(json.dumps(unique,indent=2))
        manifest[split]=dict(rows=len(unique),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),kinds=dict(collections.Counter(r['kind'] for r in unique)))
        print(split,manifest[split],flush=True)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
