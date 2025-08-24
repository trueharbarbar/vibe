import os
import json
import logging
import hashlib
import requests
from flask import Flask, request, jsonify, send_from_directory, abort
from google_play_scraper import app as play_scraper
from PIL import Image
from colorthief import ColorThief
import io
from datetime import datetime
from jinja2 import Template
import re

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Конфигурация
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8080')
STATIC_DIR = '/app/static'
LANDINGS_DIR = os.path.join(STATIC_DIR, 'landings')
IMAGES_DIR = os.path.join(STATIC_DIR, 'images')

# Создаем необходимые директории
os.makedirs(LANDINGS_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

def format_installs(installs):
    """Форматирование числа установок в человекочитаемый вид"""
    if installs >= 1_000_000_000:
        return f"{installs / 1_000_000_000:.0f}B+"
    elif installs >= 1_000_000:
        return f"{installs / 1_000_000:.0f}M+"
    elif installs >= 1_000:
        return f"{installs / 1_000:.0f}K+"
    else:
        return str(installs)

def get_youtube_embed_url(video_url):
    """Преобразование YouTube URL в embed формат"""
    if not video_url:
        return None
    
    video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', video_url)
    if video_id_match:
        video_id = video_id_match.group(1)
        return f"https://www.youtube.com/embed/{video_id}"
    return None

def download_image(url, save_path):
    """Скачивание и сохранение изображения"""
    try:
        if os.path.exists(save_path):
            logger.info(f"Image already cached: {save_path}")
            return True
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"Downloaded image: {url} -> {save_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to download image {url}: {str(e)}")
        return False

def extract_dominant_colors(image_path, num_colors=3):
    """Извлечение доминирующих цветов из изображения"""
    try:
        color_thief = ColorThief(image_path)
        palette = color_thief.get_palette(color_count=num_colors, quality=1)
        
        colors = []
        for rgb in palette[:num_colors]:
            hex_color = '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
            colors.append(hex_color)
        
        # Заполняем недостающие цвета дефолтными
        while len(colors) < 3:
            colors.append('#4285f4')
        
        return colors
    except Exception as e:
        logger.error(f"Failed to extract colors: {str(e)}")
        return ['#4285f4', '#34a853', '#fbbc04']  # Google colors as fallback

def generate_landing_id(package_name, language):
    """Генерация уникального ID для лендинга"""
    content = f"{package_name}_{language}_{datetime.now().strftime('%Y%m%d')}"
    return hashlib.md5(content.encode()).hexdigest()[:12]

def process_app_data(package_name, language):
    """Получение и обработка данных приложения из Google Play"""
    try:
        logger.info(f"Fetching app data for {package_name} in {language}")
        
        # Получаем данные из Google Play
        app_data = play_scraper(
            package_name,
            lang=language,
            country='us'
        )
        
        if not app_data:
            return None
        
        # Создаем директорию для изображений приложения
        app_images_dir = os.path.join(IMAGES_DIR, package_name)
        os.makedirs(app_images_dir, exist_ok=True)
        
        # Обрабатываем изображения
        processed_data = {
            'title': app_data.get('title', 'Unknown App'),
            'developer': app_data.get('developer', 'Unknown Developer'),
            'description': app_data.get('description', ''),
            'rating': round(app_data.get('score', 0), 1) if app_data.get('score') else 0,
            'installs': format_installs(app_data.get('minInstalls', 0)),
            'package_name': package_name,
            'language': language
        }
        
        # Скачиваем иконку
        if app_data.get('icon'):
            icon_path = os.path.join(app_images_dir, 'icon.png')
            if download_image(app_data['icon'], icon_path):
                processed_data['icon'] = f"/static/images/{package_name}/icon.png"
                processed_data['colors'] = extract_dominant_colors(icon_path)
            else:
                processed_data['icon'] = None
                processed_data['colors'] = ['#4285f4', '#34a853', '#fbbc04']
        
        # Скачиваем обложку
        if app_data.get('headerImage'):
            cover_path = os.path.join(app_images_dir, 'cover.jpg')
            if download_image(app_data['headerImage'], cover_path):
                processed_data['cover'] = f"/static/images/{package_name}/cover.jpg"
            else:
                processed_data['cover'] = None
        
        # Скачиваем скриншоты
        screenshots = []
        if app_data.get('screenshots'):
            for i, screenshot_url in enumerate(app_data['screenshots'][:6]):
                screenshot_path = os.path.join(app_images_dir, f'screenshot_{i}.jpg')
                if download_image(screenshot_url, screenshot_path):
                    screenshots.append(f"/static/images/{package_name}/screenshot_{i}.jpg")
        processed_data['screenshots'] = screenshots
        
        # Обрабатываем видео
        if app_data.get('video'):
            processed_data['video'] = get_youtube_embed_url(app_data['video'])
        else:
            processed_data['video'] = None
        
        logger.info(f"Successfully processed app data for {package_name}")
        return processed_data
        
    except Exception as e:
        logger.error(f"Failed to process app data: {str(e)}")
        return None

def generate_html(app_data):
    """Генерация HTML страницы лендинга"""
    template = Template('''<!DOCTYPE html>
<html lang="{{ language }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - Download Mobile App</title>
    <style>
        :root {
            --primary-color: {{ colors[0] }};
            --secondary-color: {{ colors[1] }};
            --accent-color: {{ colors[2] }};
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .hero {
            background: white;
            border-radius: 20px;
            padding: 40px;
            margin-bottom: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.1);
        }
        
        .app-header {
            display: flex;
            align-items: center;
            gap: 30px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        
        .app-icon {
            width: 120px;
            height: 120px;
            border-radius: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }
        
        .app-info h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            color: var(--primary-color);
        }
        
        .developer {
            color: #666;
            font-size: 1.1em;
            margin-bottom: 15px;
        }
        
        .stats {
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }
        
        .stat {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .stat-label {
            color: #999;
            font-size: 0.9em;
        }
        
        .stat-value {
            font-weight: bold;
            color: var(--primary-color);
            font-size: 1.2em;
        }
        
        .download-button {
            display: inline-block;
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            padding: 15px 40px;
            border-radius: 50px;
            text-decoration: none;
            font-size: 1.2em;
            font-weight: bold;
            margin-top: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s;
        }
        
        .download-button:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.25);
        }
        
        .description {
            background: #f8f9fa;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 40px;
        }
        
        .description h2 {
            color: var(--primary-color);
            margin-bottom: 15px;
        }
        
        .description-text {
            color: #555;
            line-height: 1.8;
            white-space: pre-wrap;
        }
        
        {% if video %}
        .video-section {
            background: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 40px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        .video-section h2 {
            color: var(--primary-color);
            margin-bottom: 20px;
        }
        
        .video-wrapper {
            position: relative;
            padding-bottom: 56.25%;
            height: 0;
            overflow: hidden;
            border-radius: 10px;
        }
        
        .video-wrapper iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: none;
        }
        {% endif %}
        
        {% if screenshots %}
        .screenshots {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        .screenshots h2 {
            color: var(--primary-color);
            margin-bottom: 20px;
        }
        
        .screenshot-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
        
        .screenshot {
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        
        .screenshot:hover {
            transform: scale(1.05);
        }
        
        .screenshot img {
            width: 100%;
            height: auto;
            display: block;
        }
        {% endif %}
        
        @media (max-width: 768px) {
            .app-header {
                flex-direction: column;
                text-align: center;
            }
            
            .app-info h1 {
                font-size: 2em;
            }
            
            .stats {
                justify-content: center;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <div class="app-header">
                {% if icon %}
                <img src="{{ icon }}" alt="{{ title }}" class="app-icon">
                {% endif %}
                <div class="app-info">
                    <h1>{{ title }}</h1>
                    <div class="developer">{{ developer }}</div>
                    <div class="stats">
                        <div class="stat">
                            <span class="stat-label">Rating:</span>
                            <span class="stat-value">⭐ {{ rating }}</span>
                        </div>
                        <div class="stat">
                            <span class="stat-label">Downloads:</span>
                            <span class="stat-value">{{ installs }}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <a href="https://play.google.com/store/apps/details?id={{ package_name }}" 
               class="download-button" target="_blank">
                Download on Google Play
            </a>
        </div>
        
        {% if description %}
        <div class="description">
            <h2>About this app</h2>
            <div class="description-text">{{ description[:1000] }}{% if description|length > 1000 %}...{% endif %}</div>
        </div>
        {% endif %}
        
        {% if video %}
        <div class="video-section">
            <h2>Preview Video</h2>
            <div class="video-wrapper">
                <iframe src="{{ video }}" 
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                        allowfullscreen>
                </iframe>
            </div>
        </div>
        {% endif %}
        
        {% if screenshots %}
        <div class="screenshots">
            <h2>Screenshots</h2>
            <div class="screenshot-grid">
                {% for screenshot in screenshots %}
                <div class="screenshot">
                    <img src="{{ screenshot }}" alt="Screenshot {{ loop.index }}" loading="lazy">
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}
    </div>
</body>
</html>''')
    
    return template.render(**app_data)

@app.route('/generate-landing', methods=['POST'])
def generate_landing():
    """API endpoint для генерации лендинга"""
    try:
        # Получаем параметры из запроса
        data = request.get_json()
        
        if not data or 'packageName' not in data:
            logger.error("Missing packageName in request")
            return jsonify({'error': 'packageName is required'}), 400
        
        package_name = data['packageName']
        language = data.get('language', 'en')
        
        logger.info(f"Received request for {package_name} in {language}")
        
        # Получаем и обрабатываем данные приложения
        app_data = process_app_data(package_name, language)
        
        if not app_data:
            logger.error(f"App not found: {package_name}")
            return jsonify({'error': 'App not found'}), 404
        
        # Генерируем уникальный ID для лендинга
        landing_id = generate_landing_id(package_name, language)
        landing_filename = f"{landing_id}.html"
        landing_path = os.path.join(LANDINGS_DIR, landing_filename)
        
        # Генерируем HTML
        html_content = generate_html(app_data)
        
        # Сохраняем HTML файл
        with open(landing_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Landing generated successfully: {landing_filename}")
        
        # Формируем URL лендинга
        landing_url = f"{BASE_URL}/landing/{landing_filename}"
        
        # Возвращаем ссылку на готовый лендинг
        return jsonify({
            'success': True,
            'landing_url': landing_url,
            'landing_id': landing_id,
            'package_name': package_name,
            'language': language
        }), 200
        
    except Exception as e:
        logger.error(f"Internal error: {str(e)}")
        return jsonify({'error': 'An internal error occurred'}), 500

@app.route('/landing/<filename>')
def serve_landing(filename):
    """Отдача готового лендинга"""
    try:
        return send_from_directory(LANDINGS_DIR, filename)
    except:
        abort(404)

@app.route('/static/images/<path:filepath>')
def serve_image(filepath):
    """Отдача изображений"""
    try:
        return send_from_directory(IMAGES_DIR, filepath)
    except:
        abort(404)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
