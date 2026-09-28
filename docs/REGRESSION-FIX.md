# v0.3.1: прохождение MAP01–MAP03

Один комплект `key-retained` прошёл MAP01, MAP02 и MAP03 без смертей
в последовательной серии `native-rtt`. Модель, исполнитель и настройки
одинаковы на всех трёх картах.

| Карта | Seed, skill | Выход | Смерти | RTT p50 | Проверка навигации |
|---|---|---:|---:|---:|---|
| MAP01 → MAP02 | 48, 3 | 168,400 с | 0 | 266,01 мс | Замечание: 32,23 с без новой области |
| MAP02 → MAP03 | 54, 3 | 420,400 с | 0 | 295,81 мс | Пройдена |
| MAP03 → MAP04 | 54, 3 | 347,114 с | 0 | 309,47 мс | Пройдена |

После каждого выхода записаны 105 тиков следующей карты. Проверки видео,
реального времени и исполнения решений модели прошли. Порог времени без
новой области на MAP01 — 25 с, поэтому общая проверка качества этой карты
остаётся `passed=false`; зачёт прохождения — `true`.
[Полный отчёт с SHA записей и исходников](../reports/v031-regression.json).

Ответ применяется сразу после получения. Искусственное ожидание готового
ответа отключено; реальный RTT и ход игрового времени сохранены.
Этот режим теперь используется в `tools/regression_suite.py` по умолчанию.
Для старого режима нужно явно передать `--minimum-decision-delay-ticks 16`.

Проверены по одному итоговому прогону на картах и seed, использованных
при разработке. Устойчивость к другим seed и колебаниям RTT не доказана.
Неуспешные опыты сохранены в журнале. Дополнительных запросов к модели,
обучения и сжатия файлов во время игры не было; журналы сжаты между картами,
их SHA не изменились.

## Запуск из корня репозитория

Установите зависимости по [README](../README.md#установка), включая
`requirements-model.txt` и патч ViZDoom. Все команды выполняются из корня
репозитория версии `v0.3.1`. Для MPS нужна macOS с Apple Silicon; на другой
платформе замените `--device mps` подходящим устройством. Время прохождения
и RTT на другом оборудовании могут отличаться.

Скачайте восемь голов модели. Зависимости обучения пока не нужны:

```bash
hf download azalio/laya-doom-map03 --revision v0.3.1 \
  --exclude 'training-assets/*' --local-dir checkpoints/laya-doom-v031
(cd checkpoints/laya-doom-v031 && shasum -a 256 -c SHA256SUMS)
```

CLI `hf` устанавливается с `huggingface-hub`; если его нет в PATH,
используйте `.venv/bin/hf`. Запустите API:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  .venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-doom-v031/laya-map2-explicit-v2 \
  --item-head-checkpoint checkpoints/laya-doom-v031/laya-v031-item-balanced-v1 --item-category-facts \
  --command-compact-facts --enemy-without-goal \
  --enemy-rank-facts --weapon-compact-facts --movement-compact-facts \
  --head-checkpoint movement=checkpoints/laya-doom-v031/laya-v031-movement-numeric-v1 \
  --head-checkpoint command=checkpoints/laya-doom-v031/laya-v031-command-key-retained-v1 \
  --head-checkpoint look_gate=checkpoints/laya-doom-v031/laya-map3-look-floor-v2 \
  --head-checkpoint switch=checkpoints/laya-doom-v031/laya-v031-switch-numeric-v1 \
  --head-checkpoint enemy=checkpoints/laya-doom-v031/laya-v031-enemy-visibility-v2 \
  --head-checkpoint weapon=checkpoints/laya-doom-v031/laya-v031-weapon-boundary-v2 \
  --device mps --port 8003
```

После `Application startup complete` в другом терминале проверьте API и запустите игру:

```bash
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-finish-route-cases.json \
  --expect-head command=checkpoints/laya-doom-v031/laya-v031-command-key-retained-v1 \
  --output runs/v031-finish-route-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-teacher-switch-cases.json \
  --expect-head switch=checkpoints/laya-doom-v031/laya-v031-switch-numeric-v1 \
  --output runs/v031-numeric-switch-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-visible-fight-cases.json \
  --expect-head command=checkpoints/laya-doom-v031/laya-v031-command-key-retained-v1 \
  --output runs/v031-visible-fight-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-key-command-cases.json \
  --expect-head command=checkpoints/laya-doom-v031/laya-v031-command-key-retained-v1 \
  --output runs/v031-visible-fight-key-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-observed-movement-errors.json \
  --expect-head movement=checkpoints/laya-doom-v031/laya-v031-movement-numeric-v1 \
  --output runs/v031-retreat-key-movement-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-enemy-visibility-cases.json \
  --expect-head enemy=checkpoints/laya-doom-v031/laya-v031-enemy-visibility-v2 \
  --output runs/v031-enemy-visibility-v2-enemy-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-weapon-boundary-cases.json \
  --expect-head weapon=checkpoints/laya-doom-v031/laya-v031-weapon-boundary-v2 \
  --output runs/v031-enemy-visibility-v2-weapon-api-repeat.json
.venv/bin/python tools/regression_suite.py \
  --endpoint http://127.0.0.1:8003/predict --tag v031-native-rtt-repeat --first-map MAP03 --minimum-decision-delay-ticks 0
```

Проверка механизмов возвращает код 1: пройдены 13 из 14 случаев.
Проверка видимости возвращает код 1: пройдены 11 из 16 случаев.
Проверки ключей, движения и оружия прошли на текущем комплекте.
Игровой прогон нужен для оценки всего комплекта.

Проверка запускает MAP01 seed 48 на 180 с, MAP02 seed 54 на 1800 с и
MAP03 seed 54 на 1200 с; везде skill 3. Для зачёта нужны выход живым,
не менее 105 тиков следующей карты, корректная запись видео и подтверждение
исполнения решений модели. Навигация проверяется отдельно. Веса и настройки
остаются одинаковыми во всех трёх прогонах. `--first-map MAP03` меняет
только порядок: затем следуют MAP01 и MAP02 с прежними условиями.
По умолчанию проверка останавливается после провала; дополнительный
флаг `--keep-going` продолжает остальные карты.

В `runs/ДАТА_v031-native-rtt-repeat_suite/` будут `suite.json`
и журналы. В каталогах карт — `video.mp4`, `report.html`, `summary.json`,
`verification.json`, решения, телеметрия и снимок исходников с SHA.
Во время игрового прогона не запускать обучение и дополнительные запросы
к модели: они изменят измеряемую задержку решений.

## Что изменено

Исполнитель выхода доходит до передней стороны выбранной линии,
прежде чем нажать USE. Опыт в движке воспроизвёл старую ошибку за
350 тиков; с исправлением выход сработал через 74.

Команды, предметы, боевое движение и механизмы оценивают текстовая Laya
и дополнительные обучаемые числовые сети. Это изменение архитектуры.
Их `numeric-residual.safetensors` и `numeric-residual.json` входят
в API-манифест по SHA. Головы оружия и противников дообучены при
замороженном энкодере. Контроллер исполняет выбор модели; офлайн-разметчик
во время игры не вызывается.

При исправлении команд изменены второй скрытый и выходной слои числовой
головы команд. Энкодер, первый числовой слой, признаки и их пороги
заморожены. Для ошибок MAP02 использованы исправленные метки; для остальных
состояний — оценки прежней модели. Checkpoint допускается к проверке
только при сохранении всех 1096 решений успешных MAP01/MAP03.

## Повторное обучение в этой директории

Данные и скрипты входят в GitHub-тег `v0.3.1`. Родительские веса, кеши
текстовых оценок и два журнала для сохранения прежних решений находятся
в том же HF-теге. Скачайте их отдельно:

```bash
hf download azalio/laya-doom-map03 --revision v0.3.1 \
  --include 'training-assets/*' --local-dir checkpoints/laya-doom-v031
(cd checkpoints/laya-doom-v031/training-assets && shasum -a 256 -c SHA256SUMS)
mkdir -p runs/v031-training-cache
cp checkpoints/laya-doom-v031/training-assets/caches/*.json runs/v031-training-cache/
```

Кеши копируются: некоторые скрипты дописывают результаты проверки в файл.
Пример ниже повторяет финальное обучение головы команд. Каталог вывода
не должен существовать:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  .venv/bin/python training/finetune_numeric_retention.py \
  --base checkpoints/laya-doom-v031/training-assets/parents/laya-v031-command-finish-retained-v1 \
  --data training/v031-command-key-return-v1 \
  --cache runs/v031-training-cache/v031-command-key-return-cache.json \
  --retention-run checkpoints/laya-doom-v031/training-assets/retention/20260928_060838_897203_v031-finish-retained-map03-seed54 \
  --retention-run checkpoints/laya-doom-v031/training-assets/retention/20260928_061517_586603_v031-finish-retained-map01-seed48 \
  --retain-all-observations --repair-category key_return_ \
  --output checkpoints/laya-v031-command-key-retained-retrained \
  --epochs 1600 --learning-rate .0001 --trainable-block hidden
```

Этот этап повторён из подготовленных к публикации файлов: текстовые веса,
числовые веса и описание признаков совпали с принятым комплектом побайтно.
[Проверка SHA](../reports/v031-training-reproduction.json). Все предыдущие
этапы целиком при подготовке релиза не повторялись.

В обучении головы команд выбрана эпоха 65: 1179/1191 совпадений с метками,
53/54 исправлений новых проверочных состояний, сохранены 1137/1137 прежних
проверочных решений и 1096/1096 решений двух успешных прогонов.
На синтетике — 2906/3000 совпадений с метками.
Это те же карты и seed, на которых велась разработка.

После обучения заменить путь головы `command` в API и все параметры
`--expect-head command` на `checkpoints/laya-v031-command-key-retained-retrained`.
Перезапустить сервер и пройти все три карты заново. Для повторных
проверок указать новые файлы `--output` и новый игровой `--tag`.

[Журнал разработки](REGRESSION-DEVELOPMENT.md) ·
[Обучение остальных голов](REGRESSION-TRAINING.md) ·
[Прежние команды обучения](REGRESSION-RECIPES.md) ·
[Манифест текущего кандидата](../reports/v031-candidate-model.json).
