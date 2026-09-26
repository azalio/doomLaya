"""Verify health gains against the installed engine in isolated inventory fixtures."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom as vzd
from agent import BUTTONS,make_game
from diagnostics.probe_health_effects import HEALTH_EFFECTS,health_gain


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    idle=[0]*len(BUTTONS);game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=54,show=False,sound=False),no_monsters=True)
    records=[]
    try:
        for hp in (50,95,100,150,200):
            for name in HEALTH_EFFECTS:
                game.new_episode();game.make_action(idle,12)
                if hp<100:
                    game.send_game_command('take health '+str(100-hp));game.make_action(idle,1)
                else:
                    for _ in range(hp-100):game.send_game_command('give HealthBonus');game.make_action(idle,1)
                before=game.get_game_variable(vzd.GameVariable.HEALTH)
                assert before==hp,(hp,before)
                game.send_game_command('give '+name);game.make_action(idle,1)
                after=game.get_game_variable(vzd.GameVariable.HEALTH);expected=health_gain(name,hp)
                assert after-before==expected,(name,hp,after,expected)
                records.append(dict(item=name,hp_before=before,hp_after=after,gain=after-before))
    finally:game.close()
    report=dict(note='Inventory-effect fixture, not gameplay. Monsters disabled; health set with console inventory commands.',engine_version=vzd.__version__,asset_sha256={n:hashlib.sha256((Path(vzd.__file__).parent/n).read_bytes()).hexdigest() for n in ('freedoom2.wad','vizdoom.pk3')},passed=True,records=records)
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
