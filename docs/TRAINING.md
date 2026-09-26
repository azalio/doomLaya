# Обучение Laya для FreeDoom <!-- slop-ignore F7 -->

[English](TRAINING.en.md) · Русский

Скрипт сохраняет обученную модель в отдельный каталог — checkpoint.
Исходные веса Laya не перезаписываются. Обучение идёт по заранее размеченным
примерам: метки задают игровые правила, а во время игры решения принимает модель.

Этот документ описывает опубликованную адаптацию v3 для MAP01.
Запуск и дообучение для MAP02 — в [отдельной инструкции](MAP02.md).

## 1. Подготовить окружение и данные

Из корня репозитория:

```bash
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements-lock.txt -r requirements-model.txt
.venv/bin/python training/finetune.py --data training --validate-only
.venv/bin/python training/finetune.py --data training/v3 --validate-only
```

JSON с обучающими примерами включены в репозиторий. Их версии зафиксированы,
поэтому для повторения обучения старые игровые записи не нужны. Хеши и происхождение — [training/datasets.json](../training/datasets.json).

| Этап | Train, вопросов | Validation, вопросов | Игровые seed |
|---|---:|---:|---|
| v1/v2 | 427 | 130 | train 42/43, validation 44 |
| v3 | 979 | 130 | train 42/43, validation 44 |

Каждая строка содержит один вопрос `command` или `weapon`.
Поля строки: `state`, `question`, `label`, `kind`, категория, исходный прогон,
тик и признак искусственного изменения состояния. Добавлялись состояния с низким HP,
нулевыми патронами и имеющимся дробовиком; примеры с редкими дверями повторялись в обучающей выборке.
Разделение сделано по исходным прогонам, не случайными соседними кадрами.
Все примеры относятся к MAP01. Итоговый seed 48 не входит в обучение,
но геометрия карты та же: перенос на неизвестный уровень здесь не проверялся.

Данные содержат состояния прежнего игрового контроллера; экспертные метки
назначены офлайн. Эти записи служат примерами для обучения, но не доказывают, что старая модель
самостоятельно принимала решения. JSON v1/v2 и v3 зафиксированы отдельно. Формат запросов между итерациями
менялся, поэтому заново созданные текущим кодом данные их не заменят.

## 2. Обучить v1 → v2 → v3

Команды ниже создают новые каталоги с суффиксом `-repro`, чтобы сохранить
готовые веса. Скрипт отклонит запуск, если каталог из `--output` уже существует.
Первый этап скачивает базу `convaiinnovations/laya/typed-decisions` по ревизии
`1c5edc17a7acd8701df6fc341c0d179f1c62c982`.

```bash
.venv/bin/python training/finetune.py \
  --data training --epochs 4 --lr 0.00003 --device mps \
  --output checkpoints/laya-doom-head-v1-repro

.venv/bin/python training/finetune.py \
  --base checkpoints/laya-doom-head-v1-repro \
  --data training --epochs 6 --lr 0.0003 --device mps \
  --output checkpoints/laya-doom-head-v2-repro

.venv/bin/python training/finetune.py \
  --base checkpoints/laya-doom-head-v2-repro \
  --data training/v3 --epochs 5 --lr 0.0001 --encoder-last 3 --device mps \
  --output checkpoints/laya-doom-v3-repro
```

На CUDA замените `--device mps` на `--device cuda`; для CPU — `cpu`.
Автовыбор — `auto`. Измеренный этап v3 на MPS занял около 507 секунд;
на других устройствах время может отличаться. Каждая сохранённая модель
занимает около 1,6 GiB: для базы и трёх этапов заложите минимум 8 GiB диска,
плюс окружение и запас. Пиковая RAM/VRAM в эксперименте не измерялась.

Общие параметры: seed 771, размер пакета (batch size) 4, AdamW,
weight decay 0.01, ограничение нормы градиента (clip grad norm) 1. У головы решений обучаются `head`, `scorer`, `type_emb`. Остальные параметры
заморожены, кроме последних трёх слоёв энкодера в v3. Их скорость обучения
(LR) фиксирована: 1e-5.
`act_head` не обучается. Энкодер остаётся в режиме оценки (eval mode), в том числе при обучении
последних слоёв. Функция потерь — cross-entropy по выбранному варианту вопроса.
Температура сбрасывается в 1; отдельная калибровка вероятностей не проводится.

Модель сохраняется, если сумма точностей (accuracy) ответов `command + weapon`
на проверочной выборке строго выросла. Эта метрика оценивает ответы на вопросы,
а не прохождение игры.
Итоговые веса соответствуют лучшей эпохе, а не обязательно последней.
Если ни одна эпоха не улучшилась, остаются базовые веса без `best-epoch.json`;
сервер адаптации отклоняет такой результат.

Исходный v3: лучшая эпоха 5, accuracy command 72,5%, weapon 98%.
Одинаковый seed не гарантирует побитово одинаковые веса между устройствами
и версиями библиотек. Для повторения итогового игрового прогона используйте готовую модель
с указанным SHA-256.

## 3. Проверить обучение в игре

```bash
.venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-doom-v3-repro --device mps --port 8001
```

В другом терминале:

```bash
.venv/bin/python agent.py --model doom-adapted --seed 48 \
  --seconds 180 --record auto --show --stop-after-level
.venv/bin/python -m tools.check_authority runs/<напечатанный-run>
.venv/bin/python -m tools.verify_run runs/<напечатанный-run>
```

Проверка требует подтверждённого движком завершения MAP01 и трёх секунд MAP02.
Игрок должен остаться жив, телеметрия — быть согласованной, а скорость игры —
соответствовать реальному времени. Если модель не прошла,
проверка вернёт FAIL. Не выбирайте эпоху по seed 48: для разработки используйте
отдельную серию проверочных прогонов и сохраняйте неудачные прогоны.

Для дальнейшей оценки запустите несколько новых seed с теми же настройками
и без дообучения по ним. Прохождение текущего seed 48 не обещает прохождения всех.

## 4. Собрать собственные обучающие примеры

`training/build_dataset.py` принимает телеметрию из `runs/<имя>/telemetry.jsonl`.
Сначала соберите отдельные игровые прогоны для обучения и проверки, затем задайте
файл `sources.json`, например:

```json
{
  "train": ["my-train-seed42", "my-train-seed43"],
  "validation": ["my-validation-seed44"]
}
```

```bash
.venv/bin/python training/build_dataset.py \
  --runs-dir runs --sources sources.json --output-dir training/custom
.venv/bin/python training/finetune.py \
  --data training/custom --encoder-last 3 --epochs 5 --lr 0.0001 \
  --output checkpoints/custom --device auto
```

Генератор рассчитан на MAP01: для другой карты нужно передать её геометрию
вместо фиксированной MAP01 и пересмотреть метки. Один исходный прогон нельзя
включать одновременно в обучающую и проверочную выборки. Чтобы повторить обучение v3, используйте зафиксированные данные,
а не заново собранные игровые траектории.

## 5. Подготовить checkpoint к распространению

```bash
.venv/bin/python scripts/package_model.py \
  --checkpoint checkpoints/laya-doom-v3 --output dist/laya-doom-v3 --archive
```

Получатся каталог для Hugging Face и архив для GitHub Releases с SHA-256.
Публикация не запускается этим скриптом. Для собственной модели обновите
`model-card/README.md`: результаты и хеш в шаблоне относятся к исходной v3.
Подробности — [PUBLISHING.md](PUBLISHING.md).
