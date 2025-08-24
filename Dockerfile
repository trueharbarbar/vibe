FROM python:3.9-slim

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
RUN mkdir -p /app/static/images /app/static/landings

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV BASE_URL=http://localhost:8080

# Открытие порта
EXPOSE 8080

# Запуск приложения через Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "120", "--log-level", "info", "app:app"]
