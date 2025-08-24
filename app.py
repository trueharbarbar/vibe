import io
import requests
import logging
from flask import Flask, request, jsonify
from google_play_scraper import app as gp_app
from jinja2 import Environment, FileSystemLoader
import colorgram
from PIL import Image

# 1. Настраиваем логирование для отладки
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 2. Создаем приложение Flask
app = Flask(__name__)
env = Environment(loader=FileSystemLoader('.'))

# 3. Читаем CSS-файл в переменную при старте, чтобы встраивать его в HTML
try:
    with open('style.css', 'r', encoding='utf-8') as f:
        css_styles = f.read()
except FileNotFoundError:
    logging.error("Файл style.css не найден! Стили не будут загружены.")
    css_styles = "/* CSS file not found */"

# 4. Вспомогательные функции
def get_palette_from_url(image_url):
    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content)).convert('RGB')
        colors = colorgram.extract(img, 6)
        primary_color = '#%02x%02x%02x' % colors[0].rgb
        secondary_color = '#%02x%02x%02x' % colors[1].rgb
        return primary_color, secondary_color
    except Exception as e:
        logging.error(f"Ошибка при извлечении палитры: {e}")
        return "#2c3e50", "#3498db"

def format_downloads(num):
    if num is None: return "N/A"
    if num < 1000: return str(num)
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '{}{}+'.format('{:f}'.format(num).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])

# 5. Основной маршрут для генерации лендинга
@app.route('/generate-landing', methods=['POST'])
def generate_landing():
    data = request.json
    package_name = data.get('packageName')
    language = data.get('language', 'en')
    
    logging.info(f"Получен запрос для пакета: {package_name}, язык: {language}")

    if not package_name:
        logging.warning("Запрос без packageName, возвращаем ошибку 400.")
        return jsonify({"error": "packageName не указан"}), 400

    try:
        logging.info(f"Начинаю скрапинг Google Play для {package_name}...")
        app_details = gp_app(package_name, lang=language, country='US')
        logging.info(f"Скрапинг для {package_name} успешно завершен.")

        logging.info("Извлекаю цвета из иконки...")
        primary_color, secondary_color = get_palette_from_url(app_details['icon'])
        logging.info(f"Цвета успешно извлечены: {primary_color}, {secondary_color}")

        context = {
            'lang': language,
            'title': app_details['title'],
            'developer': app_details['developer'],
            'icon_url': app_details['icon'],
            'cover_image': app_details.get('cover', app_details['screenshots'][0]),
            'screenshots': app_details['screenshots'],
            'description': app_details['description'],
            'store_url': app_details['url'],
            'rating': f"{app_details.get('score', 0):.1f}",
            'downloads': format_downloads(app_details.get('minInstalls', 0)),
            'video_url': app_details.get('video', '').replace('watch?v=', 'embed/'),
            'primary_color': primary_color,
            'secondary_color': secondary_color,
            'page_styles': css_styles
        }

        logging.info("Начинаю рендеринг HTML-шаблона...")
        template = env.get_template('template.html')
        html_output = template.render(context)
        logging.info("Рендеринг завершен. Отправляю HTML-ответ.")
        
        return html_output, 200, {'Content-Type': 'text/html; charset=utf-8'}

    except Exception as e:
        logging.error(f"Произошла критическая ошибка при обработке {package_name}:", exc_info=True)
        return jsonify({"error": str(e)}), 500

# 6. Тестовый маршрут для проверки работоспособности сервера
@app.route('/health', methods=['GET'])
def health_check():
    logging.info(">>> Health check endpoint was called! Server is responding.")
    return "OK", 200
