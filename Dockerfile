FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование файла зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY app.py .

# Создание директорий для статических файлов
RUN mkdir -p /app/static/images /app/static/landings /app/static/archives /app/static/legal

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV BASE_URL=https://vibe.clickapi.org

# Открытие порта
EXPOSE 80

# Запуск приложения через Gunicorn на порту 80
CMD ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "4", "--timeout", "120", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
