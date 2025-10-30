# Zenzefi Backend - Quick Start & Cheat Sheet

Краткая справка по командам для администрирования Zenzefi Backend.

---

## Быстрая установка (Automated)

```bash
# Скачать скрипт
wget https://raw.githubusercontent.com/yourusername/zenzefi_backend/main/scripts/deploy.sh

# Сделать исполняемым
chmod +x deploy.sh

# Запустить (требуется root)
sudo ./deploy.sh
```

Скрипт автоматически установит все зависимости и настроит сервер.

---

## Управление сервисом

```bash
# Статус
sudo systemctl status zenzefi-backend

# Запуск
sudo systemctl start zenzefi-backend

# Остановка
sudo systemctl stop zenzefi-backend

# Перезапуск
sudo systemctl restart zenzefi-backend

# Перезагрузка конфигурации
sudo systemctl reload zenzefi-backend

# Включить автозапуск
sudo systemctl enable zenzefi-backend

# Отключить автозапуск
sudo systemctl disable zenzefi-backend
```

---

## Логи

```bash
# Смотреть логи в реальном времени
sudo journalctl -u zenzefi-backend -f

# Последние 100 строк
sudo journalctl -u zenzefi-backend -n 100

# Логи за последний час
sudo journalctl -u zenzefi-backend --since "1 hour ago"

# Логи за сегодня
sudo journalctl -u zenzefi-backend --since today

# Логи с фильтром по ошибкам
sudo journalctl -u zenzefi-backend -p err

# Nginx логи
sudo tail -f /var/log/nginx/zenzefi-backend-access.log
sudo tail -f /var/log/nginx/zenzefi-backend-error.log

# Очистка старых логов (старше 7 дней)
sudo journalctl --vacuum-time=7d
```

---

## База данных (PostgreSQL)

```bash
# Подключиться к базе
sudo -u postgres psql zenzefi_prod

# Или с пользователем zenzefi_user
psql -h localhost -U zenzefi_user -d zenzefi_prod

# В psql консоли:
\dt                              # Показать таблицы
\d users                         # Описание таблицы users
SELECT COUNT(*) FROM users;      # Количество пользователей
SELECT COUNT(*) FROM access_tokens;  # Количество токенов

# Размер базы данных
SELECT pg_size_pretty(pg_database_size('zenzefi_prod'));

# Backup базы (как zenzefi пользователь)
pg_dump -U zenzefi_user -h localhost zenzefi_prod | gzip > backup_$(date +%Y%m%d).sql.gz

# Восстановление из backup
gunzip < backup_20240127.sql.gz | psql -h localhost -U zenzefi_user -d zenzefi_prod
```

---

## Redis

```bash
# Подключиться к Redis
redis-cli

# Если установлен пароль
redis-cli -a your_redis_password

# В redis-cli:
AUTH your_password    # Авторизация (если нужна)
PING                  # Проверка подключения
INFO                  # Информация о Redis
DBSIZE                # Количество ключей
KEYS active_token:*   # Показать все токены
FLUSHALL              # Очистить весь кеш (ОСТОРОЖНО!)
FLUSHDB               # Очистить текущую БД (ОСТОРОЖНО!)

# Мониторинг команд в реальном времени
redis-cli MONITOR

# Статистика памяти
redis-cli INFO memory
```

---

## Миграции Alembic

```bash
# Перейти в директорию приложения
cd /home/zenzefi/apps/zenzefi_backend

# Активировать виртуальное окружение
source .venv/bin/activate

# Текущая версия базы
poetry run alembic current

# История миграций
poetry run alembic history

# Применить все миграции
poetry run alembic upgrade head

# Откатить последнюю миграцию
poetry run alembic downgrade -1

# Создать новую миграцию (autogenerate)
poetry run alembic revision --autogenerate -m "Description"

# Применить конкретную миграцию
poetry run alembic upgrade <revision_id>
```

---

## Nginx

```bash
# Проверить конфигурацию
sudo nginx -t

# Перезагрузить конфигурацию (без downtime)
sudo systemctl reload nginx

# Перезапустить Nginx
sudo systemctl restart nginx

# Статус
sudo systemctl status nginx

# Редактировать конфигурацию
sudo nano /etc/nginx/sites-available/zenzefi-backend
```

---

## SSL/TLS (Let's Encrypt)

```bash
# Проверить статус сертификатов
sudo certbot certificates

# Обновить сертификаты (тестовый режим)
sudo certbot renew --dry-run

# Принудительное обновление
sudo certbot renew --force-renewal

# Список всех сертификатов
sudo certbot certificates

# Отозвать сертификат
sudo certbot revoke --cert-path /etc/letsencrypt/live/api.yourdomain.com/cert.pem

# Удалить сертификат
sudo certbot delete --cert-name api.yourdomain.com
```

---

## Обновление приложения

```bash
# 1. Переключиться на zenzefi пользователя
sudo su - zenzefi

# 2. Перейти в директорию приложения
cd ~/apps/zenzefi_backend

# 3. Создать backup ветку (на всякий случай)
git branch backup-$(date +%Y%m%d-%H%M%S)

# 4. Получить обновления
git fetch origin
git pull origin main

# 5. Обновить зависимости (если изменились)
poetry install --no-dev --no-root

# 6. Применить миграции
poetry run alembic upgrade head

# 7. Вернуться к root
exit

# 8. Перезапустить сервис
sudo systemctl restart zenzefi-backend

# 9. Проверить логи
sudo journalctl -u zenzefi-backend -f
```

---

## Откат обновления

```bash
sudo su - zenzefi
cd ~/apps/zenzefi_backend

# Посмотреть backup ветки
git branch | grep backup

# Откатиться на backup
git checkout backup-20240127-120000

# Откатить миграции (если нужно)
poetry run alembic downgrade -1

exit
sudo systemctl restart zenzefi-backend
```

---

## Мониторинг системы

```bash
# Использование CPU и памяти
htop  # или top

# Процессы Python
ps aux | grep python

# Процессы uvicorn
ps aux | grep uvicorn

# Открытые порты
sudo ss -tlnp

# Проверить порт 8000 (backend)
sudo ss -tlnp | grep 8000

# Дисковое пространство
df -h

# Использование памяти
free -h

# Нагрузка системы
uptime

# Сетевая статистика
sudo netstat -s
```

---

## API тестирование

```bash
# Health check
curl https://api.yourdomain.com/health

# API Documentation (в браузере)
https://api.yourdomain.com/docs

# Register new user
curl -X POST https://api.yourdomain.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "testpass123",
    "full_name": "Test User"
  }'

# Login
curl -X POST https://api.yourdomain.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpass123"
  }'

# Get current user (с токеном)
curl https://api.yourdomain.com/api/v1/users/me \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE"

# Purchase token
curl -X POST https://api.yourdomain.com/api/v1/tokens/purchase \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"duration_hours": 24}'
```

---

## Редактирование конфигурации

```bash
# Редактировать .env
sudo nano /home/zenzefi/apps/zenzefi_backend/.env

# После изменения .env - перезапустить backend
sudo systemctl restart zenzefi-backend

# Редактировать systemd service
sudo nano /etc/systemd/system/zenzefi-backend.service

# После изменения service файла
sudo systemctl daemon-reload
sudo systemctl restart zenzefi-backend

# Редактировать Nginx конфигурацию
sudo nano /etc/nginx/sites-available/zenzefi-backend

# После изменения Nginx
sudo nginx -t && sudo systemctl reload nginx
```

---

## Backup и восстановление

```bash
# Ручной backup базы данных
sudo -u zenzefi bash -c "PGPASSWORD=your_db_password pg_dump -U zenzefi_user -h localhost zenzefi_prod | gzip > /home/zenzefi/backups/manual_backup_$(date +%Y%m%d_%H%M%S).sql.gz"

# Список backup файлов
ls -lh /home/zenzefi/backups/

# Восстановление из backup
gunzip < /home/zenzefi/backups/zenzefi_prod_20240127_030000.sql.gz | sudo -u postgres psql zenzefi_prod

# Запустить backup скрипт вручную
sudo -u zenzefi /home/zenzefi/backup_db.sh

# Проверить cron задачи
sudo -u zenzefi crontab -l

# Редактировать cron
sudo -u zenzefi crontab -e
```

---

## Troubleshooting

### Backend не запускается

```bash
# 1. Проверить логи
sudo journalctl -u zenzefi-backend -n 50 --no-pager

# 2. Проверить конфигурацию .env
cat /home/zenzefi/apps/zenzefi_backend/.env

# 3. Проверить права доступа
ls -la /home/zenzefi/apps/zenzefi_backend/.env

# 4. Проверить порт 8000
sudo ss -tlnp | grep 8000

# 5. Проверить подключение к PostgreSQL
psql -h localhost -U zenzefi_user -d zenzefi_prod -c "SELECT 1;"

# 6. Проверить подключение к Redis
redis-cli -a your_redis_password PING

# 7. Запустить backend вручную (для отладки)
sudo su - zenzefi
cd ~/apps/zenzefi_backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 502 Bad Gateway

```bash
# 1. Проверить backend
sudo systemctl status zenzefi-backend

# 2. Проверить Nginx upstream
sudo nginx -t

# 3. Проверить логи Nginx
sudo tail -50 /var/log/nginx/zenzefi-backend-error.log

# 4. Перезапустить оба сервиса
sudo systemctl restart zenzefi-backend nginx
```

### Высокая нагрузка

```bash
# 1. Проверить количество workers
sudo systemctl cat zenzefi-backend | grep workers

# 2. Увеличить количество workers
sudo nano /etc/systemd/system/zenzefi-backend.service
# Изменить: --workers 4  на  --workers 8

# 3. Применить изменения
sudo systemctl daemon-reload
sudo systemctl restart zenzefi-backend

# 4. Мониторинг в реальном времени
htop
```

### Проблемы с SSL

```bash
# 1. Проверить срок действия
sudo certbot certificates

# 2. Тест обновления
sudo certbot renew --dry-run

# 3. Принудительное обновление
sudo certbot renew --force-renewal

# 4. Проверить конфигурацию Nginx
sudo nginx -t

# 5. Перезапустить Nginx
sudo systemctl restart nginx
```

---

## Безопасность

```bash
# Проверить открытые порты
sudo ss -tlnp

# Проверить файрвол
sudo ufw status

# Просмотр попыток входа
sudo lastb

# Просмотр успешных входов
sudo last

# Проверить fail2ban (если установлен)
sudo fail2ban-client status

# Обновление системы
sudo apt update && sudo apt upgrade -y

# Автоматические обновления безопасности
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

---

## Полезные команды

```bash
# Быстрый перезапуск всего
sudo systemctl restart postgresql redis-server zenzefi-backend nginx

# Проверка всех сервисов
sudo systemctl status postgresql redis-server zenzefi-backend nginx

# Освободить память
sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches

# Очистка старых пакетов
sudo apt autoremove -y
sudo apt autoclean

# Проверка дискового пространства по папкам
sudo du -sh /home/zenzefi/* | sort -h

# Найти большие файлы
sudo find /home/zenzefi -type f -size +100M -ls
```

---

## Переменные окружения (.env)

```bash
# Основные переменные для изменения:

DEBUG=False                           # Режим отладки (False для production)
SECRET_KEY=...                        # JWT секретный ключ (32+ символа)
BACKEND_URL=https://api.yourdomain.com  # URL backend сервера

POSTGRES_PASSWORD=...                 # Пароль базы данных
REDIS_PASSWORD=...                    # Пароль Redis

ZENZEFI_TARGET_URL=...               # URL целевого сервера Zenzefi (via VPN)

ACCESS_TOKEN_EXPIRE_MINUTES=60       # Время жизни JWT токена
COOKIE_SECURE=True                    # HTTPS only cookies
COOKIE_SAMESITE=none                  # Cross-site cookie policy
```

---

## Контакты

- **Документация**: [DEPLOYMENT.md](./DEPLOYMENT.md)
- **GitHub**: https://github.com/yourusername/zenzefi_backend
- **API Docs**: https://api.yourdomain.com/docs

---

**Примечание**: Все команды с `sudo` требуют прав администратора. Замените `api.yourdomain.com` на ваш реальный домен.