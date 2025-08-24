# Используем образ с PHP и Apache
FROM php:8.1-apache

# Установка Python и системных зависимостей
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    gcc \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Включаем mod_rewrite и mod_proxy для Apache
RUN a2enmod rewrite proxy proxy_http

# Установка рабочей директории
WORKDIR /app

# Копирование и установка Python зависимостей
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY app.py .

# Создание директорий
RUN mkdir -p /app/static/images /app/static/landings /app/static/archives /app/static/legal

# Создаем симлинк для Apache
RUN ln -s /app/static/landings /var/www/html/landing

# Конфигурация Apache
RUN echo '<VirtualHost *:80> \n\
    ServerName localhost \n\
    DocumentRoot /var/www/html \n\
    \n\
    # Алиас для лендингов \n\
    Alias /landing /app/static/landings \n\
    <Directory /app/static/landings> \n\
        Options Indexes FollowSymLinks \n\
        AllowOverride All \n\
        Require all granted \n\
        DirectoryIndex index.php index.html \n\
    </Directory> \n\
    \n\
    # Алиас для статических файлов \n\
    Alias /static /app/static \n\
    <Directory /app/static> \n\
        Options Indexes FollowSymLinks \n\
        AllowOverride None \n\
        Require all granted \n\
    </Directory> \n\
    \n\
    # Проксирование API запросов на Python \n\
    ProxyPass /generate-landing http://localhost:8080/generate-landing \n\
    ProxyPassReverse /generate-landing http://localhost:8080/generate-landing \n\
    \n\
    ProxyPass /health http://localhost:8080/health \n\
    ProxyPassReverse /health http://localhost:8080/health \n\
    \n\
    ProxyPass /config http://localhost:8080/config \n\
    ProxyPassReverse /config http://localhost:8080/config \n\
    \n\
    ProxyPass /download http://localhost:8080/download \n\
    ProxyPassReverse /download http://localhost:8080/download \n\
</VirtualHost>' > /etc/apache2/sites-available/000-default.conf

# Конфигурация Supervisor
RUN echo '[supervisord] \n\
nodaemon=true \n\
logfile=/dev/null \n\
logfile_maxbytes=0 \n\
pidfile=/var/run/supervisord.pid \n\
\n\
[program:apache2] \n\
command=/usr/sbin/apache2ctl -D FOREGROUND \n\
autostart=true \n\
autorestart=true \n\
stdout_logfile=/dev/stdout \n\
stdout_logfile_maxbytes=0 \n\
stderr_logfile=/dev/stderr \n\
stderr_logfile_maxbytes=0 \n\
\n\
[program:gunicorn] \n\
command=gunicorn --bind 127.0.0.1:8080 --workers 2 --timeout 120 app:app \n\
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

# Запуск через Supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
