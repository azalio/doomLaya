"""Offline target/weapon corrections on recorded MAP03 questions; no runtime rules."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path
from doomlib.combat import AMMO_COST,WEAPON_NAMES


def gold(packet,rapid_fire=False):
    result=[]
    enemies=packet.get('targets',{}).get('enemy',{})
    if len(enemies)>1:
        def threat(key):
            e=enemies[key];distance=e['distance']
            visibility=0 if distance<2 else (1 if e.get('visible',True) else 2)
            return visibility,distance*(.65 if e['name'] in ('ShotgunGuy','Zombieman','ChaingunGuy') else 1)
        chosen=min(enemies,key=threat)
        result.append(('enemy',chosen,'visible_threat' if any(not e.get('visible',True) for e in enemies.values()) else 'visible_priority'))
    inventory=packet['observation']['inventory']
    usable={int(k) for k,v in inventory.items() if v['owned'] and v['ammo']>=AMMO_COST[int(k)]}
    order=(6,8,4,3,2,5,9,1) if rapid_fire else (6,8,3,4,2,5,9,1)
    weapon=next(k for k in order if k in usable)
    label=WEAPON_NAMES[weapon]
    if label in packet['questions']['weapon']['criteria']:
        category='chaingun_over_shotgun' if rapid_fire and weapon==4 and 3 in usable else ('shotgun_over_chaingun' if weapon==3 and 4 in usable else label)
        result.append(('weapon',label,category))
    return result


def build(runs,replay,output,rapid_fire=False):
    if output.exists():raise ValueError('Output exists')
    pools={'train':collections.defaultdict(list),'validation':collections.defaultdict(list)}
    manifest=dict(note='Offline corrections: prefer visible threats except an enemy within 2m; give visible hitscanners a distance weight of 0.65. Prefer loaded plasma, super shotgun, shotgun, chaingun, pistol, rocket launcher, chainsaw, fists. These rules are labels, never a live fallback. Same-map development validation; not a claim that this priority is universally optimal.',sources={},splits={})
    if rapid_fire:
        manifest['note']=manifest['note'].replace('plasma, super shotgun, shotgun, chaingun, pistol','plasma, super shotgun, chaingun, shotgun, pistol')
        manifest['weapon_priority']='rapid-fire-v1'
        manifest['evidence']='runs/map03-yellow-weapon-window.json: keeping chaingun through the recorded encounter preserved 48HP versus 3HP with shotgun; local counterfactual, not a universal weapon ranking.'
    for run in runs:
        path=run/'decisions.jsonl';manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for decision in map(json.loads,path.read_text().splitlines()):
            split='validation' if decision['episode']%3==0 else 'train'
            for kind,label,category in gold(decision['packet'],rapid_fire=rapid_fire):
                row=dict(kind=kind,label=label,category=category,state=decision['packet']['state'],question=copy.deepcopy(decision['packet']['questions'][kind]),source_run=run.name,source_tick=decision['tick'],source_episode=decision['episode'],source_type='offline_map03_combat_correction',synthetic=False)
                pools[split][kind+'/'+category].append(row)
    rng=random.Random(9303);seen={};result={}
    for split in ('train','validation'):
        rows=[]
        for values in pools[split].values():
            rng.shuffle(values);rows+=values[:260 if split=='train' else 100]
        path=replay/(split+'.json');manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        groups=collections.defaultdict(list)
        for row in json.loads(path.read_text()):
            if row['kind'] not in ('weapon','enemy'):continue
            if row['kind']=='enemy' and 'last seen' in row['state']:continue
            if row['kind']=='weapon' and 'chaingun' in row['question']['criteria']:continue
            groups[row['kind']].append(row)
        for values in groups.values():rng.shuffle(values);rows+=values[:200 if split=='train' else 80]
        clean=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting labels')
                continue
            seen[key]=row['label'];clean.append(row)
        rng.shuffle(clean);result[split]=clean
    output.mkdir()
    for split,rows in result.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),kinds=dict(collections.Counter(r['kind'] for r in rows)),categories=dict(collections.Counter(r['category'] for r in rows)))
    manifest['builder_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs='+',type=Path);p.add_argument('--replay',type=Path,default=Path('training/map2-explicit-v2'));p.add_argument('--output',type=Path,required=True);p.add_argument('--rapid-fire',action='store_true');a=p.parse_args();build(a.runs,a.replay,a.output,a.rapid_fire)
