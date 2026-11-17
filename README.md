# download-speed

Десять последовательных полных загрузок по HTTP/HTTPS: среднее время запроса, общий объём и скорость. Python **3.11+**, без внешних зависимостей при работе.

## Запуск

```bash
pipx install git+https://github.com/Syrenny/etolegko-test.git
download-speed https://example.com/large-file
```

Если установлен uv, можно запустить через `uvx` без отдельной установки команды (окружение сохраняется в кеше uv):

```bash
uvx --from git+https://github.com/Syrenny/etolegko-test.git download-speed https://example.com/large-file
```

Из клонированного репозитория: `pipx install .`. Без установки: `python download_speed.py URL`.
Параметры: `--timeout SECONDS` (по умолчанию 30 секунд на сетевую операцию), `--help`, `--version`.

```text
Requests:              10/10
Total downloaded:      10.00 MiB (10485760 bytes)
Average request time:  0.100 s
Download speed:        83.89 Mbps
```

Скорость в **Mbps (Мбит/с)** = суммарные байты × 8 / суммарные секунды / 1 000 000. Объём — в MiB (1 048 576 байтов) и байтах. Значения выше — пример.

Результат зависит от сервера и включает подключение и ожидание ответа; это не полноценный тест интернет-канала. Ресурс скачивается десять раз, содержимое не сохраняется. При ошибке программа останавливается без повторов; Ctrl+C и SIGTERM завершают её без traceback.

## Разработка

```bash
uv sync --locked
uv run --locked pytest -q
```

uv управляет Python 3.11 и окружением; pytest и pytest-httpserver нужны только для тестов. Проверки используют локальный HTTP-сервер.

Решение подготовлено с помощью ИИ. [ExecPlan](.agent/execplans/download-speed.md) использован для согласования поведения и фиксации решений; sbx-песочница — для изолированного окружения разработки и проверок.
