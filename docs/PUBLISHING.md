# Публикация кода, весов и видео

[English](PUBLISHING.en.md) · Русский

Рекомендуемая схема: **GitHub — код, данные обучения и отчёт;
Hugging Face — модель; GitHub Releases — видео и при желании архив весов.**
Скрипты подготовки создают локальные файлы. Загрузка на сервисы описана отдельно
в шагах 3 и 4.

Адреса проекта: [код](https://github.com/azalio/doomLaya), [модель](https://huggingface.co/azalio/laya-doom-v3),
[релиз v0.1.0](https://github.com/azalio/doomLaya/releases/tag/v0.1.0). Чтобы скачать готовые веса, перейдите к шагу 5.

## Комплект v0.3.0 для MAP03

[Модель MAP03](https://huggingface.co/azalio/laya-doom-map03/tree/v0.3.0)
содержит восемь checkpoint из успешного прогона. Подготовка проверяет каждый
файл весов по [манифесту](../reports/map03-model.json):

```bash
.venv/bin/python scripts/package_question_heads.py \
  --routing reports/map03-model.json --card model-card/MAP03.md \
  --output dist/laya-doom-map03
.venv/bin/hf upload azalio/laya-doom-map03 dist/laya-doom-map03 .
```

Для упаковки нужно около 12,6 GiB свободного места. На macOS/APFS можно
добавить `--clone-weights`: копии независимы, но используют общие дисковые
блоки до изменения файла. Их SHA-256 проверяется так же.
Видео и архив телеметрии опубликованы в [релизе v0.3.0](https://github.com/azalio/doomLaya/releases/tag/v0.3.0).
Запуск — в [MAP03.md](MAP03.md), карточка — [model-card/MAP03.md](../model-card/MAP03.md).

## Комплект v0.2.0 для MAP01 и MAP02

[Новый комплект](https://huggingface.co/azalio/laya-doom-map02) содержит пять
checkpoint из успешных прогонов. Он публикуется отдельно от прежней v3.
Подготовка проверяет каждый файл весов по [манифесту](../reports/map02-model.json):

```bash
.venv/bin/python scripts/package_question_heads.py
.venv/bin/hf upload azalio/laya-doom-map02 dist/laya-doom-map02 .
```

Карточка — [model-card/MAP02.md](../model-card/MAP02.md). Упаковщик переносит
только обязательные файлы, очищает локальные пути в метаданных и создаёт
`SHA256SUMS`. Полный комплект занимает около 8 GiB и хранится на Hugging Face.
В GitHub Release v0.2.0 размещены видео, архивы записей и контрольные суммы.
Скачивание и запуск описаны в [MAP02.md](MAP02.md).

Разделы ниже описывают прежнюю v3 и релиз v0.1.0.

## Где хранить веса

Текущий `model.safetensors` — около 1,6 GiB, полный каталог примерно того же
размера. GitHub блокирует файлы больше 100 MiB при загрузке через обычный Git.
[Лимиты GitHub](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).

| Вариант | Подходит | Особенности |
|---|---|---|
| Hugging Face model repository | Рекомендуется | Карточка модели, ревизии, загрузка через `hf download` |
| GitHub Release asset | Да | Архив скачивается отдельно, исходный Git остаётся небольшим |
| GitHub LFS | Да | Нужен LFS-клиент; хранение и скачивания зависят от квот плана |
| Обычный Git commit | Нет | Веса превышают 100 MiB |

На момент проверки GitHub связывает лимит одного файла релиза с лимитом LFS
для выбранного плана: у Free/Pro — 2 GB. Текущий архив помещается.
[Release assets](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github#distributing-large-binaries),
[LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage).
Hugging Face предоставляет публичное хранилище по принципу best effort,
без гарантированного объёма для бесплатного аккаунта;
[актуальные правила хранения](https://huggingface.co/docs/hub/storage-limits).

## 1. Проверить исходники

```bash
.venv/bin/python -m unittest tests.test_authority tests.test_publication
.venv/bin/python scripts/check_publication.py
git diff --cached --stat
```

Скрипт проверяет файлы, которые попадут в Git: ищет секреты, личные абсолютные пути,
ссылки на отсутствующие локальные документы и крупные файлы. Он печатает только
имена проблемных файлов, без значений секретов.

В Git входят код, CI, документация, замороженные обучающие JSON, фикстура,
карточка модели и небольшие проверочные отчёты. `.env`, окружения, `runs/`,
`checkpoints/`, `dist/`, WAD, видео, старые черновики и оригинальные сторонние
материалы исключены. Локальные файлы сохранены на диске.

## 2. Подготовить модель

```bash
.venv/bin/python scripts/package_model.py --archive
(cd dist/laya-doom-v3 && shasum -a 256 -c SHA256SUMS)
(cd dist && shasum -a 256 -c laya-doom-v3.tar.sha256)
```

Скрипт копирует только нужные файлы, добавляет карточку модели, Apache-2.0 и NOTICE,
удаляет локальные пути из метаданных и создаёт `SHA256SUMS`.
Исходная модель не меняется. Выходная папка должна отсутствовать;
для повторной сборки используйте другое значение `--output`.

Получаются `dist/laya-doom-v3/`, `dist/laya-doom-v3.tar` и checksum архива.
Веса в обоих вариантах идентичны:
`bb9083189517c5dc5c0e357062446df2ea73eadc3d909ec6ec7a6cee222a6147`.

## 3. Опубликовать код и модель

Команды ниже публикуют файлы на GitHub и Hugging Face. Замените имена аккаунтов
на свои. Команды создания репозитория нужны только для новой публикации;
для существующего репозитория достаточно загрузить изменения.

GitHub через установленный `gh`:

```bash
git add .
git commit -m "Prepare reproducible Doom model comparison"
gh repo create azalio/doomLaya --public --source=. --remote=origin --push
```

Если репозиторий уже существует, вместо `gh repo create` добавьте его адрес как remote
и выполните обычный `git push -u origin main`.

Hugging Face через CLI из `requirements-model.txt`:

```bash
.venv/bin/hf auth login
HF_MODEL=azalio/laya-doom-v3
.venv/bin/hf repo create "$HF_MODEL" --repo-type model
.venv/bin/hf upload "$HF_MODEL" dist/laya-doom-v3 .
```

Вводите ключ HF интерактивно или передавайте через `HF_TOKEN`;
в исходниках его быть не должно. После загрузки добавьте в README URL модели
и хеш коммита, который определяет её версию.
Код и модель этого проекта размещаются в аккаунте `azalio`.

## 4. Добавить видео и архив в GitHub Release

```bash
gh release create v0.1.0 \
  --title "Doom model-owned decisions: Laya v3 and Jev" \
  --notes-file RELEASE_NOTES.md \
  dist/laya-doom-v3.tar dist/laya-doom-v3.tar.sha256 \
  runs/20260922_000150_decision-model-comparison/laya-vs-jev.mp4 \
  runs/20260922_000150_decision-model-comparison/original-laya-vs-jev.mp4
```

Если веса размещены только на Hugging Face, уберите два `dist/` аргумента.
Видео существуют в исходной рабочей папке автора; в свежем clone их нет.
Сверить SHA-256 можно по [reports/video-verification.json](../reports/video-verification.json).
После публикации добавьте ссылки на файлы релиза в README и COMPARISON.

## 5. Скачать опубликованные веса на другой машине

Для скачивания v3 с Hugging Face выполните команду из корня doomLaya;
в ней закреплён хеш опубликованной версии:

```bash
HF_MODEL=azalio/laya-doom-v3
HF_REVISION=d27276e3bf8275cdbc9a7a72d80cad656aa87bd7
.venv/bin/hf download "$HF_MODEL" --revision "$HF_REVISION" \
  --local-dir checkpoints/laya-doom-v3
(cd checkpoints/laya-doom-v3 && shasum -a 256 -c SHA256SUMS)
```

Либо GitHub Release:

```bash
mkdir -p dist checkpoints
gh release download v0.1.0 --repo azalio/doomLaya \
  --pattern 'laya-doom-v3.tar*' --dir dist
(cd dist && shasum -a 256 -c laya-doom-v3.tar.sha256)
tar -xf dist/laya-doom-v3.tar -C checkpoints
```

Затем запускайте сервер по [README](../README.md). Чтобы обучить собственную модель,
используйте [TRAINING.md](TRAINING.md).
