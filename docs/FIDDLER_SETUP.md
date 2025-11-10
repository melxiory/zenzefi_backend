# Fiddler: Перехват API запросов DTS Monaco к Zenzefi

## Описание

Этот документ описывает процесс перехвата и анализа API запросов от DTS Monaco клиента к Zenzefi серверу с помощью Fiddler для определения точных endpoint'ов, необходимых для работы с сертификатами.

## Требования

- Windows 10/11
- Права администратора
- DTS Monaco клиент
- 30-60 минут для перехвата

## Установка Fiddler

### Способ 1: winget (рекомендуется)

```bash
winget install Telerik.Fiddler.Classic
```

### Способ 2: Ручная установка

1. Скачать Fiddler Classic: https://www.telerik.com/fiddler/fiddler-classic
2. Запустить установщик
3. Следовать инструкциям установки

## Настройка Fiddler

### Шаг 1: Включить HTTPS декодирование

1. Запустить Fiddler
2. **Tools → Options → HTTPS**
3. ✅ Включить "Decrypt HTTPS traffic"
4. ✅ Выбрать "...from all processes"
5. Нажать **Actions → Trust Root Certificate**
6. Подтвердить установку сертификата (требуется админ)
7. Нажать **OK**

### Шаг 2: Настроить фильтры

1. **Filters tab** (правая панель)
2. ✅ "Use Filters"
3. **Hosts section:**
   - Show only the following Hosts: `zenzefi`
4. **Request Headers:**
   - Show only if URL contains: `/certificates`
5. Нажать **Actions → Run Filterset now**

### Шаг 3: Настроить колонки отображения

1. Правый клик на заголовках колонок
2. Включить:
   - ✅ Protocol
   - ✅ Host
   - ✅ URL
   - ✅ Body
   - ✅ Result
   - ✅ Method

## Перехват запросов

### Подготовка к перехвату

1. **Очистить сессию:**
   - Edit → Remove → All Sessions (Ctrl+X)

2. **Включить перехват:**
   - File → Capture Traffic (F12)
   - Индикатор должен показывать "Capturing"

3. **Запустить DTS Monaco**

### Сценарии тестирования

Выполните следующие операции в DTS Monaco для перехвата всех certificate endpoints:

#### 1. Просмотр сертификатов

- [ ] Открыть список всех сертификатов
- [ ] Применить фильтры (по дате, статусу)
- [ ] Отсортировать список

**Ожидаемые endpoints:**
- `GET /certificates/filter`
- `GET /certificates/activeForTesting`

#### 2. Детали сертификата

- [ ] Открыть детали одного сертификата
- [ ] Просмотреть свойства
- [ ] Проверить дату истечения

**Ожидаемые endpoints:**
- `GET /certificates/details/{id}`
- `GET /certificates/activeForTesting/options/{id}`

#### 3. Экспорт сертификата

- [ ] Экспортировать сертификат в файл
- [ ] Выбрать формат экспорта

**Ожидаемые endpoints:**
- `GET /certificates/export/{id}`
- `POST /certificates/export/{id}`

#### 4. Импорт сертификата

- [ ] Импортировать сертификат из файла
- [ ] Подтвердить импорт

**Ожидаемые endpoints:**
- `POST /certificates/import/files`

#### 5. Управление сертификатами

- [ ] Активировать сертификат для тестирования
- [ ] Деактивировать сертификат
- [ ] Удалить сертификат (если возможно)
- [ ] Восстановить сертификат (если возможно)

**Ожидаемые endpoints:**
- `POST /certificates/activeForTesting/activate/{id}`
- `POST /certificates/activeForTesting/deactivate/{id}`
- `DELETE /certificates/remove`
- `POST /certificates/restore`

#### 6. Обновление сертификата

- [ ] Инициировать обновление сертификата
- [ ] Проверить статус обновления
- [ ] Отменить обновление (если возможно)

**Ожидаемые endpoints:**
- `POST /certificates/update/{id}`
- `GET /certificates/update/metrics`
- `POST /certificates/update/cancel`

#### 7. Проверка целостности

- [ ] Запустить проверку целостности системы
- [ ] Просмотреть отчет
- [ ] Проверить лог

**Ожидаемые endpoints:**
- `GET /certificates/checkSystemIntegrityReport`
- `GET /certificates/checkSystemIntegrityLog`
- `GET /certificates/checkSystemIntegrityLogExistance`

#### 8. Конфигурация UI (опционально)

- [ ] Изменить порядок столбцов
- [ ] Скрыть/показать столбцы

**Ожидаемые endpoints:**
- `GET /configurations/certificatesColumnOrder`
- `POST /configurations/certificatesColumnOrder`
- `GET /configurations/certificatesColumnVisibility`

## Анализ результатов

### Экспорт перехваченных запросов

**Вариант 1: SAZ файл (для будущего анализа)**

1. File → Save → All Sessions
2. Сохранить как `dts_monaco_capture.saz`

**Вариант 2: Текстовый формат**

1. Выбрать все сессии (Ctrl+A)
2. File → Export Sessions → Selected Sessions → in HTTPArchive v1.2 format
3. Сохранить как `dts_monaco_capture.har`

**Вариант 3: CSV список**

1. Выбрать все сессии
2. File → Export Sessions → Selected Sessions → CSV
3. Открыть в Excel/Google Sheets

### Извлечение уникальных endpoint'ов

**В Fiddler:**

1. QuickExec box (внизу): `select *`
2. Просмотреть URL column
3. Вручную записать уникальные пути

**Из HAR файла (PowerShell):**

```powershell
# Извлечь все URL из HAR файла
$har = Get-Content dts_monaco_capture.har | ConvertFrom-Json
$urls = $har.log.entries | ForEach-Object { $_.request.url }

# Извлечь пути (без домена)
$paths = $urls | ForEach-Object {
    $uri = [System.Uri]$_
    $uri.AbsolutePath
} | Sort-Object -Unique

# Фильтровать только /certificates
$certPaths = $paths | Where-Object { $_ -like "*/certificates*" }
$certPaths | Out-File -FilePath "certificate_endpoints.txt"
```

**Из HAR файла (Python):**

```python
import json
from urllib.parse import urlparse

with open('dts_monaco_capture.har', 'r') as f:
    har = json.load(f)

# Извлечь уникальные пути
paths = set()
for entry in har['log']['entries']:
    url = entry['request']['url']
    parsed = urlparse(url)
    path = parsed.path
    if '/certificates' in path:
        paths.add(path)

# Сохранить в файл
with open('certificate_endpoints.txt', 'w') as f:
    for path in sorted(paths):
        f.write(path + '\n')
```

### Создание regex patterns

На основе собранных endpoint'ов создать regex patterns для `app/core/permissions.py`:

**Пример конвертации:**

```
Endpoint: /certificates/details/123
Regex:    ^certificates/details/

Endpoint: /certificates/activeForTesting/activate/456
Regex:    ^certificates/activeForTesting/activate/

Endpoint: /certificates/filter?status=active
Regex:    ^certificates/filter
```

## Шаблон отчета

После завершения перехвата заполните:

```markdown
# Отчет о перехваченных API запросах DTS Monaco

**Дата:** 2025-01-10
**Длительность перехвата:** 45 минут
**Количество запросов:** 127
**Уникальных endpoint'ов:** 18

## Найденные Certificate Endpoints

### Чтение данных (GET)
- [ ] `/certificates/filter`
- [ ] `/certificates/details/{id}`
- [ ] `/certificates/export/{id}`
- [ ] `/certificates/activeForTesting`
- [ ] `/certificates/activeForTesting/enhanced`
- [ ] `/certificates/activeForTesting/options/{id}`
- [ ] `/certificates/activeForTesting/usecases/{id}`
- [ ] `/certificates/checkSystemIntegrityReport`
- [ ] `/certificates/checkSystemIntegrityLog`
- [ ] `/certificates/checkSystemIntegrityLogExistance`
- [ ] `/certificates/update/metrics`

### Изменение данных (POST/PUT/DELETE)
- [ ] `POST /certificates/import/files`
- [ ] `POST /certificates/activeForTesting/activate/{id}`
- [ ] `POST /certificates/activeForTesting/deactivate/{id}`
- [ ] `DELETE /certificates/remove`
- [ ] `POST /certificates/restore`
- [ ] `POST /certificates/update/{id}`
- [ ] `POST /certificates/update/cancel`

### Дополнительные (если обнаружены)
- [ ] Другие endpoint'ы...

## Рекомендации для SCOPE_PERMISSIONS

```python
SCOPE_PERMISSIONS = {
    "certificates_only": [
        r"^certificates/filter",
        r"^certificates/details/",
        r"^certificates/export/",
        # ... добавить остальные из списка
    ]
}
```
```

## Troubleshooting

### Проблема: HTTPS трафик не декодируется

**Решение:**

1. Tools → Options → HTTPS → Actions → Reset All Certificates
2. Перезапустить Fiddler
3. Повторно Trust Root Certificate

### Проблема: Не видно трафика DTS Monaco

**Решение:**

1. Проверить что Fiddler Capturing включен (F12)
2. Убрать фильтры: Filters → Use Filters (OFF)
3. Проверить что DTS Monaco использует системный proxy

### Проблема: Сертификат не устанавливается

**Решение:**

1. Запустить Fiddler от имени администратора
2. certmgr.msc → Доверенные корневые центры → Импорт → DO_NOT_TRUST_FiddlerRoot.cer

## Альтернативные методы

Если Fiddler не подходит, см.:
- **mitmproxy** - command-line proxy
- **Charles Proxy** - GUI proxy (платный)
- **Backend logging** - добавить middleware в Backend

См. документацию проекта для других методов.

## Следующие шаги

После завершения перехвата:

1. Создать отчет (шаблон выше)
2. Обновить `docs/DTS_MONACO_SCOPE_PLAN.md` с реальными endpoint'ами
3. Обновить `app/core/permissions.py` с regex patterns
4. Запустить тесты с real endpoints

## Полезные ресурсы

- Fiddler Documentation: https://docs.telerik.com/fiddler
- HAR Spec: http://www.softwareishard.com/blog/har-12-spec/
- Zenzefi Backend docs: `../CLAUDE.md`
