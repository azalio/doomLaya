"""Offline expert labels for domain adaptation; never imported by the game executor."""
import argparse,collections,copy,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doomlib.policy import request
from doomlib.executor import Executor
from doomlib.items import utility
from doomlib.mission import Mission,map_data
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()
import vizdoom

parser=argparse.ArgumentParser();parser.add_argument('--output-dir',default='training/v3');parser.add_argument('--runs-dir',type=Path,default=Path('runs'));parser.add_argument('--sources',type=Path,help='JSON mapping train/validation to run folder names');args=parser.parse_args()
output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=True)
random.seed(7081)
mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP01'))
paths={
 'train':['20260921_223707_627955_paired-typed-decisions-42','20260921_223804_296993_paired-jev-42','20260921_224044_597293_paired-typed-decisions-43','20260921_223905_319051_paired-jev-43'],
 'validation':['20260921_224156_715030_paired-typed-decisions-44','20260921_224245_796456_paired-jev-44']}

if args.sources:paths=json.loads(args.sources.read_text())

def gold(packet,s):
 commands=packet['commands'];visible=[k for k,v in commands.items() if v['action']=='attack']
 candidates=[]
 for k,v in commands.items():
  if v['action']!='pickup':continue
  i=v['target'];score=utility(i,s)
  needed=(i['category']=='Weapon' and score>=100) or (i['category']=='Health' and s['hp']<75) or (i['category']=='Armor' and s['armor']<75) or (i['category']=='Ammo' and score>=80) or i['category'] in ('Key','Powerup')
  if needed and i['distance']<12:candidates.append((score-i['distance']*2,k))
 urgent=[(score,key) for score,key in candidates if commands[key]['target']['category']=='Health' and commands[key]['target']['distance']<6 and s['hp']<35]
 if urgent:command=max(urgent)[1]
 elif visible:command=visible[0]
 elif candidates:command=max(candidates)[1]
 elif s['door'] and s['door']['distance']<4:command='open_door'
 else:command='exit'
 usable={int(k) for k,v in s['inventory'].items() if v['owned'] and (int(k)==1 or v['ammo']>0)}
 slot=next(i for i in (6,3,4,2,1) if i in usable)
 weapon=next(k for k,v in packet['weapons'].items() if v==slot)
 return {'command':command,'weapon':weapon}

for split,names in paths.items():
 groups=collections.defaultdict(list)
 for name in names:
  rows=[json.loads(l) for l in (args.runs_dir/name/'telemetry.jsonl').read_text().splitlines()]
  memory=Executor();episode=None
  for row in rows:
   if episode!=row['episode']:memory=Executor();episode=row['episode']
   memory.observe(row,row['tick'])
   if row['tick']%14 or row['map']!='MAP01':continue
   row.pop('execution',None);row.pop('target_failures',None)
   variants=[row]
   if split=='train' and row['tick']%70==0:
    alt=copy.deepcopy(row);alt['hp']=20;alt['armor']=0;alt['inventory']['3']={'owned':1,'ammo':8};variants.append(alt)
    alt=copy.deepcopy(row)
    for entry in alt['inventory'].values():entry['ammo']=0
    variants.append(alt)
   for s in variants:
    packet=request(s,memory.known,mission);labels=gold(packet,s)
    for key,q in packet['questions'].items():
     choice=labels[key];category=packet['commands'][choice]['action'] if key=='command' else choice
     groups[(key,category)].append({'state':packet['state'],'question':q,'label':choice,'kind':key,'category':category,'source_run':name,'source_tick':row['tick'],'synthetic':s is not row})
 records=[]
 for group,values in groups.items():
  random.shuffle(values)
  if split=='train' and group==('command','open_door') and values:values=(values*20)[:140]
  records+=values[:(140 if split=='train' else 25)]
 random.shuffle(records)
 (output/f'{split}.json').write_text(json.dumps(records,indent=2))
 print(split,len(records),dict(collections.Counter((r['kind'],r['category']) for r in records)))
