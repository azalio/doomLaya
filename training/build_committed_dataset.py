"""Supervised continuation decisions from successful demonstrations and failed rollouts."""
import argparse,collections,copy,hashlib,json,math,random,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import make_game,BUTTONS
from mission import Mission,map_data
from executor import Executor
from policy import request
from combat import WEAPON_NAMES
from decision_questions import factorize,with_commitment,split_command,TARGET_TYPES
from training.map2_teacher import labels as teacher_labels


def examples(packet,gold,source,tick,episode,refresh_attack=False,explicit_actions=False,pickup_combat=False,pickup_recent=False):
    selected=packet['commands'][gold['command']]
    action,target,movement=split_command(gold['command'])
    committed=with_commitment(factorize(packet))
    if refresh_attack:
        from decision_questions import refresh_attack_target
        committed=refresh_attack_target(committed)
    if explicit_actions:
        from decision_questions import without_action_continuation
        committed=without_action_continuation(committed)
    if pickup_combat:
        from decision_questions import with_pickup_combat
        committed=with_pickup_combat(committed,include_recent=pickup_recent)
    same=committed['commands'].get('continue')
    continuation=same and same['action']==action and (same.get('target') or {}).get('id')==(selected.get('target') or {}).get('id')
    choices={'command':'continue' if continuation else action,'weapon':gold['weapon']}
    if action in TARGET_TYPES and (not continuation or (refresh_attack and action=='attack')):choices[TARGET_TYPES[action]]=target
    if action=='attack':choices['movement']='continue' if movement==committed.get('current_movement') else movement
    if pickup_combat:
        visible=committed['combat_targets']
        choices['combat']=min(visible,key=lambda oid:visible[oid]['distance']) if visible else 'hold'
    for kind,label in choices.items():
        question=committed['questions'][kind]
        assert label in question['criteria'],(kind,label,question)
        yield dict(state=committed['state'],question=question,label=label,kind=kind,category=action,
                   source_run=source,source_tick=tick,source_episode=episode,synthetic=False,
                   source_type='offline_teacher_consistent_policy')


def previous_execution(rows,index):
    if index and rows[index-1]['episode']==rows[index]['episode']:return dict(rows[index-1]['execution'])
    return dict(action='wait',target_id=None,status='waiting',movement=None)


def demonstration_packets(path,mission):
    rows=[json.loads(x) for x in (path/'telemetry.jsonl').read_text().splitlines()]
    pairs=collections.defaultdict(dict)
    for row in json.loads((path/'examples.json').read_text()):pairs[row['source_tick']][row['kind']]=row
    objects={}
    for row in rows:
        for item in row['items']:objects[(row['episode'],str(item['id']))]=dict(item)
    markers={str(i['id']):i for i in mission.data['key_markers']+mission.data.get('weapon_markers',[])}
    for tick,pair in pairs.items():
        s=rows[tick];commands={};q=pair['command']['question']
        for key in q['criteria']:
            action,oid,movement=split_command(key);target=None
            if action=='attack':target=next(e for e in s['enemies'] if str(e['id'])==oid)
            elif action=='pickup':
                target=dict(markers[oid] if oid in markers else objects[(s['episode'],oid)])
                target['distance']=math.dist((target['x'],target['y']),(s['x'],s['y']))/32
                if oid in s.get('reachable_items',{}):target['reachable']=s['reachable_items'][oid]
            elif action=='use_switch':target=next(v for v in s['switches'] if str(v['id'])==oid)
            elif action=='open_door':target=s['door']
            commands[key]=dict(action=action,target=target)
            if movement and movement!='stationary':commands[key]['movement']=movement
        observation={k:s.get(k) for k in ('hp','armor','inventory','walls','motion_clearance','reachable_items')}
        observation['execution']=previous_execution(rows,tick)
        packet=dict(state=pair['command']['state'],questions={k:r['question'] for k,r in pair.items()},commands=commands,
                    weapons={WEAPON_NAMES[int(k)]:int(k) for k,v in s['inventory'].items() if v['owned']},observation=observation)
        yield packet,{k:r['label'] for k,r in pair.items()},tick,s['episode']


def demonstration(path,mission,refresh_attack=False):
    for packet,gold,tick,episode in demonstration_packets(path,mission):
        yield from examples(packet,gold,path.name,tick,episode,refresh_attack)


def corrections(path,mission,nav,split,refresh_attack=False):
    rows=[json.loads(x) for x in (path/'telemetry.jsonl').read_text().splitlines()]
    for index,line in enumerate((path/'decisions.jsonl').read_text().splitlines()):
        d=json.loads(line)
        if index%2 or (d['episode']%2==0)!=(split=='train'):continue
        s=copy.deepcopy(rows[d['tick']]);s['execution']=previous_execution(rows,d['tick'])
        memory={v['id']:dict(v) for v in d['packet']['targets'].get('item',{}).values()}
        nav.observe(s,s['tick']);reachable=nav.reachable((s['x'],s['y']))
        packet=request(s,memory,mission);gold=teacher_labels(packet,s,reachable,nav)
        yield from examples(packet,gold,path.name,s['tick'],s['episode'],refresh_attack)


def main():
    p=argparse.ArgumentParser();p.add_argument('--train',nargs='+',type=Path,required=True);p.add_argument('--validation',nargs='+',type=Path,required=True);p.add_argument('--corrections',nargs='*',type=Path,default=[]);p.add_argument('--output',type=Path,required=True);p.add_argument('--refresh-attack-target',action='store_true');a=p.parse_args()
    if set(a.train)&set(a.validation):raise ValueError('Demonstration split overlaps')
    a.output.mkdir(exist_ok=False)
    game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=48,show=False,sound=False),no_monsters=True);game.make_action([0]*len(BUTTONS),12)
    mission=Mission(map_data(game.get_doom_game_path(),'MAP02'));nav=Executor(game.get_state().sectors,mission).navigator;game.close()
    manifest={'refresh_attack_target':a.refresh_attack_target,'decision_format':'committed','label_source':'one offline teacher policy; never called by runtime',
              'note':'development data; validation selects checkpoints, not an independent gameplay benchmark',
              'source_hashes':{}}
    for path in a.train+a.validation+a.corrections:
        for name in ('telemetry.jsonl','examples.json','decisions.jsonl'):
            source=path/name
            if source.exists():manifest['source_hashes'][str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
    for split,paths in [('train',a.train),('validation',a.validation)]:
        rng=random.Random(1081 if split=='train' else 1082);groups=collections.defaultdict(list)
        for path in paths:
            for row in demonstration(path,mission,a.refresh_attack_target):groups[(row['kind'],row['category'] if row['kind']=='command' else row['label'] if row['kind']=='movement' else 'all')].append(row)
        for path in a.corrections:
            for row in corrections(path,mission,nav,split,a.refresh_attack_target):groups[(row['kind'],row['category'] if row['kind']=='command' else row['label'] if row['kind']=='movement' else 'all')].append(row)
        records=[]
        for (kind,category),candidates in groups.items():
            cap=({'command':300,'weapon':550,'enemy':350,'item':400,'switch':300,'movement':180}[kind] if split=='train' else {'command':60,'weapon':130,'enemy':80,'item':100,'switch':80,'movement':50}[kind])
            rng.shuffle(candidates);records.extend(candidates[:cap])
        rng.shuffle(records);path=a.output/(split+'.json');path.write_text(json.dumps(records,indent=2))
        manifest[split]={'rows':len(records),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kinds':dict(collections.Counter(r['kind'] for r in records)),
                         'command_labels':dict(collections.Counter(r['label'] for r in records if r['kind']=='command'))}
        print(split,manifest[split],flush=True)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
