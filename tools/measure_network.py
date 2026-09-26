"""RTT TCP и HTTP без инференса; не выдаём HTTP TTFB за чистое время модели."""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path
import requests
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()

TARGETS = [('openrouter', 'https://openrouter.ai/api/v1/models/typesafe/jev-1.13/endpoints'),
           ('laya', 'http://127.0.0.1:8000/health')]
TIMING_KEYS = ('http_code', 'time_namelookup', 'time_connect', 'time_appconnect',
               'time_starttransfer', 'time_total')


def curl_timing(url):
    if shutil.which('curl') is None:
        raise RuntimeError('curl is required for cold timing samples but was not found in PATH')
    p = subprocess.run(['curl', '--silent', '--show-error', '--noproxy', '*', '--max-time', '15',
                        '-o', os.devnull, '-w', '%{json}', url],
                       capture_output=True, text=True, check=True)
    d = json.loads(p.stdout)
    return {k: d[k] for k in TIMING_KEYS}


def measure(targets=TARGETS):
    result = {}
    for name, url in targets:
        cold = [curl_timing(url) for _ in range(8)]
        session = requests.Session()
        session.trust_env = False
        warm = []
        for i in range(9):
            start = time.perf_counter()
            r = session.get(url, timeout=(5, 15))
            r.raise_for_status()
            elapsed = (time.perf_counter() - start) * 1000
            if i:
                warm.append(elapsed)
        session.close()
        result[name] = {'url': url, 'cold_samples': cold, 'warm_http_no_inference_ms': warm,
                        'tcp_handshake_rtt_ms_p50': statistics.median((x['time_connect'] - x['time_namelookup']) * 1000 for x in cold),
                        'tls_handshake_ms_p50': statistics.median((x['time_appconnect'] - x['time_connect']) * 1000 for x in cold) if name == 'openrouter' else 0,
                        'warm_http_no_inference_ms_p50': statistics.median(warm)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='JSON file for the full measurement')
    args = parser.parse_args()
    data = measure()
    args.output.write_text(json.dumps(data, indent=2))
    print(json.dumps({k: {a: b for a, b in v.items() if a.endswith('p50')} for k, v in data.items()}, indent=2))


if __name__ == '__main__':
    main()
