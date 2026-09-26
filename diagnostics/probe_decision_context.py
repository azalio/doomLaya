"""Counterfactual rubric and geometric availability probes on saved mistakes."""
import argparse,collections,copy,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import LayaClient
from mission import Mission,map_data
from policy import request,decode
from decision_questions import dependencies
from training.map2_teacher import labels


def contextual(packet,keys):
    q=packet['questions']['command']['criteria']
    enemies=list(packet.get('targets',{}).get('enemy',{}).values())
    nearest=min((e['distance'] for e in enemies),default=None)
    def band(distance):return 'close' if distance<5 else 'medium' if distance<20 else 'far'
    if 'attack' in q and nearest is not None:q['attack']+=f' Nearest enemy: {band(nearest)}, {nearest:.1f}m.'
    current=packet['commands'].get('continue')
    if current:
        target=current.get('target') or {}
        if current['action']=='attack' and target.get('distance') is not None:q['continue']+=f" Enemy range: {band(target['distance'])}."
        if current['action']=='pickup' and 'reachable' in target:q['continue']+=' Path '+('reachable.' if target['reachable'] else 'unreachable.')
        if current['action']=='use_switch' and target.get('route_keys'):
            q['continue']+=' Upper route keys: '+', '.join(c+(' collected' if c in keys else ' missing') for c in target['route_keys'])+'.'
    return packet


def legal(packet):
    items=packet.get('targets',{}).get('item',{})
    valid={oid:i for oid,i in items.items() if i.get('reachable') is not False}
    packet.get('targets',{})['item']=valid
    if valid:packet['questions']['item']['criteria']={k:v for k,v in packet['questions']['item']['criteria'].items() if k in valid}
    else:
        packet['questions'].pop('item',None);packet['commands'].pop('pickup',None);packet['questions']['command']['criteria'].pop('pickup',None)
    current=packet['commands'].get('continue')
    if current and current['action']=='pickup' and str((current.get('target') or {}).get('id')) not in valid:
        packet['commands'].pop('continue');packet['questions']['command']['criteria'].pop('continue',None)
    packet['question_dependencies']=dependencies(packet)
    return packet


def explicit(packet):
    """Require explicit actions while preserving all other available choices."""
    from decision_questions import without_action_continuation
    without_action_continuation(packet)
    packet['question_dependencies']=dependencies(packet)
    return packet


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--variants',nargs='+',choices=['original','context','legal','both','explicit'],default=['original','context','legal','both']);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    ds=[json.loads(line) for line in (a.run/'decisions.jsonl').open()];needed={d['tick'] for d in ds};states={}
    for line in (a.run/'telemetry.jsonl').open():
        s=json.loads(line)
        if s['tick'] in needed:states[s['tick']]=s
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02',3))
    class Geometry:
        @staticmethod
        def nearest(point):return point
    selected=[];counts=collections.Counter();last={}
    for d in ds:
        if not d.get('applied') or d['tick'] not in states:continue
        s=copy.deepcopy(states[d['tick']]);packet=d['packet'];s['execution']=packet['observation']['execution']
        memory={i['id']:i for i in packet.get('targets',{}).get('item',{}).values()};reachable={(i['x'],i['y']) for i in memory.values() if i.get('reachable')}
        flat=request(s,memory,mission);gold=labels(flat,s,reachable,Geometry());expected=flat['commands'][gold['command']]
        key=lambda c:(c['action'],(c.get('target') or {}).get('id'))
        if key(expected)==key(d['directive']):continue
        case=d['directive']['action']+' -> '+expected['action']
        if counts[case]>=4 or d['tick']-last.get(case,-10000)<350:continue
        counts[case]+=1;last[case]=d['tick'];selected.append((d,s,expected,case))
    client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();results=[]
    for index,(d,s,expected,case) in enumerate(selected):
        variants={}
        for name in a.variants:
            packet=copy.deepcopy(d['packet'])
            if name in ('context','both'):contextual(packet,s['keys'])
            if name in ('legal','both'):legal(packet)
            if name=='explicit':explicit(packet)
            response=client.predict(packet['state'],packet['questions'],packet.get('question_dependencies'));actual=decode(response,packet,1)
            if response['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
            variants[name]=dict(actual=actual,correct=key(actual)==key(expected),answers=response['answers'],questions=packet['questions'])
        results.append(dict(tick=d['tick'],case=case,expected=expected,variants=variants))
        if index%10==0:print('PROBE',index+1,len(selected),flush=True)
    report=dict(note='Development input ablations; not gameplay. Legal variant removes only geometrically unreachable pickup commands.',routing=routing,cases=len(results),correct={v:sum(r['variants'][v]['correct'] for r in results) for v in a.variants},results=results)
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('routing','results')},indent=2))

if __name__=='__main__':main()
