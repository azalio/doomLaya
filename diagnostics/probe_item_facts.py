"""Ablate factual item descriptions on recorded model mistakes; no gameplay."""
import argparse,collections,copy,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import LayaClient
from mission import Mission,map_data
from policy import request
from training.map2_teacher import labels
from items import weapon_slot


def describe(item,observation,keys):
    name=item['name'];category=item['category'];inv=observation['inventory']
    access='reachable' if item.get('reachable') else 'unreachable'
    distance=f"{item['distance']:.1f}m"
    if category=='Weapon':
        slot=weapon_slot(name,inv);owned=bool(slot and inv[str(slot)]['owned'])
        name=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',name).lower()
        return f"{name}; {'owned' if owned else 'new gun'}; {access}; {distance}."
    if category=='Health':
        limit=200 if 'Bonus' in name or 'sphere' in name.lower() else 100
        return f"{name}; health {observation['hp']:.0f}/{limit}; {access}; {distance}."
    if category=='Armor':
        limit=100 if name in ('GreenArmor','BasicArmor') else 200
        return f"{name}; armor {observation['armor']:.0f}/{limit}; {access}; {distance}."
    if category=='Ammo':
        slot=3 if 'shell' in name.lower() else 5 if 'rocket' in name.lower() else 6 if 'cell' in name.lower() else 2
        resource={2:'bullets',3:'shells',5:'rockets',6:'cells'}[slot]
        return f"{name}; {resource} carried {inv[str(slot)]['ammo']}; {access}; {distance}."
    if category=='Key':
        color=next((c for c in ('red','blue','yellow') if name.lower().startswith(c)),name)
        return f"{color} key; {'collected' if color in keys else 'missing'}; {access}; {distance}."
    return f"{name}; {category}; {access}; {distance}."


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    decisions=[json.loads(x) for x in (a.run/'decisions.jsonl').read_text().splitlines()]
    needed={d['tick'] for d in decisions};states={}
    for line in (a.run/'telemetry.jsonl').open():
        s=json.loads(line)
        if s['tick'] in needed:states[s['tick']]=s
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02',3))
    class Geometry:
        @staticmethod
        def nearest(point):return point
    cases=[];counts=collections.Counter();last=-10000
    for d in decisions:
        if d['tick']-last<175:continue
        s=copy.deepcopy(states[d['tick']]);packet=d['packet'];s['execution']=packet['observation']['execution']
        memory={i['id']:i for i in packet.get('targets',{}).get('item',{}).values()}
        reachable={(i['x'],i['y']) for i in memory.values() if i.get('reachable')}
        flat=request(s,memory,mission);gold=labels(flat,s,reachable,Geometry());selected=flat['commands'][gold['command']]
        if selected['action']!='pickup':continue
        item=selected['target'];category=item['category']
        if counts[category]>=10:continue
        counts[category]+=1;last=d['tick'];cases.append((d,s,str(item['id']),category))
    client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();results=[]
    for d,s,expected,category in cases:
        packet=d['packet'];q=copy.deepcopy(packet['questions']['item']);answers={}
        for variant in ('original','facts'):
            if variant=='facts':q['criteria']={oid:describe(i,packet['observation'],s['keys']) for oid,i in packet['targets']['item'].items()}
            r=client.predict(packet['state'],{'item':q})
            if r['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
            answers[variant]=r['answers']['item']
        results.append(dict(tick=d['tick'],category=category,expected=expected,**answers))
    score={v:sum(r[v]['choice']==r['expected'] for r in results) for v in ('original','facts')}
    report=dict(note='Factual input ablation on development rollout; no gameplay',routing=routing,cases=len(results),categories=dict(counts),correct=score,results=results)
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('routing','results')},indent=2))

if __name__=='__main__':main()
