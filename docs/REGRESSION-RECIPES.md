# Прежние инструкции разработки регрессии

Это архив до кандидата key-retained. Текущий запуск — в [REGRESSION-FIX.md](REGRESSION-FIX.md).

# Исправление регрессии MAP01/MAP02

Кандидат `finish-retained` прошёл MAP03 и MAP01 без смертей;
MAP02 прервана на 540,771 с без смертей после повторного цикла у лифта.
Выходы — на 391,114 с и 165,657 с соответственно, после каждого записаны
105 тиков следующей карты. Запись, реальное время и исполнение решений
модели подтверждены для двух завершённых карт. Общего зачёта трёх карт нет.

Готовится `key-retained`: исправление возврата на лифт вместо подбора
доступного жёлтого ключа. При обучении сохранены все 1096 решений из
успешных MAP01 и MAP03, исправлены 53/54 новых проверочных состояний.
Игровой результат нового комплекта пока не получен.

Проверки качества навигации не пройдены: на MAP03 до 30,06 с без новой
области; на MAP01 до 36,2 с без новой области и 25,06 с без новой ячейки.
Прохождение и качество навигации учитываются отдельно.

При дообучении сохранены все 543 прежних решения до сбора ключей;
реальный API подтвердил их, а также 16/16 исправлений финального цикла,
80/80 проверок ключей и 12/12 проверок боя. Полная проверка команд —
1126/1137.

Кандидат `finish-route` не прошёл MAP03 за 1200 с: семь смертей,
296 убийств, 51 подбор. Аудит записи и управления пройден, ошибок API нет.
MAP01 была прервана сразу после старта из-за нехватки места для записи;
MAP02 не запускалась. Общего зачёта этот комплект не получил.
Голова команд `laya-v031-command-finish-v1` исправила через API 16/16
записанных случаев отвлечения на далёкие припасы после сбора всех ключей.
Прежние проверки боя — 12/12, подбора ключей — 80/80.
Полная проверка команд через API — 1125/1137.
Новая голова механизмов дала через API 300/305 совпадений с разметкой,
исправила 13/14 сохранённых ошибок успешного офлайн-маршрута и прошла
11/12 прежних проверок механизмов у собранных ключей. Эти примеры
использовались при разработке и не измеряют обобщение на новые карты.

Используется прежняя голова движения `laya-v031-movement-numeric-v1`.
Другие головы совпадают с комплектом `numeric-switch`.

Предыдущий `numeric-switch` прерван на 548,229 с без смертей и с тремя
ключами: игрок зациклился между дальней аптечкой и патронами.
MAP01 и MAP02 этим комплектом не запускались. Новая офлайн-разметка
с приоритетом завершения уровня прошла MAP03 за 369,8 с без смертей;
это проверка разметчика, не результат нейронной модели.

Предыдущий `visible-fight` прерван на 510 с после пяти смертей.
Лимит MAP03 не исчерпан; MAP01 и MAP02 этим комплектом не запускались.

Предыдущий `retreat-key` прерван на 553,2 с после четырёх смертей.
Лимит MAP03 не исчерпан; MAP01 и MAP02 не запускались.
Предыдущий `typed-key` не завершил MAP03 за 1200 с: девять смертей,
327 убийств, 80 подборов. MAP01 и MAP02 этим комплектом не проверялись.

Офлайн-разметчик с прежним движением повторно прошёл MAP03 за 374,714 с
без смертей. Замена только движения на схему `typed` привела к первой смерти
на 63,571 с. Это диагностика разметки, не прохождение Laya.
Для прежней головы движения через API подтверждены 14/14 записанных случаев.

Отдельно проверена разметка команд: прежние приоритеты команд и предметов
привели разметчика к первой смерти на 131,057 с. Возврат приоритета боя
с видимыми врагами дал проход за 369,171 с без смертей; отдельная функция
меток для обучения повторила этот результат. Это офлайн-диагностика,
не свидетельство прохождения модели.

У предыдущего `typed-key` были следующие результаты на сохранённых состояниях.
Через API исправлены 80/80 сохранённых ошибок команды у ключа;
полная проверка команд — 903/905. Для движения — 750/750 состояний,
16/16 новых случаев с демонами и 13/13 прежних случаев бокового движения.
Это проверки записанных состояний. Прохождение трёх карт ещё не подтверждено.

Предыдущий кандидат `enemy-visibility-v2` завершил MAP01 за 138,571 с
без смертей. MAP02 прервана на 1413,971 с после трёх смертей и повторного
маршрута к синему ключу без его подбора. MAP03 прервана на 288,943 с
после трёх смертей. Лимиты этих двух карт не исчерпаны; общего зачёта нет.

Голова противников у `finish-route` сохранена: 11/16 прежних ошибок видимости
исправлены, пять остаются. На старом наборе первая цель — 231/272,
полный порядок — 213/272. Эти ограничения остаются в новом комплекте.

Комплект `lateral-weapons` проверен на трёх картах с неизменными
весами. MAP01 завершена за 108,057 с без смертей; MAP02 — за 776,286 с
с одной смертью. Переходы на следующие карты и исполнение решений модели
подтверждены. MAP03 не завершена за 1200 с: восемь смертей.
Этот комплект не получил общего зачёта.

На MAP01 пройдены все проверки навигации. На MAP02 остаются замечания:
максимум без новой ячейки — 46,83 с, без новой области — 91 с,
неподвижность — 4,37 с. Смена оружия заняла до 1,543 с при пороге 1,5 с;
сама модель выбрала улучшение за 0,886 с. Прохождение MAP02 не означает,
что все требования к движению выполнены.

Голова оружия исправила 12/12 сохранённых ошибок через API:
супердробовик больше не выбирается с одним зарядом в этих состояниях.
В полной проверке оружия — 824/849 совпадений с разметкой. Остались
два выбора пустого оружия в синтетических состояниях и расхождения
в приоритете ракетницы. Исправленными считаются только подтверждённые случаи.

У прежнего кандидата `lateral-weapons` была изменена офлайн-разметка движения
после двух воспроизведённых боёв:
безопасный боковой манёвр получил приоритет над отходом назад.
Через API подтверждены 740/740 проверочных состояний и 13/13 новых
случаев из этих боёв. Старые ожидания сохранены в прежних файлах.
См. [журнал разработки](REGRESSION-DEVELOPMENT.md) и
[результаты диагностических боёв](../reports/v031-combat-counterfactuals.json).

## Запуск из корня репозитория

Нужны локальные каталоги весов из команды ниже. Запустить API:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-map2-explicit-v2 \
  --item-head-checkpoint checkpoints/laya-v031-item-balanced-v1 --item-category-facts \
  --command-compact-facts --enemy-without-goal \
  --enemy-rank-facts --weapon-compact-facts --movement-compact-facts \
  --head-checkpoint movement=checkpoints/laya-v031-movement-numeric-v1 \
  --head-checkpoint command=checkpoints/laya-v031-command-finish-retained-v1 \
  --head-checkpoint look_gate=checkpoints/laya-map3-look-floor-v2 \
  --head-checkpoint switch=checkpoints/laya-v031-switch-numeric-v1 \
  --head-checkpoint enemy=checkpoints/laya-v031-enemy-visibility-v2 \
  --head-checkpoint weapon=checkpoints/laya-v031-weapon-boundary-v2 \
  --device mps --port 8003
```

После `Application startup complete` в другом терминале:

```bash
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-finish-route-cases.json \
  --expect-head command=checkpoints/laya-v031-command-finish-retained-v1 \
  --output runs/v031-finish-route-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-teacher-switch-cases.json \
  --expect-head switch=checkpoints/laya-v031-switch-numeric-v1 \
  --output runs/v031-numeric-switch-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-visible-fight-cases.json \
  --expect-head command=checkpoints/laya-v031-command-finish-retained-v1 \
  --output runs/v031-visible-fight-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-key-command-cases.json \
  --expect-head command=checkpoints/laya-v031-command-finish-retained-v1 \
  --output runs/v031-visible-fight-key-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-observed-movement-errors.json \
  --expect-head movement=checkpoints/laya-v031-movement-numeric-v1 \
  --output runs/v031-retreat-key-movement-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-enemy-visibility-cases.json \
  --expect-head enemy=checkpoints/laya-v031-enemy-visibility-v2 \
  --output runs/v031-enemy-visibility-v2-enemy-api-repeat.json
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-weapon-boundary-cases.json \
  --expect-head weapon=checkpoints/laya-v031-weapon-boundary-v2 \
  --output runs/v031-enemy-visibility-v2-weapon-api-repeat.json
caffeinate -i .venv/bin/python tools/regression_suite.py \
  --endpoint http://127.0.0.1:8003/predict --tag v031-finish-retained-repeat --first-map MAP03 --keep-going
```

Проверки механизмов и противников сейчас возвращают код 1:
пройдены соответственно 13 из 14 и 11 из 16 случаев.
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

В `runs/ДАТА_v031-finish-retained-repeat_suite/` будут `suite.json`
и журналы. В каталогах карт — `video.mp4`, `report.html`, `summary.json`,
`verification.json`, решения, телеметрия и снимок исходников с SHA.
Во время игрового прогона не запускать обучение и дополнительные запросы
к модели: они изменят измеряемую задержку решений.

## Изменения модели и исполнителя

Исполнитель выхода теперь доходит до передней стороны выбранной линии,
прежде чем нажать USE. Отдельный опыт в движке воспроизвёл старую ошибку
за 350 тиков; с исправлением выход сработал через 74.

Команды, предметы, боевое движение и механизмы оценивают текстовая Laya и
дополнительные обучаемые числовые сети. Это изменение архитектуры модели.
В каждом из четырёх checkpoint есть `numeric-residual.safetensors`
и `numeric-residual.json`; SHA обоих файлов входит в API-манифест.
Головы оружия и противников дообучены при замороженном энкодере.
Контроллер исполняет выбранные моделью действия. Офлайн-разметчик в игре
не вызывается; все предложенные варианты действий сохраняются.

## Повторное обучение текущих голов

Из корня репозитория, с локальными родительскими checkpoint и готовыми
наборами данных, команды ниже создадут новые каталоги. Каталоги вывода
не должны существовать. Для команды нужен сохранённый кеш из завершённого
обучения и указанный игровой журнал; для механизмов создаётся новый кеш.
Числовые сети обучаются; текстовые веса
Laya остаются замороженными. Для команд синтетические примеры размечает
`training/route_finish.py`; для механизмов используются готовые
метки из записанных наблюдений.

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  ../../laya/.venv/bin/python training/finetune_numeric_retention.py \
  --base checkpoints/laya-v031-command-visible-fight-v1 \
  --data training/v031-command-finish-v1 \
  --cache runs/v031-command-finish-cache.json \
  --retention-run runs/20260928_050827_409927_v031-numeric-switch-map03-seed54 \
  --output checkpoints/laya-v031-command-finish-retained-retrained \
  --epochs 1200 --learning-rate .0001 --trainable-block hidden
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  ../../laya/.venv/bin/python training/finetune_numeric_switch.py \
  --base checkpoints/laya-v031-switch-collected-v1 \
  --data training/v031-switch-teacher-v1 \
  --cache runs/v031-switch-retrain-cache.json \
  --output checkpoints/laya-v031-switch-numeric-retrained \
  --epochs 500 --device mps
```

Это инструкции для текущей локальной директории. Родительские checkpoint
кандидата ещё не включены в публичный релиз. После повторного обучения
заменить пути `command` и `switch` на новые каталоги `*-retrained`
в команде API и в параметрах `--expect-head`, затем перезапустить сервер.
Для проверок выбрать новые файлы `--output`, а для игрового прогона —
новый `--tag`. Заново пройти все три карты: точность на записанных
наблюдениях не заменяет игровой проверки.

## Повторное обучение исходного комплекта observed

Это обучение с учителем. Офлайн-функция `training.route_resupply.labels` размечает наблюдения; ошибочные решения
прежних моделей не копируются как эталон. Добавлены синтетические сочетания
здоровья, инвентаря, расстояний и доступных объектов. Текстовые оценки для
синтетики заменяются случайными априорными оценками — это шум при обучении,
а не ответы энкодера на синтетические состояния.

Готовые данные: `training/v031-command-observed-v1` — 2777/864 примеров,
`training/v031-item-balanced-v2` — 915/267 примеров обучения/проверки.
Набор механизмов `training/v031-switch-regression-v2` содержит 757/246 примеров.
Записи и карты использовались при разработке. Эта проверка не измеряет
обобщение на новые карты. Точность на записанных проверочных состояниях:
99,88% для команд и 98,50% для предметов; на синтетических — 99,01% и 94,55%.
Точность головы механизмов — 88,21% на проверочных примерах. Новые 25
ошибок MAP03 проверены через API: 24 исправлены, в одном случае модель
продолжает выбирать патроны при запасе 70 пуль. Состояния из этой проверки
использовались при подготовке обучения; результат измеряет исправление
известных ошибок, а не перенос на новые ситуации.

Прежний набор API-проверок дал 77/92 совпадения. В шести случаях модель
выбрала аптечку при 38 HP вместо ожидаемого ключа; ещё девять случаев
расходятся в выборе предмета. Пять проверок отказа от обычной аптечки при полном
здоровье прошли. Исходные ожидания сохранены без изменений.

Все 12 добавленных проверок команд прошли через API. В обучающие данные
добавлены 83 наблюдения из последних MAP01/MAP02. Ошибке команды `exit`
назначен вес 4 в функции потерь; остальные команды имеют вес 1. Синтетический
инвентарь охватывает до 50 патронов дробовика, а не прежние 29.

В 49 исходных проверочных случаях ожидание изменено или уточнено для новой разметки;
прежние ожидания сохранены в `assertion_history`, а исходные файлы не заменены.
Это проверка согласованности разметки и модели. Зачёт прохождения даёт отдельный
игровой запуск с неизменными весами.

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune_numeric_residual.py \
  --base checkpoints/laya-v031-command-stable-v1 \
  --data training/v031-command-observed-v1 \
  --output checkpoints/laya-v031-command-observed-repeat \
  --cache runs/v031-observed-semantic-cache-repeat.json \
  --epochs 350 --augmentation 60000 --resupply-labels --device mps \
  --wide-inventory --wide-mechanisms --exit-loss-weight 4
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune_numeric_item.py \
  --base checkpoints/laya-v031-item-consistent-v1 \
  --data training/v031-item-balanced-v2 \
  --output checkpoints/laya-v031-item-balanced-repeat \
  --cache runs/v031-item-semantic-cache-repeat.json \
  --epochs 180 --augmentation 40000 --balanced-resupply-labels
```

В этих двух командах обучаются только числовые сети; текстовые головы
заморожены. Для предметов используется `training.route_resupply_balanced.labels`: ключ
сравнивается с полезными ресурсами по общей оценке. Для механизмов:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-map3-switch-route-v1 \
  --data training/v031-switch-regression-v2 \
  --output checkpoints/laya-v031-switch-regression-repeat \
  --epochs 3 --lr 0.00002 --cache-encoder --device mps --save-at-end \
  --category-weight map2_switch_loop=5
```

Голова механизмов обучается с замороженным энкодером. Для повторения нужны начальные веса из `--base` и подготовленные данные.
Использовать новые пути `--output` и `--cache`, чтобы сохранить предыдущий опыт.

Для проверки новых весов перезапустить сервер с путями `*-repeat`, заменить
пути `--expect-head` для команд и предметов, задать диагностике новый файл
`--output` и снова запустить все три карты.

Часть исходных состояний команд получена в опытах, где команды временно
выбирал офлайн-разметчик. Такие записи помечены как диагностические;
проверка полномочий модели их отклоняет. Они не засчитываются как прохождения
Laya. Предыдущие попытки сохранены в [журнале разработки](REGRESSION-DEVELOPMENT.md).

## Поправка лечения close-health

После обучения `observed` выполнить из корня репозитория:

```bash
.venv/bin/python -m training.relabel_survival \
  --rubric resupply_close_health --kind command \
  --data training/v031-command-observed-v1 \
  --output training/v031-command-close-health-v1 \
  --cache runs/v031-observed-semantic-cache-repeat.json \
  --output-cache runs/v031-command-close-health-cache.json
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune_numeric_residual.py \
  --base checkpoints/laya-v031-command-stable-v1 \
  --data training/v031-command-close-health-v1 \
  --output checkpoints/laya-v031-command-close-health-v1 \
  --cache runs/v031-command-close-health-cache.json \
  --epochs 350 --augmentation 60000 --close-health-labels \
  --wide-inventory --wide-mechanisms --exit-loss-weight 4
```

Каталоги вывода должны быть новыми. Переразметка требует исходных записей,
перечисленных в манифесте данных. Для повторного обучения на уже подготовленных
`training/v031-command-close-health-v1` достаточно второй команды;
отсутствующий файл кэша текстовых оценок будет рассчитан заново.

При угрозе ближе 20 м офлайн-разметка отдаёт бою приоритет над срочным
лечением, если до аптечки не менее 2 м. В остальных случаях приоритеты
`observed` сохранены. Контроллер не вызывает эту функцию в игре.

## Обучение movement-switch

Использовать новые каталоги вывода. Для движения:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune_numeric_movement.py \
  --base checkpoints/laya-map3-compact-movement-v1 \
  --data training/v031-movement-numeric-v1 \
  --output checkpoints/laya-v031-movement-numeric-repeat \
  --cache runs/v031-movement-semantic-cache-repeat.json \
  --epochs 250 --augmentation 40000
```

Для механизмов:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-v031-switch-regression-v1 \
  --data training/v031-switch-collected-v3 \
  --output checkpoints/laya-v031-switch-collected-repeat \
  --epochs 5 --lr 0.00002 --cache-encoder --device mps --save-at-end \
  --category-weight collected_key_route=5 \
  --category-weight map2_switch_loop=5 --category-weight map03_route=2
```

Движение размечено офлайн по наблюдаемой геометрии, механизмы — по
доступным альтернативам маршруту с уже полученным ключом. Энкодер заморожен.
Контроллер исполняет ответы обученных голов. Записи относятся к тем же картам,
на которых велась разработка; точность не измеряет перенос на новые карты.

После повторного обучения движения и механизмов в команде запуска API
заменить `movement=checkpoints/laya-v031-movement-numeric-v1` на
`movement=checkpoints/laya-v031-movement-numeric-repeat`, а
`switch=checkpoints/laya-v031-switch-collected-v1` на
`switch=checkpoints/laya-v031-switch-collected-repeat`. В проверке API
также заменить путь `--expect-head movement` на каталог `*-repeat`.
Остальные головы оставить из того же проверяемого комплекта.

## Обучение текущих движения и оружия

Движение обучается на уже подготовленном наборе с новой разметкой:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune_numeric_movement.py \
  --base checkpoints/laya-map3-compact-movement-v1 \
  --data training/v031-movement-lateral-v1 \
  --cache runs/v031-movement-lateral-repeat-cache.json \
  --output checkpoints/laya-v031-movement-lateral-repeat \
  --lateral-priority --epochs 250 --augmentation 40000 --device mps
```

Оружие обучается в два этапа на одном наборе:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-map3-compact-weapon-v1 \
  --data training/v031-weapon-boundary-v2 \
  --output checkpoints/laya-v031-weapon-boundary-repeat1 \
  --epochs 6 --lr 0.00002 --cache-encoder --device mps --save-at-end \
  --category-weight ssg_ammo_1=4 --category-weight ssg_ammo_0=2 \
  --category-weight ssg_ammo_2=2 --category-weight recorded_ssg_one_shell=5
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-v031-weapon-boundary-repeat1 \
  --data training/v031-weapon-boundary-v2 \
  --output checkpoints/laya-v031-weapon-boundary-repeat2 \
  --epochs 10 --lr 0.00001 --cache-encoder --device mps --save-at-end
```

В команде API заменить только головы movement и weapon на новые каталоги
`laya-v031-movement-lateral-repeat` и `laya-v031-weapon-boundary-repeat2`.
В двух командах проверки заменить соответствующие пути `--expect-head`.
После этого запустить весь набор карт заново. Совпадение с обучающей
разметкой не означает, что переобученный комплект уже прошёл уровни.


## Дообучение выбора противника

Набор `training/v031-enemy-visibility-v2` содержит 1492/381 примера.
Старые 1206/272 примера сохранены. Добавлены ошибки выбора невидимой
цели при доступной видимой и синтетические сочетания видимости,
расстояния и прежней цели. Для повторения двух этапов из корня репозитория:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-map3-ranked-enemy-v1 \
  --data training/v031-enemy-visibility-v2 \
  --output checkpoints/laya-v031-enemy-visibility-stage1-repeat \
  --epochs 6 --lr 0.00002 --cache-encoder --device mps --save-at-end \
  --category-weight recorded_invisible_first=4 \
  --category-weight mixed_visibility_synthetic=2
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-v031-enemy-visibility-stage1-repeat \
  --data training/v031-enemy-visibility-v2 \
  --output checkpoints/laya-v031-enemy-visibility-stage2-repeat \
  --epochs 8 --lr 0.00005 --cache-encoder --device mps --save-at-end \
  --category-weight recorded_invisible_first=10 \
  --category-weight mixed_visibility_synthetic=2 \
  --visible-first-category recorded_invisible_first \
  --visible-first-category mixed_visibility_synthetic \
  --visible-first-weight 4
```

Второй этап добавляет штраф за суммарную вероятность невидимой первой
цели только в двух новых категориях. Он не задаёт конкретного противника
среди видимых. STOP не участвует в этом штрафе. Прежняя функция обучения
полного порядка целей сохраняется, энкодер заморожен. В игровой
исполнитель и декодер этот штраф не добавляется.

Первый этап исправил через API 7/16 сохранённых ошибок; второй — 11/16.
На всех 381 проверочных примерах второй этап дал 285 совпадений полного
порядка и 313 совпадений первой цели. Общий зачёт трёх карт пока не получен.


Для проверки повторно обученных весов остановить сервер и заменить
в команде запуска `--head-checkpoint enemy` на
`enemy=checkpoints/laya-v031-enemy-visibility-stage2-repeat`.
После перезапуска заменить `--expect-head enemy` в API-проверке на тот же
путь и задать новый файл `--output`. Затем запустить игровой набор
с новым `--tag`. Без этих замен верхние команды проверяют сохранённый
`enemy-visibility-v2`, а не результат повторного обучения.

## Обучение команд и движения typed-key

Из корня репозитория, на готовых наборах данных:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune_numeric_residual.py \
  --base checkpoints/laya-v031-command-stable-v1 \
  --data training/v031-command-key-loop-v1 \
  --output checkpoints/laya-v031-command-key-loop-repeat \
  --cache runs/v031-key-command-semantic-repeat.json \
  --epochs 350 --augmentation 60000 --close-health-labels \
  --wide-inventory --wide-mechanisms --exit-loss-weight 4
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune_numeric_movement.py \
  --base checkpoints/laya-map3-compact-movement-v1 \
  --data training/v031-movement-typed-v1 \
  --output checkpoints/laya-v031-movement-typed-repeat \
  --cache runs/v031-typed-movement-semantic-repeat.json \
  --epochs 250 --augmentation 40000 --typed-retreat
```

Если файлов кэша нет, скрипты вычислят текстовые оценки заново. Для проверки
повторного обучения заменить пути `command` и `movement` в запуске API
и в `--expect-head` на соответствующие каталоги `*-repeat`, перезапустить
сервер и задать новые имена файлов результатов и тег игрового прогона.

Команды обучены на 2891/905 примерах. Скрипт `training/append_command_trace.py`
добавил 114/41 наблюдение из последних MAP02/MAP03 с флагами
`--close-health-labels --all-errors`; прежние данные и разбиение сохранены.
Новые записи разделены по времени внутри каждого прогона: первые 80%
для обучения, последние 20% для проверки. Это данные разработки на тех же
картах, а не независимая оценка обобщения.

Движение обучено на 1307/750 примерах. `training/build_typed_movement.py`
сохранил исходные наблюдения и их разбиение, поменял 25/25 меток и добавил
175/10 наблюдений. Числовой модуль получает два дополнительных признака:
число видимых Demon/Spectre и расстояние до ближайшего. Текстовая ветка
получает прежний вход без изменений. Офлайн-разметка предпочитает отход
назад при таком противнике ближе 12 м и свободных четырёх метрах позади;
в остальных случаях сохраняет прежний выбор бокового движения.
В игре эта функция не вызывается: ответ вычисляют сохранённые веса.

В воспроизведённом бою MAP02 исходная ветка погибла за 227 тиков,
потеряв 97 HP. Новая офлайн-разметка сохранила 97 HP и дала те же четыре
убийства. Цели и оружие оставались записанными, прицеливание и огонь
пересчитывались исполнителем. Это диагностический опыт, не прохождение
моделью; см. [результат](../reports/v031-demon-counterfactual.json).

Первоначальная проверка ключей содержала 16 состояний. В трёх из них
базовая команда уже была `pickup`, но отдельная голова осмотра выбирала
`look_back`; они сохранены в прежнем файле и не объявлены исправленными.
Отдельная проверка `v031-key-command-cases.json` содержит все 80 ошибок
именно базовой команды из того же прогона. Через API пройдены 80/80.
