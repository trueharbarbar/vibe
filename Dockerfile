# Используем образ с PHP и Apache
FROM php:8.1-apache

# Установка Python и системных зависимостей
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    gcc \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Включаем необходимые модули Apache
RUN a2enmod rewrite proxy proxy_http headers

# Установка рабочей директории
WORKDIR /app

# Копирование и установка Python зависимостей
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Копирование кода приложения
COPY app.py .

# Создание директорий
RUN mkdir -p /app/static/images /app/static/landings /app/static/archives /app/static/legal

# Настройка прав доступа
RUN chown -R www-data:www-data /app/static

# Конфигурация Apache с правильным проксированием
RUN echo '<VirtualHost *:80> \n\
    ServerName localhost \n\
    \n\
    # Логирование для отладки \n\
    ErrorLog /dev/stderr \n\
    CustomLog /dev/stdout combined \n\
    LogLevel info \n\
    \n\
    # Проксирование API запросов на Python приложение \n\
    ProxyPreserveHost On \n\
    ProxyRequests Off \n\
    \n\
    # API endpoints \n\
    ProxyPass /generate-landing http://127.0.0.1:8080/generate-landing \n\
    ProxyPassReverse /generate-landing http://127.0.0.1:8080/generate-landing \n\
    \n\
    ProxyPass /health http://127.0.0.1:8080/health \n\
    ProxyPassReverse /health http://127.0.0.1:8080/health \n\
    \n\
    ProxyPass /config http://127.0.0.1:8080/config \n\
    ProxyPassReverse /config http://127.0.0.1:8080/config \n\
    \n\
    ProxyPass /test http://127.0.0.1:8080/test \n\
    ProxyPassReverse /test http://127.0.0.1:8080/test \n\
    \n\
    # Лендинги и статические файлы \n\
    ProxyPass /landing http://127.0.0.1:8080/landing \n\
    ProxyPassReverse /landing http://127.0.0.1:8080/landing \n\
    \n\
    ProxyPass /download http://127.0.0.1:8080/download \n\
    ProxyPassReverse /download http://127.0.0.1:8080/download \n\
    \n\
    # Таймауты для длительных запросов \n\
    ProxyTimeout 300 \n\
    ProxyBadHeader Ignore \n\
    \n\
    # Главная страница \n\
    ProxyPass / http://127.0.0.1:8080/ \n\
    ProxyPassReverse / http://127.0.0.1:8080/ \n\
</VirtualHost>' > /etc/apache2/sites-available/000-default.conf

# Отключаем дефолтный сайт Apache и включаем наш
RUN a2dissite 000-default && a2ensite 000-default

# Конфигурация Supervisor
RUN echo '[supervisord] \n\
nodaemon=true \n\
logfile=/dev/stdout \n\
logfile_maxbytes=0 \n\
loglevel=info \n\
\n\
[program:apache2] \n\
command=apache2ctl -D FOREGROUND \n\
autostart=true \n\
autorestart=true \n\
stdout_logfile=/dev/stdout \n\
stdout_logfile_maxbytes=0 \n\
stderr_logfile=/dev/stderr \n\
stderr_logfile_maxbytes=0 \n\
\n\
[program:gunicorn] \n\
command=gunicorn --bind 127.0.0.1:8080 --workers 2 --timeout 120 --log-level debug app:app \n\
directory=/app \n\
autostart=true \n\
autorestart=true \n\
stdout_logfile=/dev/stdout \n\
stdout_logfile_maxbytes=0 \n\
stderr_logfile=/dev/stderr \n\
stderr_logfile_maxbytes=0' > /etc/supervisor/conf.d/supervisord.conf

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV BASE_URL=https://vibe.clickapi.org

# Открытие порта
EXPOSE 80

# Добавляем простой тестовый endpoint в app.py
RUN echo "
@app.route('/test', methods=['GET'])
def test():
    return 'API is working!', 200
" >> app.py

# Запуск через Supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
