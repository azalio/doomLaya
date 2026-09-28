# v0.3.1: обучение остальных голов

Сначала скачайте зависимости и скопируйте кеши по
[инструкции v0.3.1](REGRESSION-FIX.md#повторное-обучение-в-этой-директории).
Команды ниже выполняются из корня репозитория. Они повторяют последние
этапы обучения пяти голов из опубликованных родительских весов.
Головы `default` и `look_gate` взяты из v0.3.0 без изменений.

Это обучение по меткам офлайн-разметчика и записанным наблюдениям,
с синтетическими примерами. Обучения по награде здесь нет. Энкодер заморожен;
для предметов, движения и механизмов также заморожена текстовая голова.
Офлайн-разметчик не вызывается при игре.

При подготовке релиза побайтно воспроизведён только финальный этап головы
команд, описанный в основной инструкции. Команды ниже сверены с параметрами
сохранённых моделей, но повторно целиком не запускались. Для оценки новых
весов нужны проверка API и новая серия всех трёх карт.

Нужна macOS с MPS для приведённых команд. Укажите новые каталоги вывода;
они не должны существовать. Не запускайте обучение одновременно с игрой.

```bash
export USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false
```

## Предметы

```bash
.venv/bin/python training/finetune_numeric_item.py \
  --base checkpoints/laya-doom-v031/training-assets/parents/laya-v031-item-consistent-v1 \
  --data training/v031-item-balanced-v2 \
  --cache runs/v031-training-cache/v031-item-balanced-v2-cache.json \
  --output checkpoints/laya-v031-item-balanced-retrained \
  --epochs 180 --augmentation 40000 --balanced-resupply-labels
```

## Боевое движение

```bash
.venv/bin/python training/finetune_numeric_movement.py \
  --base checkpoints/laya-doom-v031/training-assets/parents/laya-map3-compact-movement-v1 \
  --data training/v031-movement-numeric-v1 \
  --cache runs/v031-training-cache/v031-movement-numeric-cache.json \
  --output checkpoints/laya-v031-movement-numeric-retrained \
  --epochs 250 --augmentation 40000 --device mps
```

## Механизмы

```bash
.venv/bin/python training/finetune_numeric_switch.py \
  --base checkpoints/laya-doom-v031/training-assets/parents/laya-v031-switch-collected-v1 \
  --data training/v031-switch-teacher-v1 \
  --cache runs/v031-training-cache/v031-switch-teacher-semantic-cache.json \
  --output checkpoints/laya-v031-switch-numeric-retrained \
  --epochs 500 --device mps
```

## Противники

```bash
.venv/bin/python training/finetune.py \
  --base checkpoints/laya-doom-v031/training-assets/parents/laya-v031-enemy-visibility-v1 \
  --data training/v031-enemy-visibility-v2 \
  --output checkpoints/laya-v031-enemy-visibility-retrained \
  --epochs 8 --lr 0.00005 --cache-encoder --device mps --save-at-end \
  --category-weight recorded_invisible_first=10 \
  --category-weight mixed_visibility_synthetic=2 \
  --visible-first-category recorded_invisible_first \
  --visible-first-category mixed_visibility_synthetic \
  --visible-first-weight 4
```

## Оружие

```bash
.venv/bin/python training/finetune.py \
  --base checkpoints/laya-doom-v031/training-assets/parents/laya-v031-weapon-boundary-v1 \
  --data training/v031-weapon-boundary-v2 \
  --output checkpoints/laya-v031-weapon-boundary-retrained \
  --epochs 10 --lr 0.00001 --cache-encoder --device mps --save-at-end
```

После обучения замените соответствующие пути в команде API и параметрах
`--expect-head`, затем выполните проверки из основной инструкции.
Показатели совпадения с метками не заменяют проверку прохождения.
