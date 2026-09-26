"""Build the read-only ACS weapon observer with the official ZDoom ACC compiler."""
import argparse
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--acc',type=Path,required=True);p.add_argument('--include',type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as work:
        compiled=Path(work)/'LAYAOBS.o'
        subprocess.run([str(a.acc.resolve()),'-i',str(a.include.resolve()),str(ROOT/'assets/weapon_sensor.acs'),str(compiled)],check=True)
        with zipfile.ZipFile(ROOT/'assets/weapon_sensor.pk3','w') as output:
            for name,data in [('LOADACS',b'LAYAOBS\n'),('acs/LAYAOBS.o',compiled.read_bytes())]:
                info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_STORED
                output.writestr(info,data)

if __name__=='__main__':main()
