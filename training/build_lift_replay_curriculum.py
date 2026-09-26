"""Balance recent failure corrections and prior demonstrations with factual lift routes."""
import argparse,collections,copy,hashlib,json,random,re
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--corrections',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(exist_ok=False)
    routes={}
    for line in (a.run/'telemetry.jsonl').open():
        state=json.loads(line)
        routes.update({str(s['id']):s['route_keys'] for s in state['switches'] if s.get('route_keys')})
        if routes:break
    heldout={1,4,7};seen=set();manifest=dict(note='Development replay. Recent episodes 1, 4, 7 held out from training; older development splits retained. No runtime teacher.',routes=routes,sources={},splits={})
    corrections=json.loads((a.corrections/'examples.json').read_text())
    manifest['sources'][str(a.corrections/'examples.json')]=hashlib.sha256((a.corrections/'examples.json').read_bytes()).hexdigest()
    for split in ('train','validation'):
        rng=random.Random(5171 if split=='train' else 5172);pool=[]
        for root in ('map2-goal-recovery-v2','map2-dagger-v2','map2-reachable-v2'):
            path=Path('training')/root/(split+'.json');manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();pool.extend(json.loads(path.read_text()))
        pool.extend(r for r in corrections if (r['source_episode'] in heldout)==(split=='validation'))
        groups=collections.defaultdict(list)
        for original in pool:
            row=copy.deepcopy(original);state=row['state'];keys=re.search(r'Collected keys: ([^.]+)',state);keys=keys.group(1).split(', ') if keys else []
            for oid,colors in routes.items():
                fact=' Upper route keys: '+', '.join(c+(' (collected)' if c in keys else ' (missing)') for c in colors)+'.'
                state=re.sub(r'(lift #'+oid+r' phase \w+ [0-9.]+m)(?! Upper route keys:)',lambda m:m[1]+fact,state)
                if row['kind']=='switch' and oid in row['question']['criteria'] and 'Upper route keys:' not in row['question']['criteria'][oid]:row['question']['criteria'][oid]+=fact
            row['state']=state
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:continue
            seen.add(key)
            if row['kind']=='command':group=(row['kind'],row['category'])
            elif row['kind']=='item':
                text=row['question']['criteria'][row['label']];name=text.split(';')[0].split(' ')[0]
                group=('item','health' if name in ('Medikit','Stimpack','HealthBonus') else 'armor' if 'Armor' in name else 'key' if 'Card' in name or 'Skull' in name else 'weapon' if name in ('Shotgun','SuperShotgun','Chaingun') else 'ammo')
            else:group=(row['kind'],'all')
            groups[group].append(row)
        rows=[]
        for (kind,category),values in groups.items():
            cap={'command':220,'item':320,'weapon':250,'movement':350,'switch':180,'enemy':100}[kind]
            if split=='validation':cap=max(25,cap//4)
            rng.shuffle(values);rows.extend(values[:cap])
        if split=='train':
            for row in rows:
                if row['kind']=='item' and rng.random()<.5:
                    pairs=list(row['question']['criteria'].items());rng.shuffle(pairs);row['question']['criteria']=dict(pairs)
                    row['option_order_augmented']=True
        rng.shuffle(rows);path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2))
        manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),kinds=dict(collections.Counter(r['kind'] for r in rows)),commands=dict(collections.Counter(r['label'] for r in rows if r['kind']=='command')))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest['splits'],indent=2))

if __name__=='__main__':main()
