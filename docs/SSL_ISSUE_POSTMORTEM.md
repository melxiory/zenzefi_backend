# SSL Issue Postmortem

## Проблема

После деплоя HTTPS не работал - работал только HTTP на порту 80.

## Дата инцидента

4 ноября 2025

## Анализ причины

### Основная ошибка

В `docker-compose.prod.tailscale.yml` для сервиса `certbot` был неправильно настроен **entrypoint**:

```yaml
# ❌ НЕПРАВИЛЬНО (старая версия)
certbot:
  image: certbot/certbot
  entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
```

### Почему это вызвало проблему?

1. **Entrypoint переопределяет команды**
   - `entrypoint` - это точка входа контейнера, которая **всегда выполняется**
   - Когда мы запускали `docker compose run certbot certonly ...`, команда `certonly` **игнорировалась**
   - Вместо этого всегда выполнялась команда из entrypoint: `certbot renew`

2. **Certbot renew не работает без существующих сертификатов**
   - Команда `certbot renew` предназначена для **обновления существующих** сертификатов
   - Если сертификатов нет, она просто говорит "No renewals were attempted" и завершается
   - Для **получения нового** сертификата нужна команда `certbot certonly`

3. **Цепочка ошибок**
   ```
   Деплой → certbot не получил сертификат →
   HTTPS конфигурация не включилась →
   Nginx работает только с HTTP →
   HTTPS не работает
   ```

### Временное решение (использованное вручную)

Мы обошли проблему, используя флаг `--entrypoint`:

```bash
docker compose run --rm --entrypoint certbot certbot certonly ...
```

Это **переопределило** встроенный entrypoint и позволило выполнить `certonly`.

## Правильное решение

### 1. Изменить entrypoint на command

```yaml
# ✅ ПРАВИЛЬНО (новая версия)
certbot:
  image: certbot/certbot
  # Use command instead of entrypoint to allow 'docker compose run' to override
  command: /bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'
```

**Почему это работает:**
- `command` - это аргументы, передаваемые в entrypoint
- `docker compose run certbot certonly ...` **переопределяет** command
- Теперь скрипты могут нормально запускать `certonly` для получения нового сертификата

### 2. Улучшенная конфигурация Nginx

Исправлена устаревшая директива `listen 443 ssl http2`:

```nginx
# ❌ Устаревший синтаксис
listen 443 ssl http2;

# ✅ Современный синтаксис (Nginx 1.25.1+)
listen 443 ssl;
http2 on;
```

## Что было сделано

### 1. Инструменты диагностики

Созданы инструменты для автоматической диагностики и исправления:

- **scripts/fix_ssl.sh** - Автоматический скрипт диагностики и исправления
  - Проверяет статус контейнеров
  - Определяет активную конфигурацию
  - Проверяет наличие SSL-сертификата
  - Автоматически переключает конфигурацию
  - Получает новый сертификат при необходимости

- **HTTPS_TROUBLESHOOTING.md** - Руководство по устранению проблем
  - Пошаговая ручная диагностика
  - Решения для 5 типовых проблем
  - Полезные команды для отладки

### 2. Улучшен deploy_docker.sh

- Добавлена проверка DNS перед получением сертификата
- Попытка webroot метода (не требует остановки Nginx)
- Fallback на standalone метод
- Вывод информации о сертификате
- Ссылки на инструменты исправления

### 3. Исправлен docker-compose.prod.tailscale.yml

- Заменён `entrypoint` на `command` в certbot сервисе
- Теперь `docker compose run` правильно работает

### 4. Обновлена Nginx конфигурация

- Устранено предупреждение о deprecated директиве `http2`

## Проверка исправления

После применения исправлений:

```bash
# Проверка получения сертификата (должно работать без --entrypoint)
docker compose -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@example.com \
    --agree-tos \
    --no-eff-email \
    -d your-domain.com

# Проверка Nginx конфигурации (не должно быть warnings)
docker exec zenzefi-nginx nginx -t

# Проверка HTTPS
curl -I https://your-domain.com/health
```

## Уроки на будущее

1. **Различие между entrypoint и command**
   - `entrypoint` - постоянная точка входа (трудно переопределить)
   - `command` - аргументы (легко переопределить через `docker compose run`)
   - Для сервисов, которые должны поддерживать разные команды, используйте `command`

2. **Тестирование деплоя**
   - Всегда тестировать полный цикл деплоя на staging окружении
   - Проверять работу `docker compose run` для сервисов
   - Тестировать получение SSL-сертификата в процессе деплоя

3. **Документация**
   - Создавать подробные troubleshooting руководства
   - Автоматизировать диагностику частых проблем
   - Документировать известные ограничения и workarounds

4. **Мониторинг**
   - Настроить алерты на истечение SSL-сертификатов
   - Мониторить доступность HTTPS endpoint
   - Проверять логи certbot на ошибки

## Связанные коммиты

1. `fadcaee` - feat(deploy): add automated SSL/HTTPS troubleshooting tools
2. `[следующий]` - fix(deploy): fix certbot entrypoint preventing SSL certificate generation

## Статус

✅ **Исправлено** - 4 ноября 2025

HTTPS полностью работает:
- Сертификат получен и валиден до 2 февраля 2026
- HTTP редиректит на HTTPS
- Security headers настроены
- Автообновление сертификата работает

## Контакты

Если возникнут вопросы по этому инциденту:
- Документация: `HTTPS_TROUBLESHOOTING.md`
- Автоматическое исправление: `scripts/fix_ssl.sh`
