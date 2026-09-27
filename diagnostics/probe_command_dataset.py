"""Check command predictions against offline labels and retain category counts."""
import argparse, collections, hashlib, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import LayaClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', type=Path)
    parser.add_argument('--endpoint', default='http://127.0.0.1:8002/predict')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists')
    client = LayaClient(args.endpoint, 'doom-adapted')
    for attempt in range(60):
        try:
            health = client.health()
            break
        except Exception:
            if attempt == 59:
                raise
            time.sleep(1)
    rows = json.loads(args.data.read_text())
    cases = []
    for index, row in enumerate(rows):
        assert row['kind'] == 'command'
        answer = client.predict(row['state'], {'command': row['question']})
        assert answer['routing']['weights_sha256'] == health['weights_sha256']
        choice = answer['answers']['command']['choice']
        cases.append(dict(index=index, choice=choice, expected=row['label'], category=row['category'], correct=choice == row['label']))
        if index % 100 == 0:
            print(index, len(rows), flush=True)
    counts = collections.defaultdict(lambda: dict(correct=0, total=0))
    for case in cases:
        counts[case['category']]['correct'] += case['correct']
        counts[case['category']]['total'] += 1
    report = dict(note='API agreement with offline labels; not a gameplay success metric.',
                  data=str(args.data), data_sha256=hashlib.sha256(args.data.read_bytes()).hexdigest(),
                  routing=health, total=len(rows), correct=sum(r['correct'] for r in cases),
                  categories=dict(counts), cases=cases)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print({k:v for k,v in report.items() if k not in ('routing', 'cases')})


if __name__ == '__main__':
    main()
