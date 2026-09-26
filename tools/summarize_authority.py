"""Summarize model-owned gameplay, latency, cost and the integrity/acceptance distinction."""
import argparse,collections,json
from pathlib import Path
import numpy as np
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()


def summarize(paths):
 results=[]
 for path in paths:
  p=Path(path);cfg=json.loads((p/'config.json').read_text());summary=json.loads((p/'summary.json').read_text())
  rows=[json.loads(l) for l in (p/'telemetry.jsonl').read_text().splitlines()]
  decisions=[json.loads(l) for l in (p/'decisions.jsonl').read_text().splitlines()]
  events=[json.loads(l) for l in (p/'events.jsonl').read_text().splitlines()]
  verification=json.loads((p/'verification.json').read_text()) if (p/'verification.json').exists() else {}
  latencies=[d['latency_ms'] for d in decisions]
  ages=[(d['game_seconds']-d['tick']/35)*1000 for d in decisions if d['applied']]
  exit_event=next((e for e in events if e['event']=='level_finished'),None)
  gunshots=collections.Counter(str(s['weapon']) for s in rows if s['buttons'][5])
  results.append({'run':str(p.resolve()),'model':summary['model'],'seed':cfg['args']['seed'],
                  'level_completed':verification.get('level_completed',False),'exit_seconds':exit_event['game_seconds'] if exit_event else None,
                  'game_seconds':summary['game_seconds'],'wall_seconds':summary['wall_seconds'],'deaths':summary['deaths'],'kills':summary['kills'],
                  'resources':summary['resource_gains'],'shots_by_weapon_ticks':dict(gunshots),'errors':summary['errors'],
                  'requests':len(decisions),'stale_responses':sum(d['reason']=='stale' for d in decisions),
                  'http_p50_ms':float(np.percentile(latencies,50)),'http_p95_ms':float(np.percentile(latencies,95)),
                  'accepted_state_age_p50_ms':float(np.percentile(ages,50)) if ages else None,
                  'cost_usd':summary['external_api_cost_usd'],'cost_complete':summary['errors']==0,
                  'model_commands':dict(collections.Counter(d['choice'] for d in decisions)),
                  'model_weapons':dict(collections.Counter(d['answers']['weapon']['choice'] for d in decisions)),
                  'execution_status_ticks':dict(collections.Counter(s['execution']['status'] for s in rows)),
                  'experiment_valid':verification.get('experiment_valid',False),'acceptance_passed':verification.get('passed',False),
                  'navigation':verification.get('navigation'),
                  'checkpoints':cfg['laya_health']})
 return {'runs':results,'total_jev_cost_usd':sum(r['cost_usd'] for r in results if r['model']=='jev')}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('runs',nargs='+');p.add_argument('--output',required=True);a=p.parse_args()
 result=summarize(a.runs);Path(a.output).write_text(json.dumps(result,indent=2));print(json.dumps([{k:v for k,v in r.items() if k not in ('checkpoints','navigation')} for r in result['runs']],indent=2))
