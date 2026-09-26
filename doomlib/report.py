"""Самодостаточный HTML-отчёт; исходная телеметрия только читается."""
import argparse
import html
import json
from pathlib import Path
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()


def build_report(directory):
    root = Path(directory)
    summary = json.loads((root / 'summary.json').read_text())
    rows = []
    for line in (root / 'decisions.jsonl').read_text().splitlines():
        row = json.loads(line)
        rows.append('<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in [
            row.get('game_seconds'), row.get('command',row.get('choice')), row.get('answers',{}).get('weapon',{}).get('choice','—'), row.get('applied'),
            row.get('reason'), row.get('latency_ms'), row.get('tokens'),
        ]) + '</tr>')
    model=summary['model']
    cards = ''.join(f'<article><small>{html.escape(k)}</small><strong>{html.escape(str(summary.get(k)))}</strong></article>'
                    for k in ['game_seconds', 'decisions', 'kills', 'deaths', 'errors', 'latency_ms_median', 'external_api_cost_usd', 'levels_completed'])
    video = '<video controls preload="metadata" src="video.mp4"></video>' if (root / 'video.mp4').exists() else ''
    doc = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>DOOM × Laya — {html.escape(root.name)}</title>
<style>body{{background:#10151f;color:#dce4f0;font:16px system-ui;margin:32px auto;max-width:1280px;padding:0 24px}}
h1{{font-size:44px;margin-bottom:8px}}small,p{{color:#a7b6ca}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0}}
article{{background:#1d2736;padding:20px;border-radius:12px}}strong{{display:block;font-size:32px;color:#6bdacb}}video{{width:100%;border-radius:12px}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#1d2736;padding:20px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #354153}}
@media(max-width:650px){{.cards{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:32px}}.table{{overflow:auto}}}}</style>
<h1>DOOM × {html.escape(model)}</h1><p>{html.escape(root.name)} · реальные ответы модели</p>
<div class="cards">{cards}</div>{video}
<p>Модель выбирает действие, цель и оружие. Исполнитель нажимает соответствующие кнопки.
Стоимость внешнего API: ${summary.get('external_api_cost_usd',0):.6f}. Локальные затраты не измерялись.
Завершение записи не означает прохождение уровня: смотрите levels_completed и verification.json.</p>
<details><summary>Полная сводка</summary><pre>{html.escape(json.dumps(summary, ensure_ascii=False, indent=2))}</pre></details>
<h2>Решения модели</h2><div class="table"><table><tr><th>Игра, с</th><th>Команда</th><th>Оружие</th><th>Применено</th><th>Причина</th><th>Latency, ms</th><th>Tokens</th></tr>{''.join(rows)}</table></div></html>'''
    dest = root / 'report.html'
    dest.write_text(doc, encoding="utf-8")
    return dest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run')
    print(build_report(parser.parse_args().run))
