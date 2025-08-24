import os
import json
import logging
import hashlib
import requests
from flask import Flask, request, jsonify, send_from_directory, abort, send_file
from google_play_scraper import app as play_scraper
from datetime import datetime
import re
import random
import zipfile
from urllib.parse import urlparse
import shutil
import traceback

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Конфигурация
BASE_URL = os.environ.get('BASE_URL', 'https://vibe.clickapi.org')
STATIC_DIR = '/app/static'
LANDINGS_DIR = os.path.join(STATIC_DIR, 'landings')
IMAGES_DIR = os.path.join(STATIC_DIR, 'images')
ARCHIVES_DIR = os.path.join(STATIC_DIR, 'archives')

# Создаем необходимые директории
for directory in [LANDINGS_DIR, IMAGES_DIR, ARCHIVES_DIR]:
    os.makedirs(directory, exist_ok=True)

logger.info(f"Starting with BASE_URL: {BASE_URL}")

def format_installs(installs):
    """Форматирование числа установок"""
    try:
        if installs >= 1_000_000_000:
            return f"{installs / 1_000_000_000:.0f}B+"
        elif installs >= 1_000_000:
            return f"{installs / 1_000_000:.0f}M+"
        elif installs >= 1_000:
            return f"{installs / 1_000:.0f}K+"
        else:
            return str(installs)
    except Exception as e:
        logger.error(f"Error formatting installs: {e}")
        return "0+"

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
        
        logger.info(f"Downloaded image: {url}")
        return True
    except Exception as e:
        logger.error(f"Failed to download image: {str(e)}")
        return False

def generate_landing_id():
    """Генерация уникального ID для лендинга"""
    content = f"{datetime.now().isoformat()}_{random.randint(1000, 9999)}"
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
            logger.error(f"No data received for {package_name}")
            return None
        
        # Создаем директорию для изображений
        app_images_dir = os.path.join(IMAGES_DIR, package_name)
        os.makedirs(app_images_dir, exist_ok=True)
        
        # Обрабатываем данные
        processed_data = {
            'title': app_data.get('title', 'Unknown App'),
            'developer': app_data.get('developer', 'Unknown Developer'),
            'description': app_data.get('description', ''),
            'rating': round(app_data.get('score', 0), 1) if app_data.get('score') else 0,
            'installs': format_installs(app_data.get('minInstalls', 0)),
            'package_name': package_name,
            'language': language,
            'icon': None,
            'screenshots': []
        }
        
        # Скачиваем иконку
        if app_data.get('icon'):
            icon_path = os.path.join(app_images_dir, 'icon.png')
            if download_image(app_data['icon'], icon_path):
                processed_data['icon'] = 'icon.png'
        
        # Скачиваем скриншоты (максимум 3 для упрощения)
        screenshots = []
        if app_data.get('screenshots'):
            for i, screenshot_url in enumerate(app_data['screenshots'][:3]):
                screenshot_path = os.path.join(app_images_dir, f'screenshot_{i}.jpg')
                if download_image(screenshot_url, screenshot_path):
                    screenshots.append(f'screenshot_{i}.jpg')
        processed_data['screenshots'] = screenshots
        
        logger.info(f"Successfully processed app data")
        return processed_data
        
    except Exception as e:
        logger.error(f"Failed to process app data: {str(e)}\n{traceback.format_exc()}")
        return None

def generate_simple_html(app_data, landing_id):
    """Генерация простого HTML без PHP"""
    html = f"""<!DOCTYPE html>
<html lang="{app_data['language']}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{app_data['title']} - Download Mobile App</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f7fa;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        .hero {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            margin-bottom: 40px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        .app-header {{
            display: flex;
            align-items: center;
            gap: 30px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }}
        .app-icon {{
            width: 120px;
            height: 120px;
            border-radius: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }}
        .app-info h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            color: #4285f4;
        }}
        .developer {{
            color: #666;
            font-size: 1.1em;
            margin-bottom: 15px;
        }}
        .stats {{
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }}
        .stat {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .stat-label {{
            color: #999;
            font-size: 0.9em;
        }}
        .stat-value {{
            font-weight: bold;
            color: #4285f4;
            font-size: 1.2em;
        }}
        .download-button {{
            display: inline-block;
            background: linear-gradient(135deg, #4285f4, #34a853);
            color: white;
            padding: 15px 40px;
            border-radius: 50px;
            text-decoration: none;
            font-size: 1.2em;
            font-weight: bold;
            margin-top: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s;
        }}
        .download-button:hover {{
            transform: translateY(-3px);
        }}
        .description {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 40px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }}
        .description h2 {{
            color: #4285f4;
            margin-bottom: 15px;
        }}
        .screenshots {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }}
        .screenshots h2 {{
            color: #4285f4;
            margin-bottom: 20px;
        }}
        .screenshot-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }}
        .screenshot img {{
            width: 100%;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        footer {{
            background: #2c3e50;
            color: white;
            padding: 40px 0;
            margin-top: 60px;
            text-align: center;
        }}
        .footer-links a {{
            color: #ecf0f1;
            text-decoration: none;
            margin: 0 15px;
        }}
        @media (max-width: 768px) {{
            .app-header {{
                flex-direction: column;
                text-align: center;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <div class="app-header">
                {f'<img src="/landing/{landing_id}/{app_data["icon"]}" alt="{app_data["title"]}" class="app-icon">' if app_data['icon'] else ''}
                <div class="app-info">
                    <h1>{app_data['title']}</h1>
                    <div class="developer">{app_data['developer']}</div>
                    <div class="stats">
                        <div class="stat">
                            <span class="stat-label">Rating:</span>
                            <span class="stat-value">⭐ {app_data['rating']}</span>
                        </div>
                        <div class="stat">
                            <span class="stat-label">Downloads:</span>
                            <span class="stat-value">{app_data['installs']}</span>
                        </div>
                    </div>
                </div>
            </div>
            <a href="https://play.google.com/store/apps/details?id={app_data['package_name']}" 
               class="download-button" target="_blank">
                Download on Google Play
            </a>
        </div>
        
        <div class="description">
            <h2>About this app</h2>
            <p>{app_data['description'][:500]}...</p>
        </div>
        
        {f'''<div class="screenshots">
            <h2>Screenshots</h2>
            <div class="screenshot-grid">
                {"".join([f'<img src="/landing/{landing_id}/{s}" alt="Screenshot">' for s in app_data['screenshots']])}
            </div>
        </div>''' if app_data['screenshots'] else ''}
    </div>
    
    <footer>
        <div class="footer-links">
            <a href="#">Privacy Policy</a>
            <a href="#">Terms of Service</a>
            <a href="mailto:mail@vibe.clickapi.org">Contact Us</a>
        </div>
        <p>© 2024 vibe.clickapi.org. All rights reserved.</p>
    </footer>
</body>
</html>"""
    return html

@app.route('/generate-landing', methods=['POST'])
def generate_landing():
    """API endpoint для генерации лендинга"""
    try:
        # Получаем параметры
        data = request.get_json()
        
        if not data or 'packageName' not in data:
            logger.error("Missing packageName")
            return jsonify({'error': 'packageName is required'}), 400
        
        package_name = data['packageName']
        language = data.get('language', 'en')
        
        logger.info(f"Processing request for {package_name}")
        
        # Получаем данные приложения
        app_data = process_app_data(package_name, language)
        
        if not app_data:
            return jsonify({'error': 'App not found'}), 404
        
        # Генерируем ID
        landing_id = generate_landing_id()
        
        # Создаем директорию для лендинга
        landing_dir = os.path.join(LANDINGS_DIR, landing_id)
        os.makedirs(landing_dir, exist_ok=True)
        
        # Копируем изображения
        source_images_dir = os.path.join(IMAGES_DIR, package_name)
        if os.path.exists(source_images_dir):
            for filename in os.listdir(source_images_dir):
                src = os.path.join(source_images_dir, filename)
                dst = os.path.join(landing_dir, filename)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
        
        # Генерируем HTML
        html_content = generate_simple_html(app_data, landing_id)
        
        # Сохраняем HTML
        html_path = os.path.join(landing_dir, 'index.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Создаем ZIP архив
        archive_path = os.path.join(ARCHIVES_DIR, f"{landing_id}.zip")
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(landing_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, landing_dir)
                    zipf.write(file_path, arcname)
        
        logger.info(f"Landing generated: {landing_id}")
        
        # Возвращаем результат
        return jsonify({
            'success': True,
            'landing_url': f"{BASE_URL}/landing/{landing_id}/",
            'archive_url': f"{BASE_URL}/download/{landing_id}.zip",
            'landing_id': landing_id,
            'package_name': package_name,
            'language': language
        }), 200
        
    except Exception as e:
        logger.error(f"Error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

@app.route('/landing/<landing_id>/')
@app.route('/landing/<landing_id>/index.html')
def serve_landing(landing_id):
    """Отдача лендинга"""
    try:
        landing_dir = os.path.join(LANDINGS_DIR, landing_id)
        return send_from_directory(landing_dir, 'index.html')
    except:
        abort(404)

@app.route('/landing/<landing_id>/<path:filename>')
def serve_landing_resource(landing_id, filename):
    """Отдача ресурсов лендинга"""
    try:
        landing_dir = os.path.join(LANDINGS_DIR, landing_id)
        return send_from_directory(landing_dir, filename)
    except:
        abort(404)

@app.route('/download/<filename>')
def download_archive(filename):
    """Скачивание архива"""
    try:
        return send_from_directory(ARCHIVES_DIR, filename)
    except:
        abort(404)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'base_url': BASE_URL
    }), 200

@app.route('/config', methods=['GET'])
def get_config():
    """Get configuration"""
    return jsonify({
        'base_url': BASE_URL,
        'directories': {
            'static': STATIC_DIR,
            'landings': LANDINGS_DIR,
            'images': IMAGES_DIR,
            'archives': ARCHIVES_DIR
        }
    }), 200

if __name__ == '__main__':
    logger.info("Starting application")
    app.run(host='0.0.0.0', port=8080, debug=True)
