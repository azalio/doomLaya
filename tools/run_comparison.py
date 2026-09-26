"""Run original Laya, adapted Laya and Jev with identical gameplay settings."""
import argparse,json,signal,subprocess,sys
from datetime import datetime
from pathlib import Path
from diagnostics.verify_model_run import verify
from tools.summarize_authority import summarize
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()

p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=48);p.add_argument('--seconds',type=int,default=180)
p.add_argument('--models',nargs='+',default=['doom-adapted','typed-decisions','jev'],choices=['doom-adapted','typed-decisions','jev'])
a=p.parse_args();root=Path('runs')/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_decision-model-comparison');root.mkdir(parents=True)
print('SUITE',root.resolve(),flush=True);entries=[];hashes=None
for model in a.models:
 log=root/(model+'.log')
 command=[sys.executable,'agent.py','--model',model,'--seed',str(a.seed),'--seconds',str(a.seconds),'--record','auto','--stop-after-level','--tag',f'final-{model}-{a.seed}']
 with log.open('x') as output:
  process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT)
  try:code=process.wait()
  except KeyboardInterrupt:
   process.send_signal(signal.SIGINT);process.wait(timeout=30);raise
 lines=log.read_text(encoding='utf-8').splitlines()
 marker=next((line[4:] for line in lines if line.startswith('RUN ')),None)
 if marker is None:raise RuntimeError(f'{model} failed before game start; inspect {log}')
 run=Path(marker)
 config=json.loads((run/'config.json').read_text())
 if hashes is not None and hashes!=config['source_sha256']:raise RuntimeError('Gameplay source changed during comparison')
 hashes=config['source_sha256']
 result=verify(run);entry={'model':model,'seed':a.seed,'path':str(run),'process_code':code,'verified':result['passed'],'experiment_valid':result['experiment_valid'],'summary':result['summary']}
 entries.append(entry);(root/'runs.json').write_text(json.dumps(entries,indent=2))
 (root/'comparison.json').write_text(json.dumps(summarize([x['path'] for x in entries]),indent=2))
 print(json.dumps({k:entry[k] for k in ('model','path','verified','experiment_valid')}),flush=True)
 if not result['experiment_valid']:raise RuntimeError('Invalid experiment; inspect verification.json')
print('COMPLETE',root.resolve(),flush=True)
