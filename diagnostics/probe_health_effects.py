"""Ablate explicit health pickup effects on frozen observations; no gameplay."""
import argparse
import collections
import copy
import hashlib
import json
import statistics
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient

HEALTH_EFFECTS={'Medikit':(25,100),'Stimpack':(10,100),'HealthBonus':(1,200)}


def health_gain(name,hp):
    if name not in HEALTH_EFFECTS:return None
    amount,maximum=HEALTH_EFFECTS[name]
    return min(amount,max(0,maximum-hp))


def annotate(packet,variant):
    packet=copy.deepcopy(packet);hp=packet['observation']['hp'];facts=[]
    for oid,item in packet['targets'].get('item',{}).items():
        gain=health_gain(item['name'],hp)
        if gain is None:continue
        fact=f"Restores {gain:g} health at current HP {hp:g}."
        if variant=='options':packet['questions']['item']['criteria'][oid]+=' '+fact
        elif variant=='state':facts.append(item['name']+'#'+oid+': '+fact)
    if facts:packet['state']='Health pickup effects: '+'; '.join(facts)+'\n'+packet['state']
    return packet


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    groups=collections.defaultdict(list)
    for line in (a.run/'decisions.jsonl').open():
        row=json.loads(line);packet=row['packet'];hp=packet['observation']['hp'];items=packet.get('targets',{}).get('item',{})
        if not any(i['name'] in ('Medikit','Stimpack') and i.get('reachable') for i in items.values()):continue
        if len(items)<2:continue
        group='full' if hp>=100 else 'critical' if hp<35 else 'damaged'
        if not groups[group] or row['tick']-groups[group][-1]['tick']>=175:groups[group].append(row)
    cases=[]
    for group,rows in groups.items():
        cases.extend((group,rows[i]) for i in sorted({round(i*(len(rows)-1)/11) for i in range(12)}))
    client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();records=[]
    for index,(group,row) in enumerate(cases):
        results={}
        variants=['original','options','state'];variants=variants[index%3:]+variants[:index%3]
        for variant in variants:
            packet=annotate(row['packet'],variant);response=client.predict(packet['state'],{'item':packet['questions']['item']})
            if response['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
            chosen=packet['targets']['item'][response['answers']['item']['choice']];gain=health_gain(chosen['name'],packet['observation']['hp'])
            results[variant]=dict(choice=response['answers']['item'],target=chosen,health_gain=gain,latency_ms=response['latency_ms'])
        records.append(dict(group=group,tick=row['tick'],hp=row['packet']['observation']['hp'],**results))
        print(index+1,len(cases),group,{v:r['target']['name'] for v,r in results.items()},flush=True)
    client.session.close()
    counts={g:{v:dict(cases=sum(r['group']==g for r in records),zero_health_pickups=sum(r['group']==g and r[v]['health_gain']==0 for r in records),positive_health_pickups=sum(r['group']==g and r[v]['health_gain'] is not None and r[v]['health_gain']>0 for r in records)) for v in ('original','options','state')} for g in groups}
    result=dict(note='Selected frozen development observations. All candidates remain offered, including zero-gain health items. This is a rendering probe, not level-completion evidence or a ranking policy.',source_run=str(a.run),source_sha256={n:hashlib.sha256((a.run/n).read_bytes()).hexdigest() for n in ('config.json','decisions.jsonl')},routing=routing,health_effects=HEALTH_EFFECTS,counts=counts,records=records)
    a.output.write_text(json.dumps(result,indent=2));print(json.dumps(counts,indent=2))


if __name__=='__main__':main()
