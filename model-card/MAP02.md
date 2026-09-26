---
language:
- en
license: apache-2.0
library_name: laya
base_model: convaiinnovations/laya
base_model_relation: finetune
tags:
- doom
- vizdoom
- supervised-fine-tuning
- imitation-learning
- decision-making
- modernbert
---

# Laya Doom MAP02

Комплект весов Laya для FreeDoom MAP01 и MAP02. Модель выбирает действие,
цель, оружие и движение в бою; исполнитель строит путь, целится и нажимает
кнопки по её команде. Модель получает текстовое состояние игры, а не изображение.

## Проверенные прогоны

Проверка 26 сентября 2026 на macOS/MPS, skill 3, игра в реальном времени.
После каждого выхода записаны ещё три секунды следующей карты.

| Карта | Seed | Выход | Смерти | Медиана полного решения |
|---|---:|---:|---:|---:|
| MAP01 → MAP02 | 48 | 174,914 с | 0 | 384,72 мс |
| MAP02 → MAP03 | 54 | 835,600 с | 2 | 430,47 мс |

В обоих прогонах `experiment_valid=true` и `level_completed=true`.
Общий `passed=false`: на MAP01 превышены пороги неподвижности и времени
без нового района, на MAP02 — времени без нового района и смены оружия.
Это по одному прогону на картах, использованных при разработке; результат
не доказывает устойчивость на других seed или неизвестных картах.

[Видео и отчёты](https://github.com/azalio/doomLaya/releases/tag/v0.2.0).
Веса этого комплекта не сравнивались с Jev в одинаковой конфигурации.
Опубликованное сравнение v0.1.0 относится к прежней Laya v3 и другому исполнителю.

## Состав комплекта

| Вопрос | Каталог |
|---|---|
| Оружие, враг и огонь во время движения | `laya-map2-explicit-v2` |
| Команда | `laya-map2-root-goals-v1` |
| Предмет | `laya-map2-goal-invariant-items-v1` |
| Движение в бою | `laya-map2-explicit-movement-v1` |
| Механизм | `laya-map2-stable-goals-v1` |

Это пять полных checkpoint, около 8 GiB вместе. На сервере они используют
один энкодер после проверки побитового совпадения его весов.
Голова выбирается по имени вопроса; игровая ситуация не переключает модель.
Хеши отдельных весов и назначение голов находятся в `question-heads.json`.
Хеш набора:
`f8d2531bfeb4968058590d73ccf71b143df51855a6ab00406d30bb08ee078c49`.

## Обучение

Использовано обучение с учителем по состояниям игровых прогонов и меткам
офлайн-эксперта. Поздние этапы добавляют исправления на состояниях, посещённых
моделью, и варианты с другой текущей целью при сохранённых фактах мира.
Это supervised imitation learning; оптимизации по награде и обучения RL нет.
Эксперт не выбирает команды во время проверочных игровых прогонов.

У последних специализированных голов энкодер заморожен. Для головы команды
использованы 5122 обучающих и 2458 проверочных вопроса, четыре эпохи,
LR 5e-5; выбрана четвёртая эпоха. Остальные этапы, данные и команды обучения
описаны в [MAP02.md](https://github.com/azalio/doomLaya/blob/v0.2.0/docs/MAP02.md).
Конфигурации, лучшая эпоха и метрики каждой головы находятся в её каталоге.

База: `convaiinnovations/laya/typed-decisions`, ревизия
`1c5edc17a7acd8701df6fc341c0d179f1c62c982`. Исходники Laya:
`42626c348753fbb17572a813127df2278a1ec527`. Лицензия Apache-2.0;
атрибуция в `NOTICE`.

## Запуск

Установите [doomLaya v0.2.0](https://github.com/azalio/doomLaya/tree/v0.2.0)
и зависимости по его README. Из корня doomLaya:

```bash
.venv/bin/hf download azalio/laya-doom-map02 --revision v0.2.0 \
  --local-dir checkpoints/laya-doom-map02
(cd checkpoints/laya-doom-map02 && shasum -a 256 -c SHA256SUMS)

.venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-doom-map02/laya-map2-explicit-v2 \
  --item-head-checkpoint checkpoints/laya-doom-map02/laya-map2-goal-invariant-items-v1 \
  --head-checkpoint movement=checkpoints/laya-doom-map02/laya-map2-explicit-movement-v1 \
  --head-checkpoint command=checkpoints/laya-doom-map02/laya-map2-root-goals-v1 \
  --head-checkpoint switch=checkpoints/laya-doom-map02/laya-map2-stable-goals-v1 \
  --device auto --port 8001
```

Команда игры — в [инструкции MAP02](https://github.com/azalio/doomLaya/blob/v0.2.0/docs/MAP02.md).
Для перехода на MAP03 требуется включённый в doomLaya патч ViZDoom.
Исполнитель знает геометрию карты, выход, ключи, механизмы и координаты оружия.
Возможны зацикливание, неудачный выбор предметов и смерть игрока.
Комплект загружается сервером doomLaya, а не `transformers.pipeline`.
