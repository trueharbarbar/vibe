import io
import requests
from flask import Flask, request, jsonify
from google_play_scraper import app as gp_app
from jinja2 import Environment, FileSystemLoader
import colorgram
from PIL import Image

# 1. Настройка Flask. ЭТА ЧАСТЬ ИСПРАВЛЯЕТ ОШИБКУ 'NameError'
app = Flask(__name__)
env = Environment(loader=FileSystemLoader('.'))

# 2. Функция для извлечения доминирующих цветов из иконки
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
        print(f"Ошибка при извлечении палитры: {e}")
        return "#2c3e50", "#3498db"

# 3. Новая функция для красивого отображения числа скачиваний
def format_downloads(num):
    if num is None:
        return "N/A"
    if num < 1000:
        return str(num)
    
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '{}{}+'.format('{:f}'.format(num).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])

# 4. Основной маршрут для генерации лендинга
@app.route('/generate-landing', methods=['POST'])
def generate_landing():
    data = request.json
    package_name = data.get('packageName')
    language = data.get('language', 'en')

    if not package_name:
        return jsonify({"error": "packageName не указан"}), 400

    try:
        app_details = gp_app(package_name, lang=language, country='US')
        
        primary_color, secondary_color = get_palette_from_url(app_details['icon'])

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
            'secondary_color': secondary_color
        }

        template = env.get_template('template.html')
        html_output = template.render(context)
        
        return html_output, 200, {'Content-Type': 'text/html; charset=utf-8'}

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 5. Запускаем сервер
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
