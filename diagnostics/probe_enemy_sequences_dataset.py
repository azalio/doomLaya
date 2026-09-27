"""Check model-selected firing sequences against held-out offline labels."""
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
    assert health['question_heads']['enemy']['question_format'] == 'enemy-sequence-v1'
    rows = json.loads(args.data.read_text())
    cases = []
    for index, row in enumerate(rows):
        assert row['kind'] == 'enemy'
        answer = client.predict(row.get('raw_state', row['state']), {'enemy': row['question']})
        assert answer['routing']['weights_sha256'] == health['weights_sha256']
        choice = answer['answers']['enemy']['choice']
        selected = row['enemy_sequences'][choice]
        expected = row['enemy_sequences'][row['label']]
        assert selected and len(selected) == len(set(selected))
        cases.append(dict(index=index, choice=choice, expected=row['label'], sequence=selected,
                          full_correct=selected == expected, first_correct=selected[0] == expected[0]))
        if index % 100 == 0:
            print(index, len(rows), flush=True)
    report = dict(note='API agreement with offline labels; not a gameplay success metric.',
                  data=str(args.data), data_sha256=hashlib.sha256(args.data.read_bytes()).hexdigest(),
                  routing=health, total=len(rows), full_correct=sum(r['full_correct'] for r in cases),
                  first_correct=sum(r['first_correct'] for r in cases),
                  selected_lengths=dict(collections.Counter(len(r['sequence']) for r in cases)), cases=cases)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print({k:v for k,v in report.items() if k not in ('routing', 'cases')})


if __name__ == '__main__':
    main()
