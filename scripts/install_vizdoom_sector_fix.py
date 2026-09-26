"""Build pinned ViZDoom with a sector-line buffer large enough for its map limit."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

UPSTREAM='https://github.com/Farama-Foundation/ViZDoom.git'
REVISION='f771231811cd3be417f97230d009e0aa9d983ed6'
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python',default=sys.executable)
    args=parser.parse_args()
    python=str(Path(args.python).absolute())
    with tempfile.TemporaryDirectory(prefix='doomlaya-vizdoom-') as directory:
        source=Path(directory)/'source'
        subprocess.run(['git','clone','--depth','1','--branch','1.3.1',UPSTREAM,str(source)],check=True)
        revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
        if revision!=REVISION:raise RuntimeError('Unexpected upstream revision: '+revision)
        subprocess.run(['git','-C',str(source),'apply',str(ROOT/'patches/vizdoom-sector-lines.patch')],check=True)
        env=dict(os.environ)
        env['VIZDOOM_CMAKE_ARGS']=(env.get('VIZDOOM_CMAKE_ARGS','')+' -DCMAKE_POLICY_VERSION_MINIMUM=3.5').strip()
        if sys.platform=='darwin':
            prefix=Path(subprocess.check_output(['brew','--prefix','openal-soft'],text=True).strip())
            library=prefix/'lib/libopenal.dylib'
            if not library.is_file():raise RuntimeError('Install the build dependency: brew install openal-soft')
            env['VIZDOOM_CMAKE_ARGS']+=f' -DOPENAL_INCLUDE_DIR={prefix}/include/AL -DOPENAL_LIBRARY={library}'

        subprocess.run(['uv','pip','install','--python',python,'--no-deps','--reinstall',str(source)],check=True,env=env)
    print('Installed ViZDoom 1.3.1.post1 with complete sector geometry.')


if __name__=='__main__':main()
