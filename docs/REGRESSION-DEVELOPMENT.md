# Журнал промежуточных попыток исправления

Этот файл сохраняет команды и результаты прежних кандидатов. Текущая конфигурация и её статус — в [REGRESSION-FIX.md](REGRESSION-FIX.md).

## Промежуточный кандидат combat

Последний игровой комплект — `laya-v031-command-combat-v1`. Он прошёл MAP01
за 82 с: 15 убийств, без смертей, переход на MAP02 подтверждён. Проверка
навигации отметила остановку дольше 4 с. На MAP02 сохранились ранние смерти:
модель отвлекалась от боя на далёкие предметы. Диагностический прогон остановлен
до лимита 1800 с. Полного зачёта трёх карт пока нет.

Через API прошли 48 из 49 сохранённых состояний. Незакрытый случай оставлен
в отчёте: выбор близкого дробовика вместо атаки далёких видимых врагов.
Сейчас обучается `laya-v031-command-consistent-v1`: все наблюдения успешных
и неудачных игр размечены одним офлайн-правилом, без копирования ошибочных
действий старых моделей. Это не правило контроллера; в игре действие выбирает
обученная модель.

Команды ниже воспроизводят последний игровой комплект, включая его недостатки.

Предыдущая голова `laya-v031-command-lift-v1` прошла MAP01 за 116,629 с:
17 убийств, без смертей, переход на MAP02 подтверждён. На MAP02 она достигала
площадки с синим ключом, но выбирала другой лифт. В новом входе головы действий
есть отдельная строка с уже наблюдаемыми доступными ключами. Все варианты
действий сохранены; решение принимает модель. Для обучения добавлены коррекции
этого зацикливания и повторение успешного поведения на MAP01.

Также исправлен исполнитель выхода: он продолжал нажимать USE с обратной
стороны линии. Теперь он доходит до передней стороны выбранного моделью выхода.
В отдельном опыте движка ошибка воспроизводилась 350 тиков; с исправлением выход
сработал через 74 тика.

Повторить запуск из этой директории. В первом терминале:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-map2-explicit-v2 \
  --item-head-checkpoint checkpoints/laya-v031-item-regression-v1 --item-category-facts \
  --command-without-goal --command-key-facts --enemy-without-goal \
  --movement-compact-facts --enemy-rank-facts --weapon-compact-facts \
  --head-checkpoint movement=checkpoints/laya-map3-compact-movement-v1 \
  --head-checkpoint command=checkpoints/laya-v031-command-combat-v1 \
  --head-checkpoint look_gate=checkpoints/laya-map3-look-floor-v2 \
  --head-checkpoint switch=checkpoints/laya-map3-switch-route-v1 \
  --head-checkpoint enemy=checkpoints/laya-map3-ranked-enemy-v1 \
  --head-checkpoint weapon=checkpoints/laya-map3-compact-weapon-v1 \
  --device mps --port 8003
```

После `Application startup complete` во втором терминале:

```bash
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-combat-regression-cases.json \
  --expect-head item=checkpoints/laya-v031-item-regression-v1 \
  --expect-head command=checkpoints/laya-v031-command-combat-v1 \
  --output runs/v031-combat-api-repeat.json
caffeinate -i .venv/bin/python tools/regression_suite.py \
  --endpoint http://127.0.0.1:8003/predict --tag v031-combat-repeat
```

Набор запускает MAP01 seed 48 на 180 с, MAP02 seed 54 на 1800 с,
MAP03 seed 54 на 1200 с; везде skill 3. Для зачёта нужны выход живым,
не менее 105 тиков следующей карты, корректная запись и подтверждение того,
что решения принимала модель. Проверка качества навигации сохраняется отдельно.

## Промежуточный опыт: усреднение голов

Комплект с головой действий `laya-v031-command-mixed-v1` прошёл MAP01:
seed 48, skill 3, выход за 160,514 с, 18 убийств, без смертей. Переход на
MAP02 и исполнение решений модели подтверждены. Общая проверка качества
навигации не прошла: максимальная остановка 5,66 с при пороге 4 с.
MAP02 тем же комплектом зациклилась у лифта. Диагностический прогон
остановлен на 731,571 с из запланированных 1800 с; это не полный контрольный
результат. MAP03 этим комплектом не запускалась. Работа продолжается.

Голова действий — фиксированное усреднение двух обученных голов:
75% `laya-v031-command-exit-v1` и 25% `laya-v031-command-route-v1`.
На 803 проверочных примерах она дала 81,6% против 67% у исходной головы.
Все 23 сохранённых регрессионных состояния прошли проверку через API.
Выбор доли сделан на данных разработки; это не независимая оценка обобщения.

Повторить сборку усреднённых весов:

```bash
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  ../../laya/.venv/bin/python -m training.average_heads \
  --base checkpoints/laya-v031-command-route-v1 \
  --adapted checkpoints/laya-v031-command-exit-v1 --alpha 0.75 \
  --output checkpoints/laya-v031-command-mixed-v1
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  ../../laya/.venv/bin/python -m training.validate_averaged_head \
  --checkpoint checkpoints/laya-v031-command-mixed-v1 \
  --base checkpoints/laya-v031-command-route-v1 \
  --data training/v031-command-exit-v2/validation.json --device mps
```

Каталоги вывода должны быть новыми. Валидатор сохраняет `average-validation.json`
с результатом, SHA весов и данных. При улучшении он также записывает принятый
сервером файл `best-epoch.json`; поле `epoch: null` и метод проверки прямо
указывают, что это усреднённые веса, а не ещё одна эпоха обучения.

Запуск сервера этого промежуточного опыта из корня репозитория:

```bash
caffeinate -i ../../laya/.venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-map2-explicit-v2 \
  --item-head-checkpoint checkpoints/laya-v031-item-regression-v1 --item-category-facts \
  --command-without-goal --enemy-without-goal --movement-compact-facts \
  --enemy-rank-facts --weapon-compact-facts \
  --head-checkpoint movement=checkpoints/laya-map3-compact-movement-v1 \
  --head-checkpoint command=checkpoints/laya-v031-command-mixed-v1 \
  --head-checkpoint look_gate=checkpoints/laya-map3-look-floor-v2 \
  --head-checkpoint switch=checkpoints/laya-map3-switch-route-v1 \
  --head-checkpoint enemy=checkpoints/laya-map3-ranked-enemy-v1 \
  --head-checkpoint weapon=checkpoints/laya-map3-compact-weapon-v1 \
  --device mps --port 8003
```

После сообщения `Application startup complete` в другом терминале:

```bash
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-exit-regression-cases.json \
  --expect-head item=checkpoints/laya-v031-item-regression-v1 \
  --expect-head command=checkpoints/laya-v031-command-mixed-v1 \
  --output runs/v031-mixed-api-repeat.json
caffeinate -i .venv/bin/python tools/regression_suite.py \
  --endpoint http://127.0.0.1:8003/predict --tag v031-mixed
```

Дальше описаны подготовка данных и промежуточные опыты.


Первые два комплекта не завершили MAP01 за 180 секунд. Их результаты и
причины следующих опытов сохранены ниже.
Исходные неудачные прогоны описаны в [отчёте v0.3.0](REGRESSION-v0.3.0.md).

## Что воспроизведено

На сохранённом состоянии MAP01 API v0.3.0 при 100 HP выбирает
`pickup → Medikit #30`. Старая v0.2.0 на этом же состоянии тоже выбирает
аптечку. Проверка токенизации показала: здоровье, инвентарь и все варианты
предметов доходят до головы предметов целиком.

На MAP02 модель меняет цель между жёлтым ключом и лифтами, хотя красный
и синий ключи уже собраны. Для повторной проверки сохранены 17 состояний
обеих карт: `fixtures/v031-regression-cases.json`.

Исправление начинается с дообучения двух голов: выбора предмета и действия.
Энкодер заморожен. В набор входят коррекции неудачных прогонов и прежние
примеры MAP02/MAP03. Дополнительные синтетические ситуации меняют здоровье,
броню, патроны и наличие оружия; ключ предлагается не в каждой ситуации.
Варианты действий контроллера не ограничиваются новыми правилами.

## Повторить подготовку данных

Команды выполняются из корня `doomLaya`. В этой рабочей копии игровое
окружение — `.venv`, окружение с PyTorch и Laya — `../../laya/.venv`.
Нужны локальные записи четырёх прогонов, указанных ниже.

```bash
for kind in item command; do
  if [ "$kind" = item ]; then
    replay=(--replay training/map3-item-category-v4)
    base=checkpoints/laya-map3-item-category-v1
  else
    replay=(--replay training/map3-combat-priority-v2 --replay training/map2-root-goals-v1)
    base=checkpoints/laya-map3-combat-priority-v1
  fi
  .venv/bin/python -m training.build_regression_replay --kind "$kind" \
    "${replay[@]}" \
    --train-run runs/20260927_124122_585216_v030-regression-map01-seed48 \
    --train-run runs/20260927_124546_011663_v030-regression-map02-seed54 \
    --validation-run runs/20260926_204707_880341_map01-root-goals48 \
    --validation-run runs/20260926_201638_873591_map02-root-goals54 \
    --output "training/v031-$kind-regression-v1"
  USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
    ../../laya/.venv/bin/python -m training.filter_effective_inputs \
    --data "training/v031-$kind-regression-v1" --checkpoint "$base" \
    --output "training/v031-$kind-regression-v2"
done
```

Существующие выходные каталоги не перезаписываются. Для повторного опыта
задайте новые пути. Получено 4380/2336 примеров предметов и 4210/2091 примеров
действий: обучение/проверка. Совпадающих токенизированных входов после
подготовки не найдено; HP, инвентарь и ключи не обрезаны.

Разметка коррекций рассчитывается офлайн. Для проверки взяты другие прогоны,
но прежние веса уже видели часть старых примеров и те же карты. Этот набор
проверяет сохранение поведения и освоение коррекций, а не перенос на новые карты.

## Обучение и проверка сохранённых состояний

```bash
caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-map3-item-category-v1 \
  --data training/v031-item-regression-v2 \
  --output checkpoints/laya-v031-item-regression-v1 \
  --epochs 4 --lr 0.00005 --cache-encoder --device mps --save-at-end \
  --category-weight correction_weapon=2 --category-weight correction_health=2 \
  --category-weight synthetic_weapon=2
```

После завершения обучения запустите в отдельном терминале сервер на
свободном порту 8003. Здесь заменена только голова предметов; остальные
компоненты взяты из v0.3.0. Если на порту уже работает прежний кандидат,
остановите его через Ctrl+C перед запуском.

```bash
caffeinate -i ../../laya/.venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-map2-explicit-v2 \
  --item-head-checkpoint checkpoints/laya-v031-item-regression-v1 --item-category-facts \
  --command-without-goal --enemy-without-goal --movement-compact-facts \
  --enemy-rank-facts --weapon-compact-facts \
  --head-checkpoint movement=checkpoints/laya-map3-compact-movement-v1 \
  --head-checkpoint command=checkpoints/laya-map3-combat-priority-v1 \
  --head-checkpoint look_gate=checkpoints/laya-map3-look-floor-v2 \
  --head-checkpoint switch=checkpoints/laya-map3-switch-route-v1 \
  --head-checkpoint enemy=checkpoints/laya-map3-ranked-enemy-v1 \
  --head-checkpoint weapon=checkpoints/laya-map3-compact-weapon-v1 \
  --device mps --port 8003
```

В другом терминале:

```bash
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --expect-head item=checkpoints/laya-v031-item-regression-v1 \
  --output runs/v031-regression-api-check.json
```

Параметр `--expect-head` сверяет SHA-256 локального checkpoint с головой,
которую действительно загрузил API.

Код возврата 1 означает, что хотя бы одна ошибка сохранилась. Эти состояния
используются при разработке, поэтому даже 17/17 не заменяет игровой проверки.
После обучения нужны последовательные прогоны MAP01 (seed 48, 180 с), MAP02
(seed 54, 1800 с) и MAP03 (seed 54, 1200 с), skill 3, одним комплектом весов.
Условия первых двух карт и проверка записей приведены в
[инструкции регрессии](REGRESSION-v0.3.0.md).


## Проверка первой обученной головы

Голова `laya-v031-item-regression-v1` обучена за четыре эпохи.
Совпадения с проверочной разметкой выросли с 61,6% до 65,3%.
После замены только этой головы API прошёл 10 из 17 проверок вместо пяти.
Все пять состояний MAP01 теперь дают выбор дробовика `Shotgun #58`
вместо аптечки `Medikit #30` при 100 HP.

Остальные семь ошибок — выбор `use_switch` вместо `pickup` на MAP02.
Новая голова предметов во всех 12 состояниях этой карты выбирает жёлтый ключ,
но прежняя голова действий продолжает отправлять игрока к лифтам.
На этом этапе проверялись сохранённые состояния; игровой повтор ещё не проводился.

Голова действий обучена. Для повторения:

```bash
caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-map3-combat-priority-v1 \
  --data training/v031-command-regression-v2 \
  --output checkpoints/laya-v031-command-regression-v1 \
  --epochs 4 --lr 0.00005 --cache-encoder --device mps --save-at-end \
  --category-weight correction_useful_resource=3 \
  --category-weight replay_map3-combat-priority-v2_fight_near_door=15 \
  --category-weight replay_map3-combat-priority-v2_finish_fight=2
```

После его завершения в команде сервера замените только строку головы действий:

```bash
--head-checkpoint command=checkpoints/laya-v031-command-regression-v1
```

Перезапустите сервер. Для проверки двух новых голов:

```bash
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --expect-head item=checkpoints/laya-v031-item-regression-v1 \
  --expect-head command=checkpoints/laya-v031-command-regression-v1 \
  --output runs/v031-regression-combined-api.json
```

Запуск трёх карт без смены весов между ними:

```bash
caffeinate -i .venv/bin/python tools/regression_suite.py \
  --endpoint http://127.0.0.1:8003/predict --tag v031-regression
```

Скрипт фиксирует состав весов, последовательно записывает игры и проверяет
каждую запись. После первой непройденной карты серия останавливается; лимит
самого прогона не сокращается. Для проверки всех трёх карт независимо от
результата предыдущих добавьте `--keep-going`. Результат сохраняется в каталоге `SUITE`, файл `suite.json`.
Его `passed` означает, что все карты завершены с корректными записями и
подтверждённым исполнением решений. Общие проверки качества навигации
сохраняются отдельно в `results[].verification.passed`.


## Игровой повтор первого комплекта

Две новые головы прошли все 17 проверок сохранённых состояний. Однако в
`runs/20260927_144552_874207_v031-regression-map01-seed48` игрок не вышел из
MAP01 за 180 секунд: 12 убийств, ни одной смерти. Аудит подтвердил исполнение
решений модели. MAP02 и MAP03 этим комплектом не запускались: серия остановилась.

Среди 350 применённых решений 249 — подбор предметов. Он больше не стоял у
аптечки при полном здоровье, но продолжал уходить за припасами. Проверка
разметки выявила возможную причину: прежний офлайн-учитель назначал `pickup` даже для
125 состояний успешного старого MAP01, в которых игрок шёл к переключателю
или выходу.

Следующий опыт меняет разметку действий в `training/route_priority.py`:
видимые угрозы, ключи и необходимые припасы получают приоритет; необязательный
подбор больше не отодвигает маршрут. Правила работают только при подготовке
данных. Во время игры действия по-прежнему выбирает обученная модель.

В `fixtures/v031-route-regression-cases.json` добавлены два состояния первого
неудачного повтора. Теперь проверок 19. Они тоже входят в контур разработки.

```bash
.venv/bin/python -m training.build_regression_replay --kind command --route-priority \
  --replay training/map3-combat-priority-v2 --replay training/map2-root-goals-v1 \
  --train-run runs/20260927_144552_874207_v031-regression-map01-seed48 \
  --train-run runs/20260927_124122_585216_v030-regression-map01-seed48 \
  --train-run runs/20260927_124546_011663_v030-regression-map02-seed54 \
  --train-run runs/20260927_113829_722635_map03-item-category54 \
  --validation-run runs/20260926_204707_880341_map01-root-goals48 \
  --validation-run runs/20260926_201638_873591_map02-root-goals54 \
  --validation-run runs/20260927_091349_219964_map03-compact-enemy54 \
  --output training/v031-command-route-v1
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  ../../laya/.venv/bin/python -m training.filter_effective_inputs \
  --data training/v031-command-route-v1 \
  --checkpoint checkpoints/laya-v031-command-regression-v1 \
  --output training/v031-command-route-v2
caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-v031-command-regression-v1 \
  --data training/v031-command-route-v2 \
  --output checkpoints/laya-v031-command-route-v1 \
  --epochs 4 --lr 0.00005 --cache-encoder --device mps --save-at-end \
  --category-weight correction_route_continue_route=3 \
  --category-weight correction_route_missing_key=3 \
  --category-weight correction_route_fight=2 \
  --category-weight correction_route_all_keys_exit=4 \
  --category-weight replay_map3-combat-priority-v2_fight_near_door=15
```

Для этого опыта в команде сервера замените голову действий на
`command=checkpoints/laya-v031-command-route-v1`. Проверка сохранённых состояний:

```bash
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-route-regression-cases.json \
  --expect-head item=checkpoints/laya-v031-item-regression-v1 \
  --expect-head command=checkpoints/laya-v031-command-route-v1 \
  --output runs/v031-route-api.json
```


Проверка входов нового набора: 6158 примеров, без совпадающих входов между
частями и без противоречивых меток для одинаковых токенизированных входов.
В 2444 примерах обрезается конец строки `Items`. Среди них есть 406 коррекций
с выбранным предметом; его имя и идентификатор остаются во входе во всех 406.
Строки здоровья, инвентаря, ключей, врагов и механизмов не обрезаны.
Это не означает, что модель видит список предметов целиком.


## Второй игровой повтор и выбор выхода

Комплект с `laya-v031-command-route-v1` прошёл 19 проверок через API, но
MAP01 снова не завершён за 180 секунд. Запись:
`runs/20260927_152225_319380_v031-route-map01-seed48`.
После открытия прохода возникло 101 состояние, в котором модель выбирала
`pickup`, а новая разметка — `exit`. В обучающей части предыдущего набора
не было коррекций категории `route_available_exit`.

Следующий набор добавляет эти состояния только в обучение. Ещё 300 учебных
и 150 проверочных примеров моделируют завершённые механизмы: из наблюдения
убираются доступные механизмы и соответствующее действие, остальные факты
сохраняются. Активная поездка на лифте и подъём платформы выхода исключены
из таких преобразований. Это синтетические примеры, а не новые игры.

```bash
.venv/bin/python -m training.build_exit_regression \
  --replay training/v031-command-route-v2 \
  --failure runs/20260927_152225_319380_v031-route-map01-seed48 \
  --output training/v031-command-exit-v1
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  ../../laya/.venv/bin/python -m training.filter_effective_inputs \
  --data training/v031-command-exit-v1 \
  --checkpoint checkpoints/laya-v031-command-route-v1 \
  --output training/v031-command-exit-v2
caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-v031-command-route-v1 \
  --data training/v031-command-exit-v2 \
  --output checkpoints/laya-v031-command-exit-v1 \
  --epochs 3 --lr 0.00003 --cache-encoder --device mps --save-at-end \
  --category-weight failure_correction_route_available_exit=6 \
  --category-weight completed_mechanisms_exit=2 \
  --category-weight replay_map3-combat-priority-v2_fight_near_door=15
```

Для нового повтора замените в команде сервера голову действий на
`command=checkpoints/laya-v031-command-exit-v1`.

```bash
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-exit-regression-cases.json \
  --expect-head item=checkpoints/laya-v031-item-regression-v1 \
  --expect-head command=checkpoints/laya-v031-command-exit-v1 \
  --output runs/v031-exit-api.json
caffeinate -i .venv/bin/python tools/regression_suite.py \
  --endpoint http://127.0.0.1:8003/predict --tag v031-exit
```


## Коррекция петли у лифта MAP02

В `runs/20260927_155012_353035_v031-mixed-map02-seed54` модель переключалась
между лифтом #805 и далёкими припасами. После 420-й секунды найдено 210
ответов `pickup`, для которых новая офлайн-разметка требует `use_switch`.
Шесть состояний рядом с лифтом повторены через API: все шесть воспроизводят
ошибку. Прежние 23 проверки при этом проходят.

Следующий набор сочетает коррекции этой записи с повтором реальных решений
из успешных эпизодов MAP01 и MAP03. Каждый пятый 20-секундный блок выделен
для проверки; соседние состояния связаны, поэтому это проверка разработки,
а не независимое испытание на новых картах. Контрольный игровой повтор нужен
для всех трёх карт после изменения весов.

```bash
.venv/bin/python -m training.build_lift_regression \
  --failure runs/20260927_155012_353035_v031-mixed-map02-seed54 \
  --map01 runs/20260927_154727_384741_v031-mixed-map01-seed48 \
  --map03 runs/20260927_113829_722635_map03-item-category54 \
  --replay training/v031-command-exit-v2 \
  --cases fixtures/v031-exit-regression-cases.json \
  --answers runs/v031-mixed-api.json \
  --output training/v031-command-lift-v1
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  ../../laya/.venv/bin/python -m training.filter_effective_inputs \
  --data training/v031-command-lift-v1 \
  --checkpoint checkpoints/laya-v031-command-mixed-v1 \
  --output training/v031-command-lift-v2
caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-v031-command-mixed-v1 \
  --data training/v031-command-lift-v2 \
  --output checkpoints/laya-v031-command-lift-v1 \
  --epochs 3 --lr 0.00002 --cache-encoder --device mps --save-at-end \
  --category-weight near_lift_regression=8 \
  --category-weight retention_regression_cases=6 \
  --category-weight correction_route_missing_key=3 \
  --category-weight replay_completed_map01_exit=8 \
  --category-weight replay_completed_map03_exit=4
```

Получено 1434 учебных и 491 проверочный пример. После обучения в команде
сервера меняется только голова действий:
`command=checkpoints/laya-v031-command-lift-v1`.

```bash
.venv/bin/python diagnostics/probe_regression_cases.py \
  --endpoint http://127.0.0.1:8003/predict \
  --cases fixtures/v031-lift-regression-cases.json \
  --expect-head item=checkpoints/laya-v031-item-regression-v1 \
  --expect-head command=checkpoints/laya-v031-command-lift-v1 \
  --output runs/v031-lift-api.json
caffeinate -i .venv/bin/python tools/regression_suite.py \
  --endpoint http://127.0.0.1:8003/predict --tag v031-lift
```


## Повторить обучение с наблюдением ключей

Нужны исходные записи прогонов из команд ниже. Для повторного опыта замените
выходные каталоги новыми: существующие результаты не перезаписываются.

```bash
.venv/bin/python -m training.build_command_key_facts \
  --replay training/v031-command-lift-v2 \
  --failure runs/20260927_162439_799412_v031-exit-side-map02-seed54 \
  --success runs/20260927_162238_832673_v031-exit-side-map01-seed48 \
  --cases fixtures/v031-lift-regression-cases.json \
  --answers runs/v031-lift-api.json \
  --output training/v031-command-keys-v1
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  ../../laya/.venv/bin/python -m training.filter_effective_inputs \
  --data training/v031-command-keys-v1 \
  --checkpoint checkpoints/laya-v031-command-lift-v1 \
  --output training/v031-command-keys-v2
USE_TF=0 USE_TORCH=1 TOKENIZERS_PARALLELISM=false \
  caffeinate -i ../../laya/.venv/bin/python training/finetune.py \
  --base checkpoints/laya-v031-command-lift-v1 \
  --data training/v031-command-keys-v2 \
  --output checkpoints/laya-v031-command-keys-v1 \
  --epochs 3 --lr 0.00003 --cache-encoder --device mps --save-at-end \
  --category-weight key_observed_pickup=4 \
  --category-weight key_color_contrast_pickup=3 \
  --category-weight near_lift_regression=4 \
  --category-weight retention_probe=6 \
  --category-weight retention_regression_cases=6
```

Получено 1816 учебных и 568 проверочных примеров. Энкодер заморожен.
Выбрана вторая эпоха: 87,7% правильных ответов на проверочных примерах.
Данные включают поведение на тех же картах и временные блоки одного прогона;
эта оценка не показывает перенос на новые карты. SHA весов:
`bf729017cf175c610945ab9cfc46226b25481c23ad1008ddb7f251901d40ce30`.


## Числовые головы и проверка ресурсов

Текстовая голова после нескольких дообучений продолжала ошибаться в сравнении
здоровья, запаса патронов и расстояний. К замороженным текстовым оценкам добавлены
обучаемые числовые сети команд и предметов. Это расширение архитектуры Laya;
офлайн-разметчик в обычном игровом API не вызывается.

| Комплект | MAP01 seed 48 | MAP02 seed 54 |
| --- | --- | --- |
| `numeric-v2` | 92,971 с, без смертей | Многократные смерти; прерван |
| `old-movement` | 78,229 с, без смертей | 5 смертей за 122,371 с; прерван |
| `survival` | Не пройден за 180 с: выбор Stimpack при полном здоровье | Не запускался после провала MAP01 |
| `numeric-items` | 82,343 с, без смертей | Более 10 смертей; прерван без ключей |

Для каждого комплекта сохранены отдельные каталоги `runs/` с его именем в теге.
Результаты разных комплектов не объединяются в успешную регрессионную проверку.

В контрольном опыте `v031-reference-nearest-map02` заменён только выбор врага:
ближайший видимый первым, остальные по расстоянию. За 180 с получено 36 убийств
и 3 смерти без выхода. Такой опыт проверяет гипотезу о выборе цели; он не
засчитывается как прохождение Laya.

В разметке ресурсов найдено два ограничения: заряженный обычный дробовик
мешал выбору ещё не полученной двустволки, а пополнение дробовика начиналось
лишь при запасе меньше четырёх патронов. `training/route_resupply.py` возвращает
приоритеты получения оружия и снабжения из прежних офлайн-учителей: учитывать
неполученное оружие, пополнять дробовик при запасе меньше 20 патронов, брать
нужные здоровье и броню. Бой имеет приоритет для врагов ближе 20 метров;
срочная аптечка и близкое улучшение оружия могут его прервать. Эта разметка проверена диагностикой `v031-reference-resupply-map02`: за 600 с
получено 97 убийств, 2 смерти и 40 подборов. Красный ключ был получен в первой
жизни; выход не достигнут. Обучение Laya на этих приоритетах проверяется отдельно.

Диагностические записи содержат `diagnostic_policy`, пометку `REFERENCE POLICY`
в видео и исходные ответы модели. Проверка полномочий модели отклоняет их,
даже если удалось закончить карту. Они пригодны для анализа и обучения,
но не подтверждают прохождение обученной моделью.


## Выход после сбора ключей и движение на MAP03

`resupply` прошёл MAP01 за 151,943 с. На MAP02 игрок без смертей получил все
три ключа, но выбирал лифты вместо выхода. В обучение команд добавлены 83
наблюдения из этих двух прогонов, вес ошибки `exit` увеличен до 4, диапазон
синтетического инвентаря расширен до 50 патронов дробовика.

Следующий комплект, `exit-resupply`, прошёл MAP01 за 104,629 с и MAP02 за
354,229 с без смертей. Переходы на следующие карты и исполнение решений
модели подтверждены. MAP03 за 1200 с не пройдена: 349 убийств, 11 смертей.
Все три результата относятся к одному манифесту:
`b7a9ccf82e7e07f3784882307840294da788d666603cdde0258b9cf4502e720c`.

Для проверки движения сохранены 65 состояний проваленного MAP03. В 54 из них
голова MAP02 выбирала просвет меньше метра, хотя другое направление давало
не менее четырёх метров. Голова `laya-map3-compact-movement-v1` при повторе
через API не выбрала ни одного просвета меньше метра; с офлайн-разметкой
совпали 58 из 65 ответов. Эта проверка не подтверждает прохождение карты.
В комплекте `compact-movement` заменена только голова движения и включена
соответствующая проекция наблюдений. Все три карты проверяются заново.


## Переключение целей MAP02 и приоритет ключей MAP03

В `compact-movement` MAP01 пройдена за 170,114 с без смертей. MAP02 прервана
на 586,143 с: игрок выжил, убил 28 врагов, но не получил ключей. Выбор
переключался между механизмами 662 и 805. Между 160-й и 250-й секундами
координаты не менялись: игрок только поворачивался. Влияние смены цели
проверяется отдельно. Для дообучения выбора механизма сохранены 96 примеров
с вариантами прежней цели; исходные данные MAP03 оставлены. Новый набор
`training/v031-switch-regression-v1` содержит 776/248 примеров.

На MAP03 найдены 49 решений, где разметка ставила ключ выше более полезного
лечения. Например, при 32 HP модель выбирала ключ в 37 метрах, хотя аптечка
была в 13 метрах. Восемь состояний сохранены в
`fixtures/v031-balanced-resupply.json`. Офлайн-вариант
`training/route_resupply_balanced.py` сравнивает предметы по прежней общей
оценке полезности; команды не меняет. Игровой эффект проверяется отдельно
через явно помеченный диагностический режим выбора предметов.

MAP03 комплекта `compact-movement` завершила бюджет 1200 с без выхода:
314 убийств, 9 смертей, 42 подбора. Диагностический запуск
`v031-reference-balanced-items-map03` меняет только выбор предметов;
остальные решения остаются у той же Laya. Прогон прерван на 184,143 с: 59 убийств, 3 смерти, 12 подборов, без выхода.
Следующая диагностика `v031-reference-key-health-map03` заменяла только
выбор ключа вместо лечения; после аптечки здоровье выросло с 27 до 37.
Одной этой коррекции не хватило для выхода; прогон также прерван перед обучением.


## Дообучение по наблюдениям MAP03

В полном `compact-movement` MAP03 найдено 76 решений `pickup` вместо
размеченного `use_switch`. В наблюдениях было 7–11 механизмов, тогда как
синтетический генератор охватывал только 0–3. Новый параметр
`--wide-mechanisms` расширяет диапазон до 0–12; прежнее поведение генератора
без этого параметра сохранено. В набор команд добавлены 111 наблюдений
с сохранёнными текстовыми оценками Laya.

Подготовлены три независимых дообучения: команд — на ошибках MAP03,
предметов — на сравнении ключей с полезными ресурсами, механизмов — на
переключении целей MAP02. Офлайн-функции в игровом API не вызываются.
Новая проверка `fixtures/v031-observed-regression-cases.json` содержит
25 записанных ошибок команд и предметов. Прежний API получил 0/25, новый — 24/25. Оставшаяся ошибка —
выбор патронов при запасе 70 пуль вместо продолжения маршрута.
Общий игровой запуск ещё не завершён.


Комплект `observed` прошёл MAP01 за 164,971 с и MAP02 за 500,971 с, обе
без смертей. Выходы, переходы на следующие карты, видео и полномочия модели
подтверждены. Отдельная навигационная проверка не прошла: MAP01 — 33,71 с
без новой области; MAP02 — 25,06 с без новой клетки и 107,2 с без новой
области при порогах 25 с. MAP03 продолжается теми же весами.

## Завершение observed и поправка лечения

`runs/20260927_234150_998243_v031-observed_suite/suite.json`: один комплект
прошёл MAP01 за 164,971 с и MAP02 за 500,971 с без смертей. MAP03 не пройдена
за 1200 с: 10 смертей, 354 убийства, 55 подборов. Ошибок API нет. Для MAP03
медиана RTT — 304,91 мс, p90 — 362,34 мс; медиана применения решения —
457,143 мс. Видео и полные записи сохранены.

На 533,6–534,1 с игрок с 18 HP шёл к аптечке на расстоянии 4–5 м, пока
призраки приблизились до 1,5–2 м. Прежняя разметка требовала лечения даже
при этой угрозе. Поправка `training.route_resupply_close_health` оставляет
срочное лечение во время ближнего боя только при расстоянии до предмета
меньше 2 м. Это офлайн-разметка; исполнитель не вызывает её в игре.
На записанных успешных MAP01/MAP02 поправка не меняет решений.

В `fixtures/v031-close-health-regression-cases.json` четыре таких состояния.
Старый API дал 0/4; это проверка воспроизведения, не доказательство исправления.
В данных команд изменены 27 обучающих и 3 проверочных метки из 2777/864.
Состояния, разбиение и текстовые оценки сохранены. Кандидат меняет
только голову команд; результат его обучения и начало игровой проверки — ниже.

`close-health` обучен за 102,58 с; выбран epoch 236. Совпадения с разметкой:
862/864 на записанных состояниях и 98,77% на синтетических. Через API
получено 4/4 на эпизодах лечения, 23/25 на предыдущих ошибках MAP03
и 77/92 на старом наборе. Новое несовпадение — отказ от подбора патронов
на расстоянии 19,67 м при 12 зарядах дробовика; прежнее — подбор пуль
при запасе 70. Ни одно ожидание в этих наборах не переписано.

Suite `runs/20260928_001834_412074_v031-close-health_suite` использует
манифест `c346dbc6e08154bcb852006993cfbc98aa2fb212134a0add518890e5553f7aee`.
На момент старта была зачтена MAP01 без смертей; дальнейшие результаты
MAP02 и MAP03 описаны ниже.
Изменена только голова команд. Проверки кода: 278 запущено, 269 прошли,
9 пропущены в игровом окружении и затем прошли в окружении PyTorch.

Отдельный разбор завершённого MAP03 `observed` обнаружил 111 расхождений
с прежней разметкой движения из 838 боевых решений; 46 — при здоровье
ниже 40. Файл `runs/v031-observed-movement-audit.json` содержит состояния.
Это кандидаты для следующего исправления, не доказанная причина всех смертей.

### Повторный обход синего ключа на MAP02

MAP02 `close-health` прерван на 481.771 с: игрок жив, синий ключ
получен, остальные не взяты. После получения ключа модель продолжала
выбирать лифт к синему ключу. Прогон не засчитан; видео и записи сохранены.
Затем MAP03 запущена теми же весами для проверки поправки лечения;
её итог приведён в следующем разделе.

`training/build_collected_key_switches.py` создаёт офлайн-примеры выбора
альтернативы уже завершённому маршруту к ключу. Начатый подъём на ближайшем
выбранном лифте сохраняется. Добавлены 116 обучающих и 23 проверочных
примера, включая варианты прежней цели; старые данные MAP02/MAP03 сохранены.
В `fixtures/v031-collected-key-switch-v2-cases.json` — 12 записанных ошибок.
На этом этапе голова механизмов ещё не была обучена.

### Завершение close-health и обучение движения/механизмов

MAP03 `close-health` не пройдена за 1200 с: 9 смертей, 334 убийства,
41 подбор, ошибок API нет. Медиана RTT — 301,67 мс, p90 — 363,16 мс.
Проверка трёх карт `20260928_001834_412074_v031-close-health_suite` не зачтена.

Старая голова механизмов разошлась с новой разметкой во всех 12 случаях;
в девяти она возвращалась к уже полученному ключу;
новая обучена на `training/v031-switch-collected-v3` (873/269 примеров).
Выбран epoch 5: новые случаи — 21/23, прежний цикл MAP02 — 13/16,
маршрут MAP03 — 72/80 вместо 74/80; остальные механизмы — 126/150.
Это улучшение новых примеров с небольшим ухудшением сохранённых.

Числовая поправка движения обучена на `training/v031-movement-numeric-v1`:
1132/740 записанных состояний и 40000 синтетических. На проверочных
состояниях точность выросла с 86,35% до 100%; на 5000 синтетических — 100%.
Выбран epoch 91. Записанные текстовые оценки проверены свежим `Agent.predict`:
максимальное отклонение вероятности — 0,00009934. Разметка использует ту же
округлённую геометрию, что получает модель; карты использовались при разработке.
Это не оценка обобщения на новые карты.

До обучения старый API дал 0/14 на сохранённых ошибках движения и 0/12
на возврате к полученному ключу. Ниже приведены результаты последующей проверки новых весов через API
и начала игрового прогона. Полный набор кода — 289 тестов;
13 пропущенных в игровом окружении проверены в окружении PyTorch.

Через новый API подтверждены 740/740 состояний движения, 14/14 его
сохранённых ошибок и 4/4 случаев лечения. Механизмы дали 232/269 —
в точности как при обучении. В наборе из 12 случаев точных совпадений 9;
ни одно новое решение не возвращается к синему ключу, прежних возвратов
было 9. Одно из 13 одинаковых наблюдений даёт разный выбор при смене
прежней цели: между 662 и 728; остальные 12 групп стабильны.

Общий прогон: `runs/20260928_010105_348569_v031-movement-switch_suite`.
Манифест весов — `559b551f858e034475f9c09f1ae468296babc3c2346f0bb5481bd6c34d6ab513`.
Первый результат этого прогона — прохождение MAP01, описанное ниже.

MAP01 `movement-switch` зачтена: выход за 102,914 с, 0 смертей, 15 убийств,
10 подборов. Переход на MAP02 подтверждён. Проверки навигации прошли:
максимум без продвижения — 2,2 с, без новой области — 7,8 с.
Медиана RTT — 271,10 мс, p90 — 312,84 мс; применение решения — 457,143 мс.
Запись: `runs/20260928_010105_482513_v031-movement-switch-map01-seed48`.

### Найденная граница патронов супердробовика

MAP02 `movement-switch` прерван на 444,629 с после одной смерти. Зафиксированы
107 выборов супердробовика при одном заряде. Вариант содержал `Loaded: no`;
обычный дробовик мог стрелять этим зарядом. Пока выбиралось другое оружие,
исполнитель удерживал стрельбу выключенной, как и требуется при смене оружия.
Веса во время игры не менялись. MAP03 продолжила проверку того же комплекта.

В прежнем обучении оружия 25 примеров с супердробовиком: 6 с нулём зарядов
и 19 с запасом от 8. Примеров с одним зарядом нет. Готовится дополнение
данных для границы 0/1/2 заряда с сохранением примеров MAP03.

### Дополнение набора оружия

Из завершённого MAP02 извлечено 135 решений, в которых модель выбрала супердробовик с одним зарядом. Из них 107 пришлись на первый непрерывный эпизод ошибки, описанный выше. Сохранены 12 состояний для повторной проверки через API.

Набор `training/v031-weapon-boundary-v1` сохраняет старые примеры оружия и добавляет случаи с 0, 1 и 2 зарядами. В нём 1025 обучающих и 849 проверочных примеров после удаления повторов. Метки использует прежний офлайн-приоритет оружия: супердробовик требует двух зарядов, обычный дробовик — одного. Четыре проверки разметки и инструмента повторного запроса прошли. На момент подготовки данных обучение ещё не запускалось: шёл игровой прогон MAP03.

### Завершение movement-switch

Весь комплект проверен без смены весов:
MAP01 завершена за 102,914 с без смертей, все проверки навигации пройдены.
MAP02 прервана на 444,629 с после ошибки оружия, одна смерть.
MAP03 не завершена за 1200 с: 10 смертей, 331 убийство, 36 подборов,
ошибок API нет. Медиана RTT MAP03 — 309,03 мс, p90 — 365,12 мс;
медиана применения решения — 457,143 мс. Общий зачёт не получен.

Проверка головы осмотра по завершавшемуся журналу не обнаружила расхождений
в первых 1668 решениях, включая 19 наблюдений завершённого разворота.
Это проверка соответствия прежней разметке, а не доказательство качества тактики.

Все 12 сохранённых ошибок оружия воспроизведены через старый API.
После токенизации нового набора не удалено ни одного примера:
1025 обучающих и 849 проверочных. Запущено дообучение головы оружия;
во время обучения игровые регрессионные прогоны не идут.

### Контрфактическая проверка движения MAP03

Два отрезка заново воспроизведены в движке по записанным кнопкам.
Исходный и пересчитанный варианты совпали с записью. В диагностических
ветках заменены варианты движения или оружия. Записанные цели сохранены;
наведение и стрельба пересчитаны исполнителем по изменившемуся состоянию.
Это не запуск модели.

В окне 37661–37761 исходное движение оставило 5 HP из 50 и дало три
убийства. Движение влево сохранило 50 HP при тех же трёх убийствах;
стояние на месте — 50 HP и два убийства, вправо — 29 HP и три убийства.
Постоянный отход назад повторил исходный результат. В том же окне
замена пулемёта на дробовик или ракетницу привела к смерти раньше конца
отрезка, поэтому приоритет оружия для этого боя не менялся.

В окне 19305–19555 исходный вариант оставил 17 HP из 37 и дал два
убийства. Боковые варианты сохранили 37 HP и дали по одному убийству.
Эти локальные опыты поддерживают проверку бокового движения, но не
доказывают, что оно всегда лучше. Сводка: [контрфактические бои](../reports/v031-combat-counterfactuals.json).

Для нового кандидата изменена офлайн-разметка движения: сохранять безопасный
боковой ход при просвете от 2 м; если он закрыт — выбирать свободную сторону;
отходить назад при близкой угрозе, когда сбоку тесно. Все четыре варианта
по-прежнему выбирает обученная модель. В контроллер эта разметка не добавлена.

В наборе остались прежние 1132/740 наблюдений и их разделение.
Изменены 307 обучающих и 270 проверочных меток; прежняя метка сохранена
в `previous_label`. Старые файлы ожиданий не менялись.
Голова `laya-v031-movement-lateral-v1` дала 740/740 совпадений и 100%
на синтетической проверке, выбрана эпоха 23. Это соответствие новой
разметке; результат API и нового игрового прогона на этом этапе ещё не получен.


### Проверка lateral-weapons

Оружие дообучено в два этапа на дополненном наборе. Итоговая голова
`laya-v031-weapon-boundary-v2` дала 824/849 совпадений через API и
исправила 12/12 сохранённых ошибок выбора супердробовика с одним зарядом.
Остались 25 расхождений с разметкой, включая два выбора пустого пулемёта
в синтетических состояниях. Все ошибки оружия исправленными не считаются.
Движение подтвердило через API 740/740 проверочных состояний и
13/13 состояний из двух диагностических боёв.

Общий прогон — `runs/20260928_015057_556384_v031-lateral-weapons_suite`;
манифест — `69ee759b6d00746f878de30be316c967c5239d9ac38a430211754e2a0b6aab8e`.
MAP01 завершена за 108,057 с: 0 смертей, 14 убийств, 11 подборов,
переход на MAP02 и все проверки навигации подтверждены.
Медиана RTT — 258,25 мс, p90 — 296,52 мс.

MAP02 завершена за 776,286 с: 1 смерть, 99 убийств, 26 подборов,
переход на MAP03 и полномочия модели подтверждены. Медиана RTT —
304,82 мс, p90 — 336,31 мс. Применение решения на обеих картах —
457,143 мс по медиане. MAP02 не прошла все проверки качества:
максимум без новой ячейки — 46,83 с, без новой области — 91 с,
неподвижность — 4,37 с; смена оружия — 1,543 с при пороге 1,5 с.
Выбор улучшения самой моделью занял не более 0,886 с.
MAP03 на момент этой записи ещё выполняется с теми же весами.


### Завершение lateral-weapons и выбор противника

MAP03 не завершена за 1200 с: 8 смертей, 312 убийств, 75 подборов,
ошибок API нет. Медиана RTT — 299,17 мс, p90 — 361,91 мс.
Запись и исполнение решений модели проверены; общего зачёта трёх карт нет.
В последней жизни осталось 43 HP, 100 брони и два ключа.

Два дополнительных опыта меняли первую цель, сохраняя записанное движение,
оружие и прочие кнопки; наведение и стрельба пересчитывались. Исходные
и пересчитанные ветки совпали с записями. В окне 1940–2068 выбор видимого
стрелка #97 оставил 57 HP вместо 6 при тех же четырёх убийствах.
В окне 12238–12495 удержание демона #144 оказалось хуже:
смерть через 169 тиков без убийств; исходная ветка прожила 257 тиков
и закончилась с 1 HP и двумя убийствами. Это локальные диагностические
ветки, а не прохождения модели. Они не обосновывают общее правило
удержания любой цели.

Следующее дообучение ограничено ошибками выбора невидимого противника,
когда в вопросе предложен видимый. Добавлены 30 обучающих и 13 проверочных
записанных состояний, а также 256/96 синтетических. Исходные 1206/272
примера головы противников сохранены вместе с метками и разделением.
Новый набор — 1492/381; он использует прежнюю архитектуру головы и
замороженный энкодер. Новые исправления разделены по эпизодам,
это проверка на картах разработки, не оценка переноса на новые карты.


В дополнительной ветке первого боя выбор другой видимой цели #95
оставил 51 HP при тех же четырёх убийствах. Таким образом, в этом окне
обе проверенные видимые цели дали больше оставшегося здоровья, чем
исходный выбор невидимой цели. Это по-прежнему локальный опыт.

Первое дообучение головы противников выбрало эпоху 5 из 6.
Через API полная последовательность совпала в 279/381 случаях,
первая цель — в 299/381. На прежних 272 примерах полное совпадение
выросло с 205 до 212, первая цель — с 216 до 225.
Из 16 сохранённых ошибок видимости исправлены 7; прежний API давал 0/16.
Этого недостаточно для зачёта исправления.

На втором этапе к обучению добавлен отдельный штраф за вероятность
невидимой первой цели. Он применяется только к новым категориям
исправлений и синтетики; исходные метки сохранены. Декодер игры
не меняется. Проверки градиента подтверждают, что штраф повышает
оценки видимых целей, не затрагивает STOP и не добавляет меток
к прежним категориям.


Второй этап завершён, выбрана эпоха 2 из 8. Через API подтверждены
285/381 совпадение полного порядка и 313/381 первой цели.
Прежний набор: 213/272 полного порядка и 231/272 первой цели.
В сохранённых ошибках исправлены 11/16, пять остаются. В полной
проверке остаются 10 ошибок видимости в прежних примерах, 18 в синтетике
и четыре в новых проверочных состояниях. Оба выбора из первого
диагностического боя теперь отдают предпочтение видимой цели.
Полный игровой прогон нового комплекта начинается без смены других голов.


Общий прогон `enemy-visibility-v2`:
`runs/20260928_025324_371261_v031-enemy-visibility-v2_suite`.
Манифест весов — `26ae696f6da23efce4c521c6a44647272d89ce8eaeb8c05a80905e9d0e0ca22a`.
MAP01 завершена за 138,571 с без смертей: 15 убийств, восемь подборов.
Переход на MAP02, запись и исполнение решений модели подтверждены.
Осталось замечание к навигации: максимум без новой области — 34,09 с.
Медиана RTT — 267,46 мс, p90 — 298,12 мс; применение — 457,143 мс.
MAP02 прервана на 1413,971 с: 161 убийство, три смерти, 72 подбора,
без выхода. Ошибок API нет. Медиана RTT — 322,92 мс, p90 — 339,91 мс;
медиана применения решения — 457,143 мс. Эта карта не зачтена.

После третьей смерти повторился маршрут через лифт 805 к синему ключу
и обратно. В решении 2410 (тик 43323) BlueCard доступен в 7,5 м,
врагов и незавершённого подъёма нет. Проекция сохраняет эти факты.
Текстовая голова выбирает `pickup` с вероятностью 1,0; числовой модуль
меняет итог на `use_switch` с вероятностью 0,616. Офлайн-разметка требует
`pickup`. Этот случай предстоит повторить через API и добавить в обучение.

MAP03 прервана на 288,943 с после трёх смертей. Лимит 1200 с не исчерпан;
прохождение этой сборкой не подтверждено. Общий прогон завершён без зачёта.

## Ошибка команды у ключа и тип противника для движения

На MAP02 найдено 80 состояний, где базовая команда ошибочно выбирала
действие вместо подбора доступного ключа. Ещё три состояния из первоначальной
проверки относятся к отдельной голове осмотра: базовая команда там уже
выбирала `pickup`. Они сохранены и не включены в число исправленных ошибок.

В данные команд добавлено 114/41 наблюдение, итог — 2891/905. Новая голова
`laya-v031-command-key-loop-v1` выбрана на эпохе 331 из 350. Через API:
903/905 по полной выборке, 108/108 в категории отсутствующего ключа,
80/80 новых ошибок команды. Остались два расхождения с разметкой:
рядом с дверью и у платформы выхода.

Диагностический бой MAP02, тики 7800–8027: исходная и пересчитанная ветки
совпали точно и погибли, начав с 97 HP; четыре убийства. Отход назад сохранил
97 HP, три убийства. Разметка с учётом видимых Demon/Spectre сохранила
97 HP и четыре убийства. Этот опыт не использует нейронный выбор и не
засчитывается как игровое прохождение.

Для движения добавлены два наблюдаемых числовых признака. Старый текстовый
вход и замороженные веса текстовой ветки не меняются. Модуль
`training/typed_movement.py` используется только при подготовке обучения
и в диагностике; игровой API его не импортирует. Исполнитель движения
не менялся. Новый набор — 1307/750 примеров; выбрана эпоха 250 из 250.
Через API: 750/750 по полной выборке, 16/16 случаев с демонами и 13/13
прежних случаев бокового движения. Синтетическая проверка обучения —
4997/5000, поэтому полного покрытия всех возможных состояний не заявлено.

Проверки кода: 308 тестов, из них 17 пропущены в игровом окружении;
все соответствующие проверки выполнены в окружении с Torch (31 тест).
Следующий общий прогон `typed-key` начинается с MAP03; MAP01 и MAP02
остаются обязательными с прежними seed и лимитами.

Запущен `runs/20260928_035050_218570_v031-typed-key_suite`,
манифест весов `f233ec1e8630ad920d11e0b325736d0b4fdda143fabef7b688357b65dcfae115`.
MAP03 не завершена за 1200 с: 327 убийств, девять смертей, 80 подборов,
ошибок API нет. MAP01 и MAP02 этим комплектом не запускались: проверка
остановилась после первой неудачи.

### Проверка разметки на полном маршруте

Офлайн-разметчик `focused-retreat` повторно прошёл MAP03 seed 54 с skill 3
за 374,714 с без смертей: `runs/v031-teacher-ceiling-focused`.
Использованы текущий исполнитель, задержка 16 тиков и прежние варианты
стрельбы, механизмов и ресурсов. Результат совпал со старой записью
`map03-focused-queue-floor-geometry54-delay16`.

Замена только движения на `training.typed_movement.choose_typed` привела
к смерти на 63,571 с: `runs/v031-teacher-ceiling-typed`.
Остальные функции выбора сохранены. Этот диагностический запуск остановлен
по заранее заданному лимиту одной смерти; это не провал полного 1200-секундного
бюджета. Сравнение показывает, что улучшение двух отдельных боёв не переносится
на первый проход полного маршрута. Оба запуска используют офлайн-правила,
не Laya, и не засчитываются как прохождение модели.

Следующий кандидат `retreat-key` возвращает обученную голову
`laya-v031-movement-numeric-v1`. Головы команд, предметов, противников,
оружия, механизмов и осмотра сохранены из `typed-key`. Исполнитель не меняется.
`retreat-key` прерван на 553,2 с после четырёх смертей: 145 убийств,
16 подборов, ошибок API нет. Лимит MAP03 не исчерпан, MAP01 и MAP02
не запускались. Манифест —
`cd5cf0f6ec56d255d0b67d192711b8878cdbd5eace686265954dbfecaad6b157`.

### Команды и предметы в успешном офлайн-разметчике

Замена его команд и предметов на текущие функции `route_resupply_close_health`
и `route_resupply_balanced` привела к первой смерти на 131,057 с.
Запуск `runs/v031-teacher-current-resupply` имел лимит одной смерти.
При сохранении боя с видимыми врагами этот вариант прошёл карту
за 369,171 с без смертей: `runs/v031-teacher-visible-resupply`.
Повтор с отдельной функцией меток `training.route_visible_resupply.labels`
получил тот же результат: `runs/v031-teacher-learnable-visible`.
Это три офлайн-опыта без нейронного выбора.

Новая функция сохраняет бой при видимом враге или запомненном враге ближе
20 метров. Во время боя допускает близкую аптечку при HP ниже 25 и первое
сильное оружие при безопасном расстоянии до врага. Обычные припасы ждут
окончания боя. Функция используется только в обучении и диагностике.

На записанных наблюдениях успешного старого разметчика текущий API дал:
команды 339/365, предметы 93/99, механизмы 101/115, движение 102/102,
оружие 342/365, первая цель 97/102, весь порядок целей 93/102.
Это сопоставление с эталонной траекторией, а не новый игровой запуск.
Все 23 расхождения оружия появились в конце маршрута при пустом пулемёте:
модель выбирала ракетницу при доступном дробовике. Их ещё не исправляли.

В прерванной игре сохранены 12 случаев переключения с боя на другую команду.
Все 12 воспроизведены через API прежней головы команд: 0/12 совпадений
с новыми метками. Файл — `fixtures/v031-visible-fight-cases.json`.
Новый набор команд сохраняет прежние наблюдения и разбиение; изменено
139 обучающих и 35 проверочных меток. Добавлены 188/79 наблюдений
из завершённых `typed-key` и `retreat-key`: итог 3079/984.
Голова `laya-v031-command-visible-fight-v1` выбрана на эпохе 297 из 350:
977/984 на записанной проверке, 98,51% на синтетической. Через API также
977/984, 12/12 новых отвлечений и 80/80 прежних ошибок сбора ключей.
Игра `runs/20260928_044645_410619_v031-visible-fight-map03-seed54`
прервана на 510 с после пяти смертей: 155 убийств, 23 подбора,
ошибок API нет. Лимит 1200 с не исчерпан; MAP01 и MAP02 не запускались.
Манифест:
`d336ce59068e3ad2f5226e9a7189f1ec8a8541b1caa67e0cda23b83e5e31888e`.

### Числовая часть головы механизмов

Все 14 расхождений механизмов из успешного маршрута повторены через API:
0/14. Они сохранены в `fixtures/v031-teacher-switch-cases.json`.
К прежним данным добавлены 78/36 наблюдений, один повтор исключён.
Итого `training/v031-switch-teacher-v1` содержит 951/305 примеров.
Старые метки и разбиение сохранены; новые наблюдения разделены временными
блоками того же маршрута. Независимое обобщение не измеряется.

Для этой головы подготовлена дополнительная обучаемая числовая сеть.
Она видит расстояния, типы механизмов, ключи, фазы лифтов и выбранную цель;
ID механизмов в числовые признаки не входят. Текстовая Laya получает
прежний полный вход и остаётся замороженной. Новая сеть учится поправлять
её оценки. Исполнитель и набор доступных механизмов не меняются.
Четыре проверки признаков и нейронного выбора с Torch прошли.
Обучение завершено: лучшая эпоха 359 из 500, проверка выросла с 267/305
до 300/305. Реальный API повторил 300/305, в том числе все 36 новых
проверочных состояний успешного маршрута. На сохранённых ошибках — 13/14;
на прежних случаях механизмов у собранных ключей — 11/12. Два расхождения
из этих файлов остаются. Проверка совпадения кеша текстовых оценок
с обычным вызовом Laya дала максимальную разницу 0.

После экспорта исправлен унаследованный `best-epoch.json`; веса не менялись.
Запись исправления — `runs/v031-switch-export-metadata-fix.json`.
Точный исходник выполненного обучения сохранён внутри checkpoint в
`source/training/finetune_numeric_switch.py`; его SHA совпадает с config.
Текущий тренер сразу пишет правильную эпоху и сохраняет собственный исходник.

Общие тесты: 318, из них 18 пропущены в окружении без Torch; ошибок нет.
В окружении с Torch отдельно прошли 20 тестов числовых голов.

Запущена общая проверка `runs/20260928_050827_274602_v031-numeric-switch_suite`:
MAP03, затем MAP01 и MAP02, прежние бюджеты, одни веса.
Манифест:
`295779ae7de6169e234e0ad48c152df22170507b6dff1de5060733129308c65e`.
Этот прогон прерван на 548,229 с без смертей: 70 убийств, 15 подборов,
все три ключа собраны. После этого модель зациклилась между дальней
аптечкой и патронами. При 75 HP и 49 патронах дробовика офлайн-разметка
тоже выбирала припасы вместо маршрута к выходу. MAP01 и MAP02 не запускались.
Лимит MAP03 не исчерпан; прохождение не засчитано.

### Завершение уровня после сбора ключей

Новый офлайн-разметчик `training/route_finish.py` меняет только обычный
подбор далёких припасов: при всех ключах, HP не ниже 45 и заряженном
сильном оружии он ставит механизм выхода или выход выше предмета дальше
шести метров. Бой, близкие припасы, экстренное лечение и незавершённый
подъём на лифте сохраняют прежний приоритет. В игровой код эта функция
не импортируется.

Полный офлайн-проход с новой разметкой завершил MAP03 за 369,8 с
без смертей: `runs/v031-teacher-finish-route`. Это проверка разметчика,
не прохождение нейронной модели.

На прежних входах изменены 13 обучающих и три проверочные метки.
Из прерванного прогона добавлены 202/153 наблюдения; итоговый набор
`training/v031-command-finish-v1` — 3281/1137. Разбиение внутри того же
маршрута не измеряет перенос на другие карты.

`laya-v031-command-finish-v1` обучена 350 эпох с прежней замороженной
текстовой головой и 60 000 синтетических примеров. Лучшая эпоха — 350:
1125/1137 на записанной проверке, 98,25% на синтетической. Новые 16 случаев
цикла воспроизведены через API: до обучения 0/16, после 16/16.
Прежние проверки ключей — 80/80, боя — 12/12.
Общие тесты: 322, из них 18 пропущены в окружении без Torch; ошибок нет.

Для публикации новые диагностические скрипты добавлены в исключения
`.gitignore`. Обучающий файл занимает 13,2 MB, поэтому лимит одного
зарегистрированного набора данных увеличен с 12 до 16 MiB. Проверки SHA,
секретов, приватных путей и лимит 10 MiB для обычных исходников сохранены.


### Полный результат finish-route и сохранение прежних решений

`runs/20260928_052920_607044_v031-finish-route-map03-seed54` завершён
по лимиту 1200 с: семь смертей, 296 убийств, 51 подбор, выход не достигнут.
Ошибок API нет, запись и аудит управления корректны. HTTP p50 — 299,32 мс,
p90 — 357,21 мс, медиана применения — 457,143 мс. Манифест:
`3198bd0306f70279e3078836843fc9f41f0e5734085b7b9cf0cd07ff9f2411be`.
Первая смерть произошла на 197,686 с: повторное обучение изменило
поведение задолго до исправляемого финального участка.

Серия остановлена после проверки MAP03, когда MAP01 только начала
запускаться. Причина — запас диска около 1,3 GiB; MAP02 не запускалась.
Сжатие последних журналов и данных сохранило все SHA. Повторное объединение
блоков checkpoint почти не освободило места; все веса сохранили прежние SHA.
Старые видео сохранены без перекодирования.

Для новых записей кодировщик изменён с `ultrafast` на `veryfast`, два
потока, прежние CRF 24, 1920×1080 и 35 кадров/с. Проба на 30 секундах
старого видео дала 1050 кадров за 5,125 с и файл 16 177 670 байт.
Это проверка скорости кодирования; реальное время каждого нового игрового
прогона по-прежнему проверяется отдельно. Новые игровые кадры кодируются
один раз, исходные записи не меняются.

Начато точечное обучение только последнего слоя прежней числовой головы
команд. Для исправляемых финальных состояний используются новые метки,
для остальных — сохранение оценок прежней модели. Отдельное условие
выбора checkpoint требует сохранения всех решений до сбора трёх ключей
из прогона `numeric-switch`, где игрок не погиб. Это дистилляция прежней
модели и обучение на исправленных метках, не новая политика в исполнителе.
Игрового результата такого checkpoint пока нет.


Вариант с одним обучаемым выходным слоем не прошёл условие сохранения
прежних решений; checkpoint не экспортирован. При обучении последнего
блока (второй скрытый и выходной слои) выбран checkpoint эпохи 950 из 1200.
Энкодер, первый числовой слой, признаки и их пороги остались прежними.
Сеть во время игры использует прежний формат `laya-command-numeric-residual-v2`.
Новые правила в исполнитель не добавлены.

Через API `laya-v031-command-finish-retained-v1`:
543/543 прежних решений до сбора ключей, 16/16 случаев финального цикла,
80/80 случаев ключей и 12/12 случаев боя. Полный набор — 1126/1137.
Внутри него исправлены 151/154 финальных состояния, а 982/983 остальных
сохранили прежний выбор. На синтетической проверке — 2907/3000 совпадений
с метками, но только 13/50 состояний нового приоритета завершения.
Это ограничение сохраняется; перенос исправления на произвольные состояния
не доказан.

Общие тесты: 324, 18 пропущены без Torch, ошибок нет. Новая серия:
`runs/20260928_060838_770815_v031-finish-retained_suite`, порядок MAP03,
MAP01, MAP02, прежние бюджеты. Манифест:
`a6ecfb5a1860a8995c9a8b226f78f5f029a60541dac66b9201d2acc8740ed857`.
Игрового результата пока нет.


### Две успешные карты finish-retained и цикл MAP02

Серия `20260928_060838_770815_v031-finish-retained_suite` завершила MAP03
за 391,114 с и MAP01 за 165,657 с без смертей. Полные записи с тремя
секундами следующей карты — 394,143 с и 168,686 с. Аудит модели,
видео и реального времени пройден. Навигационные пороги превышены:
MAP03 — 30,06 с без новой области; MAP01 — 25,06 с без новой ячейки
и 36,2 с без новой области.

MAP02 прервана на 540,771 с без смертей: 52 убийства, 16 подборов,
синий и красный ключи. После 333 с модель возвращалась на лифт к синему
ключу каждые 19 с. Текстовая голова выбирала pickup, числовая меняла
решение на use_switch. В журнале 218 расхождений с меткой route_missing_key;
исполнитель выполнял выбранную команду. Лимит 1800 с не исчерпан.

В `training/v031-command-key-return-v1` добавлены 62/54 уникальных
наблюдения после 320 с с прежними метками route_missing_key/route_nearby_door.
Разметчик и игровой исполнитель не менялись. Новый селектор категорий
обучает только отмеченные исправления. Все решения завершённых MAP01
и MAP03 используются как обязательные примеры сохранения.

`laya-v031-command-key-retained-v1`: эпоха 65 из 1600, обучение 76,710 с.
CPU: 1179/1191, исправлены 53/54 новых проверочных случаев, сохранены
1137/1137 старых проверочных решений и 1096/1096 решений успешных карт.
API: 1096/1096 сохранены, исправлены 114/116 состояний цикла; два
расхождения остаются возле двери. Игрового результата пока нет.

Манифест нового API:
`74eea1043aa584bf825fe25ac40be5fc7affc555c63dea8712b9b807ae9cafb6`.
Числовые веса:
`072b09627912b03cc6783cb0ecb893c8a40db2ff8841b1d73666138a567e4d00`.

Из 324 тестов один потребовал обязательную фразу об отсутствии
независимой выборки в реестре данных; после уточнения все пять тестов
публикации прошли. Остальные тесты прошли в общем запуске, 18 пропущены
в окружении без Torch. Сжатие шести завершённых JSONL сохранило SHA и
освободило 259 MB; видео и веса сохранены.

## Проверка key-retained и причины расхождения на MAP03

Комплект `74eea1043aa584bf825fe25ac40be5fc7affc555c63dea8712b9b807ae9cafb6`
прошёл MAP02 за 372,057 с и MAP01 за 165,657 с без смертей. MAP02 прошла
также проверку навигации. MAP03 прервана на 705,686 с после шести смертей;
лимит 1200 с не исчерпан. Результаты сохранены в
`reports/v031-key-retained-regression.json`.

На всех 1374 записанных состояниях MAP03 старая и новая головы команд
выбрали одинаковое действие. Первое расхождение с прежним успешным
маршрутом появилось после получения жёлтого ключа: ответ на запрос
тика 6524 применён через 23 тика в успешном прогоне и через 24 в неуспешном.
HTTP занял соответственно 434,63 и 446,09 мс. Это показывает чувствительность
траектории к задержке, но само по себе не доказывает ошибку исполнения.

В офлайн-повторе боя 6677–7028 исходная ветка погибла, а исправленный
порядок целей сохранил 34 HP. Остальные кнопки оставлены из записи.
Контрольная пересчитанная ветка точно совпала с исходной. Опыт не является
прохождением модели: `runs/v031-key-retained-enemy-order-counterfactual.json`.

## Эксперимент с числовой головой противников

Добавлены признаки расстояния, направления, видимости, типа противника и
предыдущей цели; номера карты и координат нет. Энкодер и текстовая голова
заморожены. Обучены два скрытых слоя по 96 узлов, выход и вес текстовой
оценки. Все непустые последовательности целей сохранены в вариантах ответа.
В исполнитель и игровой API офлайн-разметчик не добавлен.

Данные `training/v031-enemy-numeric-v1`: 849 учебных и 82 проверочных
записи из разных прогонов, повторы входов исключены между выборками.
Дополнительно использованы 16 000/3000 синтетических примеров.
Из 250 эпох выбрана 42; обучение заняло 25,115 с.
CPU: 849/849 на обучении, 81/82 на проверке, 2975/3000 на синтетике.
Реальный API: 88/88 прежних ошибок первой цели, 16/16 случаев видимости,
81/82 первых целей и 78/82 полных порядков на отдельной записи.
Это данные тех же карт, на которых велась разработка.

Сборка `989c5e174ab01be4a3687fe1f9db9d20338165be18e984a9fdef1fdcc7e6479b`
прервана на MAP03 через 524,543 с: четыре смерти, 144 убийства, ошибок API
нет. Лимит 1200 с не исчерпан. Голова исключена из текущего кандидата;
веса, данные и отчёт `reports/v031-enemy-numeric-regression.json` сохранены.

## Событие появления противника и реальная задержка

Добавлен необязательный `--enemy-events`: новый видимый противник запускает
запрос, когда предыдущий завершён. Событие не выбирает действие, не меняет
ответ и не отменяет ожидание API. Тесты проверяют отсутствие изменения
состояния и сохранение настоящего времени ответа. Общие проверки: 332 теста,
20 пропущены без Torch, ошибок нет.

С прежними весами key-retained и задержкой 16 тиков опыт enemy-events
прерван на MAP03 через 405,086 с после трёх смертей. Результат:
`reports/v031-enemy-events-regression.json`. Улучшение не подтверждено.

Следующая серия `20260928_074537_900045_v031-native-rtt_suite` использует
те же веса без enemy-events и с `--minimum-decision-delay-ticks 0`.
Ответ применяется по получении, без добавленного ожидания до 16 тиков.
Реальный RTT, исходные seed, skill, бюджеты, скорость наведения и запись
сохранены. Режим одинаков для всех трёх карт. Прохождения пока не заявлены.

## Итог native-rtt: три карты одним комплектом

Серия `runs/20260928_074537_900045_v031-native-rtt_suite` завершилась
зачётом всех трёх карт. Веса на протяжении серии не менялись:
`74eea1043aa584bf825fe25ac40be5fc7affc555c63dea8712b9b807ae9cafb6`.

| Карта | Seed, skill | Выход | Смерти | RTT p50/p90 | Применение решения p50 |
|---|---|---:|---:|---:|---:|
| MAP01 | 48, 3 | 168,400 с | 0 | 266,01/288,46 мс | 285,714 мс |
| MAP02 | 54, 3 | 420,400 с | 0 | 295,81/337,32 мс | 328,572 мс |
| MAP03 | 54, 3 | 347,114 с | 0 | 309,47/367,67 мс | 342,857 мс |

Во всех случаях подтверждены живой выход и 105 тиков следующей карты.
Проверки управления, видео и реального времени прошли.
MAP02 и MAP03 прошли также пороги навигации. На MAP01 остаётся
32,23 с без новой области при пороге 25 с; общий quality passed=false
отделён от зачёта прохождения. Замечание не скрыто и порог не ослаблен.

Отчёт `reports/v031-regression.json` содержит SHA видео, телеметрии,
решений, конфигурации и снимков исходников. Сжатие логов между картами
сохранило их SHA и не пересекалось с игрой. Старые одинаковые диагностические
WAD заменены независимыми APFS-клонами с сохранением байтов и метаданных.
Видео и веса прежних опытов сохранены.

В обёртке регрессии закреплён проверенный режим 0 добавленных тиков по
умолчанию. Явный параметр 16 сохраняет возможность повторять старые опыты.
Фактические аргументы принятой серии уже содержали 0 на каждой карте.
Итоговые тесты: 332 в игровом Python, 20 пропущены без Torch; 36 проверок
в модельном Python прошли, в том числе все пропущенные проверки Torch.
Результат относится к одной итоговой серии после разработки на этих
картах; надёжность на других seed и при другом RTT не заявляется.
