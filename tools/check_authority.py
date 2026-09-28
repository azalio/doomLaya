"""Audit every non-idle motor frame against an accepted, unexpired model response."""
import argparse,hashlib,json
from pathlib import Path
from doomlib.combat import WEAPON_SLOTS
from doomlib.decision_questions import NAVIGATION_ACTIONS
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()


def check(run):
 run=Path(run);cfg=json.loads((run/'config.json').read_text());summary=json.loads((run/'summary.json').read_text())
 decisions=[json.loads(l) for l in (run/'decisions.jsonl').read_text().splitlines()]
 rows=[json.loads(l) for l in (run/'telemetry.jsonl').read_text().splitlines()]
 errors=[];accepted={};sequence_indices={}
 if cfg['args'].get('enemy_commitment_facts'):
  from doomlib.enemy_commitment import recorded_facts
  enemy_facts=recorded_facts(decisions)
 def require(condition,message):
  if not condition and len(errors)<30:errors.append(message)
 require(cfg.get('protocol')=='model-authority-v1','Wrong protocol')
 require(not (cfg.get('diagnostic_policy') or cfg.get('laya_health',{}).get('diagnostic_policy')),'Diagnostic reference policy is not model authority')
 require(not cfg['args']['dry'],'Dry run has no model authority')
 require(not cfg['args']['give'],'Nonstandard inventory')
 require(summary['errors']==0,'API errors occurred')
 require(summary['status']=='completed','Run did not finish cleanly')
 for name,digest in cfg['source_sha256'].items():
  require(hashlib.sha256((run/'source'/name).read_bytes()).hexdigest()==digest,'Source snapshot changed: '+name)
 for d in decisions:
  require(not d.get('routing',{}).get('diagnostic_policy'),'Diagnostic reference response is not a model decision')
  if cfg['args'].get('enemy_commitment_facts'):
   require(d['packet'].get('enemy_commitment')==enemy_facts[d['directive']['decision_id']],'Enemy acceptance facts differ from recorded model decisions')
  p=d['packet'];directive=d['directive'];key=d['answers']['command']['choice']
  if cfg['args'].get('enemy_sequences') and 'enemy' in p['questions']:
   from doomlib.enemy_sequences import with_enemy_sequences
   rebuilt=with_enemy_sequences(p)
   require(p.get('enemy_sequences')==rebuilt['enemy_sequences'],'Enemy sequence options changed')
   observed_ids={str(e['id']) for e in rows[d['tick']]['enemies']}
   require(set(p['targets']['enemy'])<=observed_ids,'Sequence contains an unobserved target')
   require(p['questions']['enemy']==rebuilt['questions']['enemy'],'Enemy sequence question changed')
  if cfg['args'].get('mask_unreachable_items'):
   require(all(i.get('reachable') is True for i in p.get('targets',{}).get('item',{}).values()),'Unreachable item remained selectable')
   require(all(i.get('reachable') is False for i in p.get('masked_unreachable_items',())), 'Reachable item was masked')
  if cfg['args'].get('look_gate'):
   from doomlib.look_questions import mix_look_answer
   answer=d['answers']['command'];parts=answer.get('look_gate')
   require(parts is not None,'Missing learned look-gate evidence')
   require(p['questions']['command'].get('look_observation')==p.get('look_facts'),'Look facts changed')
   if parts is not None:
    expected_mix=mix_look_answer(parts['base_answer'],parts['answer'],list(p['questions']['command']['criteria']))
    require(all(abs(answer['probabilities'][key]-value)<1e-6 for key,value in expected_mix['probabilities'].items()),'Command mixture probabilities replaced')
  if cfg['args'].get('floor_hazard_facts'):
   expected_floor=rows[d['tick']].get('floor_hazard')
   require(p.get('floor_hazard')==expected_floor,'Floor facts differ from request-time telemetry')
   require(p.get('look_facts',{}).get('standing_on_damaging_floor')==(expected_floor or {}).get('mapped_damaging_floor'),'Look gate floor fact changed')
  if p.get('decision_format') in ('factorized','committed'):
   from doomlib.decision_questions import decode
   expected=decode(d,p,directive['decision_id'])
  else:expected=p['commands'][key]
  require(directive['action']==expected['action'] and directive['target']==expected['target'],'Model target/action replaced')
  require(directive.get('target_sequence')==expected.get('target_sequence'),'Model firing sequence replaced')
  require(directive.get('movement')==expected.get('movement'),'Model combat movement replaced')
  require(directive.get('combat_target')==expected.get('combat_target'),'Secondary model combat target replaced')
  require(directive['weapon']==p['weapons'].get(d['answers']['weapon']['choice']),'Model weapon replaced')
  if 'subrequests' in d:
   required={'command','weapon'}|set(p['question_dependencies'].get(key,[]))
   require(set(d['answers'])==required,'Wrong conditional questions')
   combined={}
   for part in d['subrequests']:
    require(set(part['questions'])==set(part['answers']),'Conditional response keys differ')
    require(part['routing'].get('weights_sha256')==d['routing'].get('weights_sha256'),'Conditional checkpoint changed')
    combined.update(part['answers'])
   require(combined==d['answers'],'Conditional answers replaced')
   require(sum(part['tokens'] for part in d['subrequests'])==d['tokens'],'Conditional token usage mismatch')
   require(abs(sum(part.get('cost_usd',0) for part in d['subrequests'])-d.get('cost_usd',0))<1e-10,'Conditional cost mismatch')
   require(d['latency_ms']+1>=sum(part['latency_ms'] for part in d['subrequests']),'Conditional latency excludes a request')
  if d['applied']:
   accepted[directive['decision_id']]=d
   minimum=cfg['args'].get('minimum_decision_delay_ticks',0)
   if minimum:
    accepted_tick=round(d['game_seconds']*35)
    require(d.get('decision_accepted_tick')==accepted_tick,'Wrong decision acceptance tick')
    require(d.get('decision_age_ticks')==accepted_tick-d['tick'],'Wrong decision age')
    require(accepted_tick-d['tick']>=minimum,'Decision applied before configured minimum delay')
    require(d.get('minimum_decision_delay_ticks')==minimum,'Decision timing configuration changed')
 for index,s in enumerate(rows):
  a=s['buttons'];e=s['execution'];did=e['decision_id'];prefix=f"tick {s['tick']}: "
  require(s['tick']==index,prefix+'Missing tick')
  if did is None:
   require(not any(a),prefix+'Activity without an accepted decision');continue
  require(did in accepted,prefix+'Unknown decision ID')
  if did not in accepted:continue
  d=accepted[did];command=d['directive'];kind=command['action']
  require(d['episode']==s['episode'],prefix+'Decision from another episode')
  require(d['game_seconds']<=s['seconds']+.001,prefix+'Decision from future')
  require(s['tick']<=command['expires_tick'],prefix+'Expired decision')
  require(e['action']==kind,prefix+'Action override')
  from doomlib.enemy_sequences import advance_sequence
  selected=command['target']
  if kind=='attack':
   selected,sequence_indices[did]=advance_sequence(command,s['enemies'],sequence_indices.get(did,0))
   if 'target_sequence' in command:require(e.get('sequence_index')==sequence_indices[did],prefix+'Sequence cursor override')
  require(e['target_id']==((selected or {}).get('id')),prefix+'Target override')
  require(e.get('movement')==command.get('movement'),prefix+'Combat movement override')
  if kind=='attack':require(abs(a[4])<=cfg['args'].get('attack_turn_rate',9)+.00001,prefix+'Attack turn exceeds configured motor limit')
  if kind=='attack' and 'recover_same_goal' not in s.get('reflexes',[]):
   if a[1]:require(command.get('movement')=='backward',prefix+'Unauthorized backward attack')
   if a[2]:require(command.get('movement')=='strafe_left',prefix+'Unauthorized left strafe')
   if a[3]:require(command.get('movement')=='strafe_right',prefix+'Unauthorized right strafe')
  secondary=command.get('combat_target') if kind in NAVIGATION_ACTIONS else None
  require(e.get('combat_target_id')==(secondary['id'] if secondary else None),prefix+'Secondary combat target override')
  if a[5]:
   require(kind=='attack' or secondary is not None,prefix+'Unauthorized attack')
   if command['weapon'] is not None:require(s['weapon']==command['weapon'],prefix+'Firing a weapon other than the model requested')
   shot_target=e['target_id'] if kind=='attack' else e.get('combat_target_id')
   require(any(x['id']==shot_target and x.get('visible',True) for x in s['enemies']),prefix+'Shooting at unobserved/different enemy')
  if a[6]:require(kind in ('open_door','use_switch','exit'),prefix+'Unauthorized USE')
  for slot in range(1,8):
   if a[6+slot]:require(WEAPON_SLOTS.get(command['weapon'])==slot,prefix+'Unauthorized weapon selection')
  if kind=='look_back':
   require(not any(a[:4]+a[5:7]) and 0<=a[4]<=9,prefix+'Look-back motor override')
  if kind=='wait':require(not any(a[:7]),prefix+'Wait overridden')
 require(bool(accepted),'No accepted model decisions')
 require(summary['video_frames']==len(rows) if cfg['args']['record'] else True,'Video/telemetry frame mismatch')
 result={'pass':not errors,'frames':len(rows),'accepted_decisions':len(accepted),'errors':errors,
         'level_completed':summary['levels_completed']>0,'final_map':summary['final_map']}
 (run/'authority-verification.json').write_text(json.dumps(result,indent=2));return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('run');a=p.parse_args();r=check(a.run);print(json.dumps(r,indent=2));raise SystemExit(not r['pass'])
