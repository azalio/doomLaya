"""Run MAP01, MAP02 and MAP03 sequentially with one frozen model manifest."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from doomlib import ensure_utf8_stdio
ensure_utf8_stdio()
CASES=(('MAP01',48,180),('MAP02',54,1800),('MAP03',54,1200))
FLAGS=['--decision-format','committed','--question-schedule','conditional',
       '--interval','0.5','--minimum-decision-delay-ticks','0',
       '--explicit-actions','--explicit-movement','--movement-facts','--movement-obstacle-facts',
       '--refresh-attack-target','--enemy-visibility-facts','--enemy-commitment-facts',
       '--enemy-sequences','--look-gate','--floor-hazard-facts','--attack-turn-rate','9',
       '--weapon-sensor','--map-weapons','--reachable-items','--mechanism-facts',
       '--combat-during-navigation','--pickup-recent-targets','--inventory-events','--ammo-events',
       '--mask-unreachable-items','--skill','3','--record','auto','--stop-after-level']


def identity(endpoint):
    url=endpoint.rsplit('/',1)[0]+'/health'
    with urllib.request.urlopen(url,timeout=20) as response:
        data=json.load(response)
    if data.get('status')!='ok' or not data.get('weights_sha256'):
        raise ValueError('Model is not ready or lacks identity')
    return {k:data.get(k) for k in ('weights_sha256','question_heads','inference_precision','laya_source_commit','decoding')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--endpoint',default='http://127.0.0.1:8003/predict')
    p.add_argument('--tag',default='v031-regression')
    p.add_argument('--first-map',choices=[case[0] for case in CASES],help='Run this case first; every map and its original budget remain required')
    p.add_argument('--keep-going',action='store_true',help='Run later maps even after a failed completion check')
    p.add_argument('--enemy-events',action='store_true',help='Request model replanning when a new visible enemy appears')
    p.add_argument('--minimum-decision-delay-ticks',type=int,default=0,help='Minimum response age; 0 applies each real response as soon as it arrives')
    a=p.parse_args()
    if not 0<=a.minimum_decision_delay_ticks<70:p.error('--minimum-decision-delay-ticks must be in 0..69')
    flags=FLAGS+(['--enemy-events'] if a.enemy_events else [])
    flags[flags.index('--minimum-decision-delay-ticks')+1]=str(a.minimum_decision_delay_ticks)
    cases=sorted(CASES,key=lambda case:case[0]!=a.first_map) if a.first_map else CASES
    tag=re.sub(r'[^\w-]','_',a.tag)
    out=ROOT/'runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+tag+'_suite')
    out.mkdir()
    manifest=identity(a.endpoint)
    report=dict(started_at=datetime.now(timezone.utc).isoformat(),model=manifest,
                cases=[dict(map=m,seed=s,seconds=t,skill=3) for m,s,t in cases],
                common_flags=flags,minimum_next_map_ticks=105,results=[],status='running')
    def save():
        (out/'suite.json').write_text(json.dumps(report,indent=2)+'\n')
    save();print('SUITE',out,flush=True)
    child=None
    try:
        for map_name,seed,seconds in cases:
            if identity(a.endpoint)!=manifest:raise ValueError('Model changed before '+map_name)
            report['active_map']=map_name;save()
            command=[sys.executable,str(ROOT/'agent.py'),'--model','doom-adapted','--endpoint',a.endpoint,
                     *flags,'--map',map_name,'--seed',str(seed),'--seconds',str(seconds),
                     '--tag',f'{tag}-{map_name.lower()}-seed{seed}']
            log=out/(map_name.lower()+'.log')
            print('START',map_name,'budget',seconds,flush=True)
            with log.open('w') as handle:
                child=subprocess.Popen(command,cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
                report['active_pid']=child.pid;save();code=child.wait();child=None
            matches=re.findall(r'^RUN (.+)$',log.read_text(encoding='utf-8'),re.M)
            if code or len(matches)!=1:raise RuntimeError(f'{map_name} failed; inspect {log}')
            run=Path(matches[0]);verify_log=out/(map_name.lower()+'-verify.log')
            if identity(a.endpoint)!=manifest:raise ValueError('Model changed during '+map_name)
            with verify_log.open('w') as handle:
                verified=subprocess.run([sys.executable,'-m','tools.verify_run',str(run)],cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
            verification=json.loads((run/'verification.json').read_text(encoding='utf-8'));summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
            verification.pop('summary',None)
            with (run/'decisions.jsonl').open(encoding='utf-8') as decisions:
                for line in decisions:
                    routing=json.loads(line)['routing']
                    if routing['weights_sha256']!=manifest['weights_sha256'] or routing['question_heads']!=manifest['question_heads']:
                        raise ValueError('Decision model differs from suite manifest')
            passed=verification['experiment_valid'] and verification['authority']['pass'] and verification['level_completed']
            result=dict(map=map_name,run=str(run.relative_to(ROOT)),passed=passed,
                        verifier_exit=verified.returncode,verification=verification,
                        summary={k:v for k,v in summary.items() if not isinstance(v,(dict,list)) and k!='run'})
            report['results'].append(result);save()
            print('RESULT',map_name,'completed',verification['level_completed'],'experiment_valid',verification['experiment_valid'],flush=True)
            if not passed and not a.keep_going:
                report.update(status='stopped_after_failure',passed=False)
                report.pop('active_map',None);report.pop('active_pid',None);save()
                print('RESULTS',out/'suite.json',flush=True)
                return 1
        report.update(status='completed',passed=all(r['passed'] for r in report['results']))
        report.pop('active_map',None);report.pop('active_pid',None);save()
        print('RESULTS',out/'suite.json',flush=True)
        return 0 if report['passed'] else 1
    except BaseException as exc:
        if child is not None and child.poll() is None:
            # Let the game finalize telemetry/video and mark the run interrupted.
            if sys.platform != "win32": child.send_signal(signal.SIGINT)
            else: child.terminate()
            try:child.wait(timeout=30)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        report.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc));save()
        raise


if __name__=='__main__':raise SystemExit(main())
