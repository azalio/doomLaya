"""Offline MAP03 route corrections after resource collection; no runtime policy."""
import argparse
import collections
import copy
import hashlib
import json
import random
import re
from pathlib import Path
from training.build_map3_survival import label as local_label
from training.build_goal_invariant_commands import change_goal, goal_headers


def label(packet):
    local = local_label(packet)
    if local and local[1] in ('nearby_enemy','urgent_health'):
        return local
    door = packet.get('commands',{}).get('open_door',{}).get('target') or {}
    if 'open_door' in packet['questions']['command']['criteria'] and door.get('distance',999)<4 and not door.get('locked'):
        return 'open_door', 'blocking_door'
    if local:
        return local
    options = packet['questions']['command']['criteria']
    targets = packet.get('targets', {})
    if 'pickup' in options and any(i.get('reachable') and i['category']=='Key' for i in targets.get('item',{}).values()):
        return 'pickup', 'reachable_key'
    keys = re.search(r'^Collected keys: (.*)\.', packet['state'], re.M)
    collected = set(keys[1].replace(',','').split()) if keys else set()
    mechanisms = [s for s in targets.get('switch',{}).values() if not s.get('activated') and not s.get('locked') and not (s.get('route_keys') and set(s['route_keys']) <= collected)]
    if 'use_switch' in options and mechanisms:
        return 'use_switch', 'continue_route_with_supplies'
    return None


def sufficient_ammo(packet):
    result = copy.deepcopy(packet)
    inventory = result['observation']['inventory']
    names = {2:'pistol',3:'shotgun',4:'chaingun',5:'rocket_launcher',6:'plasma_rifle',7:'BFG',8:'super_shotgun'}
    counts = {2:120,3:40,4:120,5:20,6:120,7:120,8:40}
    for slot,name in names.items():
        if inventory[str(slot)]['owned']:
            inventory[str(slot)]['ammo'] = counts[slot]
            result['state'] = re.sub(r'\b'+name+r' [0-9.]+ ammo',name+' '+str(counts[slot])+' ammo',result['state'])
    # Shared pools remain internally consistent even when one of the guns is unowned.
    for a,b in ((2,4),(3,8),(6,7)):
        if inventory[str(a)]['owned'] or inventory[str(b)]['owned']:
            inventory[str(a)]['ammo'] = inventory[str(b)]['ammo'] = counts[a]
    return result


def build(run,replay,output):
    if output.exists():raise ValueError('Output exists')
    pools={'train':[],'validation':[]};pairs=collections.Counter();sources={}
    for name in ('config.json','decisions.jsonl','summary.json'):
        sources[str(run/name)]=hashlib.sha256((run/name).read_bytes()).hexdigest()
    for d in map(json.loads,(run/'decisions.jsonl').read_text().splitlines()):
        split='train' if d['episode']%2 else 'validation'
        for synthetic,packet in ((False,d['packet']),(True,sufficient_ammo(d['packet']))):
            gold=label(packet)
            if not gold or (synthetic and gold[1]!='continue_route_with_supplies'):continue
            action,reason=gold
            if not synthetic:pairs[d['choice']+' -> '+action]+=1
            row=dict(kind='command',category=reason,label=action,state=packet['state'],question=copy.deepcopy(packet['questions']['command']),source_run=run.name,source_tick=d['tick'],source_episode=d['episode'],source_type='counterfactual_sufficient_ammo' if synthetic else 'offline_map03_route_correction',synthetic=synthetic,model_choice=d['choice'])
            pools[split].append(row)
            if reason=='continue_route_with_supplies':
                pools[split].append(change_goal(row,None))
                goals=goal_headers(row).get('pickup',[])
                if goals:pools[split].append(change_goal(row,goals[0]))
    rng=random.Random(9302);seen={};result={}
    manifest=dict(note='Offline local resource/combat labels plus missing-key mechanisms when no useful nearby resource or enemy takes priority. Exact recorded root questions. MAP03 odd episodes train, even episodes validation; counterfactual sufficient-ammo states and goal variants remain in the parent split. Previous dataset retains its train/validation allocation. Same-map development validation, not generalization. No runtime import.',sources=sources,action_pairs=dict(pairs),splits={})
    for split in ('train','validation'):
        groups=collections.defaultdict(list)
        for row in pools[split]:groups[row['category']].append(row)
        rows=[]
        for values in groups.values():
            rng.shuffle(values);rows.extend(values[:160 if split=='train' else 60])
        path=replay/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        old=collections.defaultdict(list)
        for row in json.loads(path.read_text()):old[row['label']].append(row)
        for values in old.values():
            rng.shuffle(values);rows.extend(values[:80 if split=='train' else 40])
        clean=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting labels')
                continue
            seen[key]=row['label'];clean.append(row)
        rng.shuffle(clean);result[split]=clean
        manifest['splits'][split]=dict(rows=len(clean),labels=dict(collections.Counter(r['label'] for r in clean)),categories=dict(collections.Counter(r['category'] for r in clean)))
    output.mkdir()
    for split,rows in result.items():
        path=output/(split+'.json');path.write_text(json.dumps(rows,indent=2));manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest['builder_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--replay',type=Path,default=Path('training/map3-survival-v1'));p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.run,a.replay,a.output)
