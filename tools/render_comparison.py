"""Два игровых окна 1280×960 и крупная телеметрия в синхронном видео 2560×1440."""
import argparse
import json
from pathlib import Path
import subprocess

from PIL import Image,ImageDraw
from doomlib.overlay import font
from doomlib.combat import WEAPON_NAMES
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()


class Replay:
    def __init__(self,path):
        self.path=Path(path)
        self.config=json.loads((self.path/'config.json').read_text())
        self.summary=json.loads((self.path/'summary.json').read_text())
        self.rows=[json.loads(l) for l in (self.path/'telemetry.jsonl').read_text().splitlines()]
        self.decisions=[json.loads(l) for l in (self.path/'decisions.jsonl').read_text().splitlines()]
        events=[json.loads(l) for l in (self.path/'events.jsonl').read_text().splitlines()]
        self.finish=next((e['game_seconds'] for e in events if e['event']=='level_finished'),None)
        self.death_times=[e['game_seconds'] for e in events if e['event']=='death']
        self.error_times=[e['game_seconds'] for e in events if e['event']=='api_error']
        self.decoder=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-i',str(self.path/'video.mp4'),
                                       '-vf','crop=1120:840:40:108,scale=1280:960:flags=neighbor',
                                       '-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE)
        self.frame=None
        self.decision_index=0
        self.latest={}
        self.cost=0
        self.count=0

    def next(self,tick):
        index=min(tick,len(self.rows)-1)
        if tick<len(self.rows):
            size=1280*960*3
            data=self.decoder.stdout.read(size)
            if len(data)!=size:raise RuntimeError('Missing source video frame')
            self.frame=Image.frombytes('RGB',(1280,960),data)
        while self.decision_index<len(self.decisions) and self.decisions[self.decision_index]['game_seconds']<=self.rows[index]['seconds']:
            self.latest=self.decisions[self.decision_index]
            self.cost+=self.latest.get('cost_usd',0)
            self.count+=1;self.decision_index+=1
        if tick>=len(self.rows):
            self.cost=self.summary['external_api_cost_usd']
            self.count=len(self.decisions)
        return self.rows[index],self.frame,tick>=len(self.rows)

    def close(self):
        self.decoder.stdout.close()
        if self.decoder.wait()!=0:raise RuntimeError('Video decoder failed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('laya');p.add_argument('jev');p.add_argument('--output',required=True)
    a=p.parse_args();paths=[Path(a.laya),Path(a.jev)]
    configs=[json.loads((r/'config.json').read_text()) for r in paths]
    for field in ('map','seed','skill','seconds','interval','give','stop_after_level','decision_format','question_schedule',
                  'weapon_sensor','map_weapons','reachable_items','physical_facts','explicit_movement','movement_facts','mechanism_facts','combat_during_pickup','combat_during_navigation','refresh_attack_target','explicit_actions','pickup_recent_targets','item_resource_facts','inventory_events','ammo_events','mask_unreachable_items'):
        if configs[0]['args'].get(field)!=configs[1]['args'].get(field):raise ValueError('Different setup: '+field)
    if configs[0]['source_sha256']!=configs[1]['source_sha256']:raise ValueError('Different controller code')
    if configs[0]['wad_sha256']!=configs[1]['wad_sha256']:raise ValueError('Different WAD')
    if configs[0]['args']['model'] not in ('typed-decisions','doom-adapted') or configs[1]['args']['model']!='jev':raise ValueError('Expected Laya left and Jev right')
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    replays=[Replay(r) for r in paths];frames=max(len(r.rows) for r in replays)
    initial_map=configs[0]['args']['map'].upper()
    next_map=f'MAP{int(initial_map[3:])+1:02d}'
    encoder=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-n','-f','rawvideo','-pix_fmt','rgb24',
                              '-s','2560x1440','-r','35','-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','22',
                              '-pix_fmt','yuv420p','-movflags','+faststart',str(output)],stdin=subprocess.PIPE)
    fonts={n:font(n) for n in (19,22,26,34)}
    names=['LAYA / '+('Doom-adapted' if configs[0]['args']['model']=='doom-adapted' else 'original')+' / local MPS','JEV 1.13 / OpenRouter']
    colors=['#6bdacb','#ffad66']
    short=[('strafe_left_fire','left'),('strafe_right_fire','right'),('advance','advance'),('retreat','retreat'),
           ('pickup','pickup'),('patrol','patrol'),('turn_around','turn'),('open_door','door')]
    for tick in range(frames):
        im=Image.new('RGB',(2560,1440),'#10151f');d=ImageDraw.Draw(im)
        def text(x,y,value,size=22,color='#dce4f0'):
            d.text((x,y),str(value),font=fonts[size],fill=color)
        for i,r in enumerate(replays):
            x=i*1280;s,frame,frozen=r.next(tick);decision=r.latest
            text(x+26,15,names[i],34,colors[i])
            cost_label='API $0 (compute not priced)' if i==0 else f"API total ${r.summary['external_api_cost_usd']:.6f}"
            text(x+26,62,f"{s.get('map','')}   SEED {configs[i]['args']['seed']}   SKILL {configs[i]['args']['skill']}   {cost_label}",22)
            im.paste(frame,(x,105))
            if frozen or s.get('map')!=initial_map:
                label=f"{initial_map} COMPLETE {r.finish:.2f}s | {next_map}" if r.finish else 'TIME BUDGET REACHED'
                if frozen:label+=' | FROZEN'
                d.rectangle((x+12,117,x+1268,171),fill='#10151f')
                text(x+28,127,label,26,colors[i])
            y=1083
            text(x+24,y,f"t={s['seconds']:5.1f}s   HP {s['hp']:.0f}   ARMOR {s['armor']:.0f}   AMMO {s['ammo']:.0f}   KILLS {s['kills']}",26)
            text(x+24,y+40,f"MODEL: {s['tactic']}   CONTROL: {s.get('combat',{}).get('mode','')}   {WEAPON_NAMES.get(s['weapon'],s['weapon'])}",22,colors[i])
            age=max(0,s['seconds']-decision.get('tick',tick)/35)*1000
            text(x+24,y+77,f"HTTP {decision.get('latency_ms',0):.0f}ms incl. RTT   STATE AGE {age:.0f}ms   CALLS {r.count}   ID #{s.get('execution',{}).get('decision_id','-')}",22)
            resource=s.get('resource',{}).get('target');combat=s.get('combat',{})
            target=combat.get('target_name') or (resource['name'] if resource else s['tactic'])
            deaths=sum(t<=s['seconds'] for t in r.death_times)
            errors=sum(t<=s['seconds'] for t in r.error_times)
            text(x+24,y+114,f"TARGET {target}   ERRORS {errors}   DEATHS {deaths}   COST ${r.cost:.6f}",22)
            probs=decision.get('answers',{}).get('command',{}).get('probabilities',decision.get('probabilities',{}))
            short=sorted(((k,k) for k in probs),key=lambda pair:probs[pair[0]],reverse=True)[:4]
            selected_weapon=WEAPON_NAMES.get(s.get('execution',{}).get('weapon'),'keep')
            text(x+24,y+157,f"COMMAND {s.get('execution',{}).get('command',s['tactic'])} | WEAPON CHOICE {selected_weapon} | {s.get('execution',{}).get('status','')}",22,colors[i])
            text(x+24,y+186,f"FRAME RESPONSE #{decision.get('directive',{}).get('decision_id','-')} / {decision.get('reason','-')}: probabilities",19,'#9cacc4')
            for j,(key,label) in enumerate(short):
                col=j%4;row=j//4;bx=x+24+col*310;by=y+208+row*54;p=probs.get(key,0)
                text(bx,by,f'{label:7} {p:4.0%}',19)
                d.rectangle((bx,by+28,bx+285,by+34),fill='#293445')
                if p:d.rectangle((bx,by+28,bx+max(1,285*p),by+34),fill=colors[i])
        d.rectangle((1278,0,1282,1400),fill='#526078')
        text(24,1401,'Model chooses action, target and weapon | same motor executor and seed | 35 fps game time | HTTP includes RTT',22,'#9cacc4')
        encoder.stdin.write(im.tobytes())
        if tick%350==0:print(f'Rendered {tick/35:.0f}/{frames/35:.1f}s',flush=True)
    for r in replays:r.close()
    encoder.stdin.close()
    if encoder.wait()!=0:raise RuntimeError('Video encoder failed')
    metadata={'left':str(paths[0].resolve()),'right':str(paths[1].resolve()),'synchronization':'game seconds; 35 fps; no speed changes',
              'duration':frames/35,'frames':frames,'resolution':[2560,1440],'seed':configs[0]['args']['seed'],
              'code_sha256':configs[0]['source_sha256'],'completed_side':'frozen final frame with label',
              'jev_run_cost_usd':replays[1].summary['external_api_cost_usd']}
    output.with_suffix('.json').write_text(json.dumps(metadata,indent=2));print(output)

if __name__=='__main__':main()
