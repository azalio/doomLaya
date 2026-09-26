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
- reinforcement-learning-environment
- supervised-fine-tuning
- decision-making
- modernbert
---

# Laya Doom v3

Адаптация Laya `typed-decisions`: модель выбирает действие, цель и оружие
для FreeDoom MAP01 через ViZDoom. Исполнитель реализует выбранные команды.
Модель обучалась с учителем по заранее размеченным примерам
(supervised fine-tuning). Обучение с подкреплением (RL) в игре не проводилось.

## База и лицензия

`convaiinnovations/laya`, подкаталог `typed-decisions`, ревизия
`1c5edc17a7acd8701df6fc341c0d179f1c62c982`; ModernBERT-large с головой решений.
Исходники Laya: `42626c348753fbb17572a813127df2278a1ec527`.
Apache-2.0; атрибуция в `NOTICE`, лицензия в `LICENSE` внутри выгрузки.

## Обучение

v1: голова, 4 эпохи, LR 3e-5. v2: продолжение v1, голова, 6 эпох, LR 3e-4.
v3: продолжение лучшей v2, голова со скоростью обучения (LR) 1e-4 и последние 3 слоя энкодера с LR 1e-5,
5 эпох. Размер пакета (batch) 4, AdamW, weight decay 0.01,
ограничение нормы градиента (clip grad norm) 1, seed 771.
Обучение v3: 979 размеченных вопросов; проверка: 130 вопросов.
Обучающие игровые seed 42/43, проверочный 44. Метки созданы игровыми правилами
офлайн. Сохранялась модель с наибольшей суммой точностей (accuracy) ответов
на вопросы command + weapon.

Лучшая эпоха v3 — 5: command 72,5%, weapon 98% на этой проверочной выборке.
Это доли верных ответов, а не вероятность прохождения игры.
Инструкции и зафиксированные данные
поставляются в исходном репозитории [doomLaya](https://github.com/azalio/doomLaya)
([TRAINING.md](https://github.com/azalio/doomLaya/blob/main/docs/TRAINING.md)).

## Игровая проверка и ограничения

Один финальный прогон: FreeDoom MAP01, skill 3, seed 48,
переход на MAP02 через 61,429 с без смертей. Исходная Laya не прошла за 180 с;
Jev прошёл за 68,971 с. Это результат на одной карте и одном итоговом seed, не общая оценка моделей.
Laya обучалась для этой задачи; Jev не дообучался. Для обучения использовалась
та же карта с другими seed: новая геометрия уровня не проверялась.

Исполнитель знает полную геометрию WAD и координаты выхода, строит маршрут и
целится в выбранного врага. Модель получает текстовые данные сенсоров, а не пиксели.
Все участники сравнения получали одинаковые возможности исполнителя.
На других состояниях возможны неудачный выбор оружия, зацикливание и гибель.
Калибровка вероятностей после дообучения отдельно не измерялась.

## Загрузка

Скачайте полный каталог модели и передайте его в локальный сервер doomLaya.
Установка окружения описана в [README](https://github.com/azalio/doomLaya#установка).

```bash
python serve_doom_laya.py --checkpoint checkpoints/laya-doom-v3 --device auto
```

Внутри каталога обязательны `model.safetensors`, `rl_agent_config.json`,
`encoder/`, `tokenizer/`, `best-epoch.json`, `training-metrics.json`.
Каталог загружается библиотекой Laya, а не через `transformers.pipeline`.
SHA-256 весов: `bb9083189517c5dc5c0e357062446df2ea73eadc3d909ec6ec7a6cee222a6147`.
Проверка всех файлов выгрузки: `shasum -a 256 -c SHA256SUMS`.
