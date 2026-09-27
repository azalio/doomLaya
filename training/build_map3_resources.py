"""Offline MAP03 resource/action labels on recorded model inputs; no live policy."""
import argparse,collections,copy,hashlib,json,random,re
from pathlib import Path
from doomlib.combat import AMMO_COST
from doomlib.items import WEAPONS
from training.build_goal_invariant_commands import change_goal

def without_goal(row):
    if row["kind"]=="command":return change_goal(row,None)
    result=copy.deepcopy(row)
    result["state"]="\n".join(line for line in row["state"].splitlines() if not line.startswith(("Current command:","Previous command result:")))
    result.update(synthetic=True,source_type="counterfactual_item_previous_goal",counterfactual_goal="none")
    return result



def candidates(packet):
    observation=packet['observation'];inventory=observation['inventory'];hp=observation['hp'];armor=observation.get('armor',0)
    usable={int(k) for k,v in inventory.items() if v['owned'] and v['ammo']>=AMMO_COST[int(k)]}
    strong=bool(usable.intersection({3,4,5,6,7,8}))
    result=[]
    for key,item in packet.get('targets',{}).get('item',{}).items():
        if not item.get('reachable'):continue
        name=item['name'];category=item['category'];distance=item['distance'];score=0
        if category=='Key':score=200
        elif category=='Health' and 'Bonus' not in name and hp<85:score=220 if hp<45 else 90
        elif category=='Armor' and 'Bonus' not in name and armor<60:score=150
        elif category=='Weapon':
            slot=WEAPONS.get(name);entry=inventory.get(str(slot),{})
            if slot in (3,4,6,8) and not entry.get('owned'):score=180 if not strong else 100
            elif slot in (3,8) and entry.get('owned') and entry['ammo']<20 and distance<20:score=110
        elif category=='Ammo':
            slot=3 if 'shell' in name.lower() else 2 if name in ('Clip','ClipBox') else None
            if slot and inventory[str(slot)]['owned'] and inventory[str(slot)]['ammo']<(20 if slot==3 else 70) and distance<20:score=110
        if score>2*distance:result.append((score-2*distance,key))
    return sorted(result,reverse=True),strong


def labels(packet):
    targets=packet.get('targets',{});options=packet['questions']['command']['criteria'];observation=packet['observation'];hp=observation['hp']
    resources,strong=candidates(packet);items=targets.get('item',{})
    nearest=min((e['distance'] for e in targets.get('enemy',{}).values()),default=float('inf'))
    current=observation.get('execution') or {};mechanisms=targets.get('switch',{})
    riding=any(m.get('kind')=='lift' and m.get('phase') in ('board','ride') and m['distance']<5 and current.get('action')=='use_switch' and str(current.get('target_id'))==key for key,m in mechanisms.items())
    urgent=[(score,key) for score,key in resources if items[key]['category']=='Health' and hp<35 and items[key]['distance']<6]
    upgrades=[(score,key) for score,key in resources if items[key]['category']=='Weapon' and not strong and items[key]['distance']<10]
    door=packet.get('commands',{}).get('open_door',{}).get('target') or {}
    keys=re.search(r'^Collected keys: (.*)\.',packet['state'],re.M)
    collected=set(keys[1].replace(',','').split()) if keys else set()
    chosen=resources[0][1] if resources else None
    if 'open_door' in options and 'A closed door blocks movement' in current.get('detail',''):action,category='open_door','blocked_door_prerequisite'
    elif riding:action,category='use_switch','continue_lift'
    elif urgent:action,category='pickup','urgent_health';chosen=max(urgent)[1]
    elif upgrades and nearest>=3:action,category='pickup','loaded_weapon';chosen=max(upgrades)[1]
    elif nearest<20 and 'attack' in options:action,category='attack','nearby_threat'
    elif 'open_door' in options and door.get('distance',999)<4:action,category='open_door','nearby_door'
    elif resources:action,category='pickup','useful_resource'
    elif 'exit' in options and collected>={'blue','red','yellow'}:action,category='exit','all_keys_exit'
    elif mechanisms and 'use_switch' in options:action,category='use_switch','continue_route'
    elif 'exit' in options:action,category='exit','available_exit'
    else:action,category='explore','other_route'
    result=[('command',action,category)] if action in options else []
    if chosen is not None:result.append(('item',chosen,items[chosen]['category'].lower()))
    return result


def build(runs,kind,replay,output):
    if output.exists():raise ValueError('Output exists')
    rng=random.Random(9307);pools={'train':collections.defaultdict(list),'validation':collections.defaultdict(list)};sources={};pairs=collections.Counter()
    for run in runs:
        path=run/'decisions.jsonl';sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for decision in map(json.loads,path.read_text().splitlines()):
            packet=decision['packet'];split='validation' if decision['episode']%3==0 else 'train'
            for question,label,category in labels(packet):
                if question!=kind:continue
                row=dict(kind=kind,label=label,category=category,state=packet['state'],question=copy.deepcopy(packet['questions'][kind]),source_run=run.name,source_tick=decision['tick'],source_episode=decision['episode'],source_type='offline_map03_resource_correction',synthetic=False)
                pools[split][category].append(row)
                if kind in decision['answers']:pairs[decision['answers'][kind]['choice']+' -> '+label]+=1
    seen={};result={};dropped=collections.Counter()
    for split in ('train','validation'):
        rows=[]
        for values in pools[split].values():
            rng.shuffle(values)
            for row in values[:250 if split=='train' else 90]:
                rows.append(row)
                if row['kind']=='item' or row['category'] in ('continue_route','useful_resource'):rows.append(without_goal(row))
        path=replay/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        groups=collections.defaultdict(list)
        for row in json.loads(path.read_text()):
            if row['kind']==kind:groups[row['label'] if kind=='command' else row.get('category','item')].append(row)
        old=[]
        for values in groups.values():rng.shuffle(values);old+=values[:80 if split=='train' else 35]
        clean=[]
        for row in rows+old:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:dropped['conflicting_duplicate']+=1
                else:dropped['duplicate']+=1
                continue
            seen[key]=row['label'];clean.append(row)
        rng.shuffle(clean);result[split]=clean
    output.mkdir();splits={}
    for split,rows in result.items():
        path=output/(split+'.json');path.write_text(json.dumps(rows,indent=2));splits[split]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    manifest=dict(note='Offline teacher-style resource scores and physical door/lift prerequisites on recorded Laya questions. MAP03 episode modulo 3 split; goal-removed variants stay with their source. Replay retains its old allocation; duplicates removed globally with new labels preferred within each split. Previous models saw overlapping map/run distributions: development fitting only, not independent generalization or proof of optimal labels. No runtime import.',kind=kind,sources=sources,splits=splits,dropped=dict(dropped),action_pairs=dict(pairs),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());(output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({k:v for k,v in manifest.items() if k!='action_pairs'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs='+',type=Path);p.add_argument('--kind',choices=['command','item'],required=True);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.runs,a.kind,a.replay,a.output)
