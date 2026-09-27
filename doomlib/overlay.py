"""Dashboard видео: игровые кадры, состояние и реальные вероятности Laya."""
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont
from doomlib.combat import WEAPON_NAMES

COLORS = ['#ffad66', '#6bdacb', '#79adff', '#d6a1ff', '#ffd670', '#78d49c', '#ff8392', '#bfc8dd']


def font(size):
    for path in ['/System/Library/Fonts/Menlo.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


class Overlay:
    width, height = 1920, 1080

    def __init__(self, tactics, model):
        self.tactics = list(tactics)
        self.model = model
        self.fonts = {n: font(n) for n in [18, 22, 26, 34, 52]}

    def render(self, frame, state, decision, tactic, stats, pending):
        im = Image.new('RGB', (self.width, self.height), '#10151f')
        d = ImageDraw.Draw(im)
        def txt(x, y, text, size=22, color='#dce4f0'):
            d.text((x, y), str(text), font=self.fonts[size], fill=color)
        routing=decision.get('routing',{})
        decoding=routing.get('decoding',{})
        name='LAYA' if self.model=='doom-adapted' else self.model.upper()
        mode=('SAMPLED T='+str(decoding['temperature'])) if decoding.get('method')=='categorical' else ('ARGMAX' if decoding else 'WAITING')
        txt(38, 25, 'DOOM / '+name+(' / '+mode if self.model=='doom-adapted' else ''), 34)
        txt(1370, 34, routing.get('checkpoint',self.model), 18, '#6bdacb')
        if state.get('map_weapons_known'):txt(1370,60,'MAP WEAPON LOCATIONS: ON',18,'#8795aa')
        d.line((38, 84, 1882, 84), fill='#354153', width=2)
        im.paste(Image.fromarray(frame).resize((1120, 840), Image.Resampling.NEAREST), (40, 108))
        txt(1200, 112, f"{state['seconds']:06.1f}s", 52)
        txt(1550, 124, f"HP {state['hp']:3.0f}", 34, '#ff8392' if state['hp'] < 35 else '#78d49c')
        txt(1200, 191, f"AMMO {state['ammo']:.0f}  ARMOR {state['armor']:.0f}  KILLS {stats['kills']}", 26)
        txt(1200, 232, f"MODEL {'continue' if decision.get('answers',{}).get('command',{}).get('choice')=='continue' else tactic}", 22, '#6bdacb')
        movement='recover' if 'recover_same_goal' in state.get('reflexes',()) else state.get('execution',{}).get('movement') or ('route' if state.get('execution',{}).get('action') in ('pickup','open_door','use_switch','exit','explore') else 'still')
        txt(1200, 266, f"CONTROL {state.get('combat',{}).get('mode','explore')} / {WEAPON_NAMES.get(state['weapon'],str(state['weapon']))} / {movement}", 18, '#ffad66')
        label='ACTION PROBABILITY' if any(k in decision.get('answers',{}) for k in ('enemy','item','switch')) and 'continue' not in decision.get('answers',{}).get('command',{}).get('probabilities',{}) else 'ACTION PROBABILITY MASS (SUM)'
        txt(1200, 294, label, 18, '#8795aa')
        probs = decision.get('probabilities', {})
        for i, name in enumerate(self.tactics):
            y = 330 + i * 53
            p = probs.get(name, 0)
            txt(1200, y, name, 18, COLORS[i])
            txt(1805, y, f'{p:.0%}', 18)
            d.rounded_rectangle((1200, y + 26, 1865, y + 35), radius=4, fill='#253043')
            if p > 0:
                d.rounded_rectangle((1200, y + 26, 1200 + max(8, 665 * p), y + 35), radius=4, fill=COLORS[i])
        pending_label="WAIT DECISION" if decision.get("minimum_decision_delay_ticks",0) else "WAIT API"
        txt(1200, 780, f"CMD #{state.get('execution',{}).get('decision_id')}  {pending_label if pending else 'READY'}", 26)
        if decision.get('minimum_decision_delay_ticks',0):
            txt(1200, 820, f"RTT {decision.get('latency_ms',0):.0f} ms  APPLY {decision.get('decision_age_ms',0):.0f} ms", 22)
            txt(1200, 850, f"MIN DELAY {decision['minimum_decision_delay_ticks']} ticks  {decision.get('tokens',0)} tokens", 18)
        else:
            txt(1200, 832, f"{decision.get('latency_ms', 0):.0f} ms   {decision.get('tokens', 0)} tokens", 26)
        txt(1200, 883, f"DECISIONS {stats['decisions']}   ERRORS {stats['errors']}", 22)
        txt(1200, 925, 'KEYS '+(', '.join(state.get('keys',[])) or 'none')+f"   LEVELS {stats.get('levels_completed',0)}",18,'#ffd670')
        txt(42, 978, f"{state.get('map','')}   {len(state['enemies'])} known enemies   {len(state['items'])} items   {stats['deaths']} deaths", 26)
        w = state['walls']
        txt(970, 978, f"WALLS  L {w['left']:.1f}m / F {w['ahead']:.1f}m / R {w['right']:.1f}m", 22)
        resource=state.get('resource',{}).get('target')
        goal=resource['name'] if resource else state.get('navigation',{}).get('goal_kind','explore')
        target=state.get('combat',{}).get('target_name') or 'none'
        txt(42, 1030, f'TARGET {target}    RESOURCE / ROUTE {goal}', 18, '#8795aa')
        return im


class Recorder:
    def __init__(self, path, fps=35):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # -n защищает существующее видео от перезаписи.
        self.process = subprocess.Popen([
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-n',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '1920x1080', '-r', str(fps),
            '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(self.path),
        ], stdin=subprocess.PIPE)
        self.frames = 0

    def write(self, image):
        self.process.stdin.write(image.tobytes())
        self.frames += 1

    def close(self):
        self.process.stdin.close()
        if self.process.wait(timeout=60):
            raise RuntimeError('ffmpeg failed to finalize the video')
