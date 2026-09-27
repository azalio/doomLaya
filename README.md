# doomLaya

[English](README.en.md) · Русский

Laya и Jev играют в FreeDoom. Модель выбирает действие, цель и оружие;
контроллер строит маршрут, целится и нажимает кнопки по её команде.

[Обучение](docs/TRAINING.md) · [MAP02](docs/MAP02.md) · [Результаты](docs/COMPARISON.md) ·
[Веса и публикация](docs/PUBLISHING.md) · [Контракт управления](docs/DOOM.md)

## v0.3.0: MAP03 → MAP04

Laya прошла MAP03 за 819,914 с: seed 54, skill 3, четыре смерти.
После выхода записаны три секунды MAP04. Аудит управления и записи пройден.
Общая проверка качества не пройдена: неподвижность достигала 141,83 с.
Это один успешный прогон; MAP01/MAP02 с новым комплектом не проверены.

[Веса](https://huggingface.co/azalio/laya-doom-map03/tree/v0.3.0) ·
[Запуск и обучение](docs/MAP03.md) ·
[Видео с телеметрией](https://github.com/azalio/doomLaya/releases/download/v0.3.0/laya-map03.mp4) ·
[Отчёт](reports/map03-success.json).

## Обновление v0.2.0: MAP01 и MAP02

Один комплект весов прошёл обе карты с тем же исполнителем:

| Карта | Seed, skill | Выход | Смерти | Полное решение, p50 |
|---|---|---:|---:|---:|
| MAP01 → MAP02 | 48, 3 | 174,914 с | 0 | 384,72 мс |
| MAP02 → MAP03 | 54, 3 | 835,600 с | 2 | 430,47 мс |

После каждого выхода записаны три секунды следующей карты. Аудит управления,
видео и реального времени пройден. Общий `passed=false` сохраняется:
на MAP01 превышены пороги неподвижности и времени без нового района,
на MAP02 — времени без нового района и смены оружия. Это по одному
прогону; устойчивость на других seed не проверена.

[Веса на Hugging Face](https://huggingface.co/azalio/laya-doom-map02) ·
[Запуск и обучение](docs/MAP02.md) ·
[Видео MAP02](https://github.com/azalio/doomLaya/releases/download/v0.2.0/laya-map02.mp4) ·
[Финал MAP02, 65 секунд](https://github.com/azalio/doomLaya/releases/download/v0.2.0/laya-map02-finish.mp4) ·
[Видео MAP01](https://github.com/azalio/doomLaya/releases/download/v0.2.0/laya-map01.mp4).

Ниже сохранено сравнение прежней v3 с Jev. Оно относится к другой
конфигурации и не оценивает новый комплект весов.

## Сравнение v0.1.0 на MAP01

Сравнение проведено 22 сентября 2026 на macOS/MPS: FreeDoom MAP01, сложность
`skill 3`, начальное значение генератора случайных чисел `seed 48`. У моделей
один исполнитель, асинхронные запросы и скорость игры 35 тиков/с.

| Модель | Результат | HTTP p50 с RTT | Стоимость API |
|---|---|---:|---:|
| Исходная Laya typed-decisions | Не прошла за 180 с | 106 мс | $0 |
| Laya, адаптация v3 | **MAP01 → MAP02 за 61,43 с** | 108 мс | $0 |
| Jev 1.13 | **MAP01 → MAP02 за 68,97 с** | 357 мс | $0,004580184 |

Оба успешных прогона без смертей. Laya подбирала ресурсы, получила и использовала
дробовик. Laya дообучалась на задаче, Jev — нет. Проверен один итоговый seed
и одна карта; они не доказывают общего превосходства модели.
Расходы на локальные вычисления и обучение не оценивались.

Измерения, проверки прохождения и SHA-256 видео — в [reports](reports).
[Видео: Laya v3 и Jev](https://github.com/azalio/doomLaya/releases/download/v0.1.0/laya-vs-jev.mp4) ·
[Видео: исходная Laya и Jev](https://github.com/azalio/doomLaya/releases/download/v0.1.0/original-laya-vs-jev.mp4) ·
[Модель на Hugging Face](https://huggingface.co/azalio/laya-doom-v3) · [Архив весов](https://github.com/azalio/doomLaya/releases/tag/v0.1.0).
Команды скачивания — в [PUBLISHING.md](docs/PUBLISHING.md).

## Установка

Нужны Python 3.12+, Git, [uv](https://docs.astral.sh/uv/) и `ffmpeg` в PATH.
На macOS: `brew install uv ffmpeg cmake boost sdl2 openal-soft`. На Ubuntu
для сборки нужны `cmake`, `libboost-all-dev`, `libsdl2-dev`, `libopenal-dev`.
Клонируйте репозиторий и установите окружение.

```bash
git clone https://github.com/azalio/doomLaya.git
cd doomLaya
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements-lock.txt
uv pip install --python .venv/bin/python -r requirements-model.txt
.venv/bin/python scripts/install_vizdoom_sector_fix.py
```

Последняя команда собирает ViZDoom `1.3.1.post1` из закреплённой ревизии
с патчем буфера секторов. Штатная `1.3.1` падает на MAP03: у одного сектора
168 линий при размере массива 128. Карты и игровая логика не меняются.
После повторной установки `requirements-lock.txt` примените патч снова.

`requirements-model.txt` нужен для локальной Laya и обучения; для одного Jev
достаточно первого файла. Версия исходников Laya закреплена по commit SHA.
Базовые веса загружаются с Hugging Face по фиксированной ревизии, без
зависимости от чужого checkout или домашней директории.

## Запуск исходной Laya

В первом терминале:

```bash
.venv/bin/python serve_doom_laya.py --model typed-decisions --device auto
```

Первый запуск скачает `typed-decisions` из `convaiinnovations/laya`.
Во втором терминале, из той же директории:

```bash
.venv/bin/python agent.py --model typed-decisions --seed 48 \
  --seconds 180 --record auto --show --stop-after-level
```

Исходная модель в итоговом эксперименте уровень не прошла. Для воспроизведения
успешного прохождения нужны веса адаптации ниже.

## Запуск адаптации v3

Скачайте полный каталог модели в `checkpoints/laya-doom-v3`:

```bash
.venv/bin/hf download azalio/laya-doom-v3 \
  --revision d27276e3bf8275cdbc9a7a72d80cad656aa87bd7 \
  --local-dir checkpoints/laya-doom-v3
(cd checkpoints/laya-doom-v3 && shasum -a 256 -c SHA256SUMS)
```

Другие варианты: [архив из GitHub Release](docs/PUBLISHING.md) или
[обучение своей модели](docs/TRAINING.md). Команда `git clone` скачивает исходники без весов.

```bash
.venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-doom-v3 --device auto --port 8001
```

Во втором терминале:

```bash
.venv/bin/python agent.py --model doom-adapted --seed 48 \
  --seconds 180 --record auto --show --stop-after-level
```

`--device auto` выбирает CUDA, затем MPS, затем CPU. Для точного соответствия
исходному эксперименту используйте `--device mps`. CPU и CUDA доступны в коде;
полное прохождение на них отдельно не проверялось. Для запуска без окна уберите `--show`.
Обычный старт — стандартный инвентарь FreeDoom. WAD входит в пакет ViZDoom.

## Jev и сравнение

Создайте локальный `.env`, если его ещё нет, и внесите ключ OpenRouter:

```bash
test -e .env || cp .env.example .env
chmod 600 .env
```

Клиент автоматически читает `OPENROUTER_API_KEY`. Не добавляйте `.env` в Git.

```bash
.venv/bin/python agent.py --model jev --seed 48 \
  --seconds 180 --record auto --show --stop-after-level
```

Для трёх последовательных прогонов запустите оба локальных сервера
(исходный на 8000, адаптацию на 8001), затем:

```bash
.venv/bin/python -m tools.run_comparison --seed 48 --seconds 180
```

В строке `SUITE` скрипт выведет каталог результатов. Путь к каждому прогону
будет в поле `path` следующей JSON-записи; строка `RUN` сохраняется в его логе.
Ошибки API не включают запасную стратегию. Если игрок не прошёл уровень, проверка прохождения вернёт FAIL,
даже если исполнитель правильно выполнил все команды модели.

```bash
.venv/bin/python -m tools.render_comparison runs/<laya-run> runs/<jev-run> \
  --output runs/laya-vs-jev.mp4
.venv/bin/python -m tools.measure_network runs/network.json
```

В видео два окна: видны HP, патроны, убийства, команда, цель, оружие,
вероятности выбора, возраст состояния и цена API.
Полное время HTTP-запроса включает RTT — время передачи по сети туда и обратно. <!-- slop-ignore R1 -->
Игра идёт и во время запроса; окна синхронизированы по игровому времени. Когда прогон заканчивается,
его последний кадр остаётся на экране с подписью.

## Граница ответственности

По умолчанию модель получает текстовое состояние и два вопроса: `command`, `weapon`.
Режим `--decision-format factorized` отдельно спрашивает действие, цель, оружие
и движение в бою. Режим `committed` добавляет текущую цель и явную команду
продолжения; он используется в [эксперименте MAP02](docs/MAP02.md).
Варианты команд включают конкретных видимых монстров и наблюдавшиеся предметы.
Исполнитель умеет целиться, идти к указанной цели и обходить препятствия.
Он не выбирает полезность предметов, приоритет боя или лучшее оружие.

Обеим моделям доступны геометрия WAD и положение выхода. `exit` строит маршрут
к выходу; промежуточная дверь требует отдельного `open_door`. `explore` —
макрокоманда движения к ближайшей непосещённой области. Эксперимент сравнивает выбор команд по текстовому состоянию. Он не проверяет
нейросетевое управление каждой кнопкой или игру только по изображению.

Предмет может подбираться случайно по пути самим движком. Автосмена оружия при
подборе отключена. Недостижимая команда временно исключается после реального
отказа поиска пути и возвращается после изменения позиции/дверей.
Ответы старше двух секунд и ответы из другого эпизода не применяются.
После реального завершения MAP01 запускается MAP02 со стандартным инвентарём;
`--stop-after-level` записывает ещё три секунды и останавливается.

## Проверка

```bash
.venv/bin/python -m unittest tests.test_authority tests.test_map2 tests.test_publication
.venv/bin/python scripts/check_publication.py
.venv/bin/python -m tools.check_authority runs/<run>
.venv/bin/python -m tools.verify_run runs/<run>
```

В каждой записи сохраняются запросы/ответы, события, покадровая телеметрия,
видео, конфигурация и копия игровых исходников с хешами.
`execution.decision_id` связывает кнопки с конкретным ответом модели.
Перед публикацией в чистом окружении проверены установка, 16 тестов,
один шаг обучения и пятисекундная игра с упакованными весами.
[Протокол проверки](reports/publication-validation.json). Полное обучение и
прохождение при подготовке архива повторно не запускались.

GitHub Actions выполняет проверки исходников без API-ключа и больших весов;
обучение и полное игровое прохождение в CI не запускаются.

## Лицензия и источники

Код и адаптация — [Apache-2.0](LICENSE); атрибуция — [NOTICE](NOTICE).
Основа: [Laya](https://github.com/NandhaKishorM/laya),
[ViZDoom](https://github.com/Farama-Foundation/ViZDoom),
[FreeDoom](https://freedoom.github.io/),
[Jev через OpenRouter](https://openrouter.ai/typesafe/jev-1.13).
Идея эксперимента пришла из предоставленного пользователем поста канала
[prompt_design](https://t.me/prompt_design); оригинальные сторонние материалы
и исторические черновики не включены в публикацию.
