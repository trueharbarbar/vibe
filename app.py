#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import hashlib
import requests
from flask import Flask, request, jsonify, send_from_directory, abort, make_response
from google_play_scraper import app as play_scraper, search
from PIL import Image
from colorthief import ColorThief
import io
from datetime import datetime
from jinja2 import Template
import re
import random
import zipfile
from urllib.parse import urlparse
import colorsys
import shutil
import traceback

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаем Flask приложение
app = Flask(__name__)

# Конфигурация
BASE_URL = os.environ.get('BASE_URL', 'https://vibe.clickapi.org')
STATIC_DIR = os.environ.get('STATIC_DIR', '/app/static')
LANDINGS_DIR = os.path.join(STATIC_DIR, 'landings')
IMAGES_DIR = os.path.join(STATIC_DIR, 'images')
ARCHIVES_DIR = os.path.join(STATIC_DIR, 'archives')
LEGAL_DIR = os.path.join(STATIC_DIR, 'legal')

# Создаем необходимые директории
for directory in [LANDINGS_DIR, IMAGES_DIR, ARCHIVES_DIR, LEGAL_DIR]:
    try:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Directory ready: {directory}")
    except Exception as e:
        logger.error(f"Failed to create directory {directory}: {e}")

logger.info(f"Starting with BASE_URL: {BASE_URL}")
logger.info(f"Static directory: {STATIC_DIR}")

def format_installs(installs):
    """Форматирование числа установок в человекочитаемый вид"""
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

def format_size(size_bytes):
    """Форматирование размера в человекочитаемый вид"""
    try:
        if not size_bytes:
            return "Varies"
        # Преобразуем строку в число если нужно
        if isinstance(size_bytes, str):
            # Удаляем все нецифровые символы кроме точки
            size_bytes = re.sub(r'[^\d.]', '', size_bytes)
            if not size_bytes:
                return "Varies"
            size_bytes = float(size_bytes)
        
        size_mb = float(size_bytes) / (1024 * 1024)
        if size_mb < 1:
            return f"{int(float(size_bytes) / 1024)} KB"
        elif size_mb < 1024:
            return f"{size_mb:.1f} MB"
        else:
            return f"{size_mb / 1024:.1f} GB"
    except Exception as e:
        logger.error(f"Error formatting size: {e}")
        return "Varies"

def get_youtube_embed_url(video_url):
    """Преобразование YouTube URL в embed формат"""
    try:
        if not video_url:
            return None
        
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', video_url)
        if video_id_match:
            video_id = video_id_match.group(1)
            return f"https://www.youtube.com/embed/{video_id}"
        return None
    except Exception as e:
        logger.error(f"Error converting YouTube URL: {e}")
        return None

def download_image(url, save_path):
    """Скачивание и сохранение изображения"""
    try:
        if os.path.exists(save_path):
            logger.info(f"Image already cached: {save_path}")
            return True
        
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"Downloaded image: {url} -> {save_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to download image {url}: {str(e)}")
        return False

def vary_color(hex_color, variation=0.15):
    """Варьирование цвета для создания уникальности"""
    try:
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        
        h = (h + random.uniform(-variation, variation)) % 1
        s = max(0, min(1, s + random.uniform(-variation/2, variation/2)))
        v = max(0.3, min(1, v + random.uniform(-variation/2, variation/2)))
        
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        
        return '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b*255))
    except Exception as e:
        logger.error(f"Error varying color: {e}")
        return hex_color

def extract_dominant_colors(image_path, num_colors=3):
    """Извлечение доминирующих цветов из изображения"""
    try:
        color_thief = ColorThief(image_path)
        palette = color_thief.get_palette(color_count=num_colors, quality=1)
        
        colors = []
        for rgb in palette[:num_colors]:
            hex_color = '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
            colors.append(vary_color(hex_color, 0.1))
        
        default_colors = ['#4285f4', '#34a853', '#fbbc04']
        while len(colors) < 3:
            colors.append(vary_color(random.choice(default_colors)))
        
        return colors
    except Exception as e:
        logger.error(f"Failed to extract colors: {str(e)}")
        return [vary_color(c) for c in ['#4285f4', '#34a853', '#fbbc04']]

def get_similar_apps(package_name, developer, category, max_apps=8):
    """Получение похожих приложений"""
    try:
        similar_apps = []
        
        # Пробуем найти приложения того же разработчика
        if developer:
            try:
                dev_results = search(developer, n_hits=5)
                for app in dev_results:
                    if app.get('appId') != package_name:
                        similar_apps.append({
                            'title': app.get('title', ''),
                            'icon': app.get('icon', ''),
                            'package_name': app.get('appId', ''),
                            'rating': round(app.get('score', 0), 1) if app.get('score') else 0
                        })
            except Exception as e:
                logger.error(f"Error searching by developer: {e}")
        
        # Если мало приложений, ищем по категории
        if len(similar_apps) < 4 and category:
            try:
                # Извлекаем ключевые слова из категории
                category_keywords = category.split('_')[-1] if '_' in category else category
                cat_results = search(category_keywords, n_hits=10)
                for app in cat_results:
                    if app.get('appId') != package_name and not any(s['package_name'] == app.get('appId') for s in similar_apps):
                        similar_apps.append({
                            'title': app.get('title', ''),
                            'icon': app.get('icon', ''),
                            'package_name': app.get('appId', ''),
                            'rating': round(app.get('score', 0), 1) if app.get('score') else 0
                        })
                        if len(similar_apps) >= max_apps:
                            break
            except Exception as e:
                logger.error(f"Error searching by category: {e}")
        
        return similar_apps[:max_apps]
    except Exception as e:
        logger.error(f"Error getting similar apps: {e}")
        return []

def generate_landing_id(package_name, language):
    """Генерация уникального ID для лендинга"""
    content = f"{package_name}_{language}_{datetime.now().isoformat()}_{random.randint(1000, 9999)}"
    return hashlib.md5(content.encode()).hexdigest()[:12]

def generate_randomization_params():
    """Генерация параметров для рандомизации дизайна"""
    try:
        params = {
            'layout_style': random.choice(['classic', 'modern', 'minimal', 'bold', 'elegant']),
            'hero_layout': random.choice(['left-aligned', 'center-aligned', 'right-aligned']),
            'screenshot_layout': random.choice(['grid', 'carousel', 'masonry']),
            'font_family': random.choice([
                '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, sans-serif',
                '"SF Pro Display", -apple-system, BlinkMacSystemFont, sans-serif',
                'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
                '"Google Sans", Roboto, Arial, sans-serif'
            ]),
            'heading_weight': random.choice(['600', '700', '800', '900']),
            'title_size': random.uniform(2.2, 3.0),
            'container_padding': random.randint(20, 40),
            'section_spacing': random.randint(30, 50),
            'border_radius': random.randint(10, 25),
            'button_radius': random.choice(['50px', '15px', '25px', '10px']),
            'shadow_intensity': random.uniform(0.05, 0.2),
            'gradient_angle': random.randint(90, 180),
            'animation_speed': random.uniform(0.2, 0.5),
            'use_gradient_bg': random.choice([True, False]),
            'dark_mode': random.choice([False, False, False, True]),
            'stats_style': random.choice(['inline', 'cards', 'badges']),
            'button_style': random.choice(['solid', 'gradient', 'outline']),
            'description_style': random.choice(['card', 'transparent', 'bordered']),
            'sections_order': random.sample(['description', 'video', 'screenshots'], 3)
        }
        return params
    except Exception as e:
        logger.error(f"Error generating randomization params: {e}")
        return {
            'layout_style': 'classic',
            'hero_layout': 'left-aligned',
            'screenshot_layout': 'grid',
            'font_family': '-apple-system, BlinkMacSystemFont, sans-serif',
            'heading_weight': '700',
            'title_size': 2.5,
            'container_padding': 30,
            'section_spacing': 40,
            'border_radius': 15,
            'button_radius': '50px',
            'shadow_intensity': 0.1,
            'gradient_angle': 135,
            'animation_speed': 0.3,
            'use_gradient_bg': False,
            'dark_mode': False,
            'stats_style': 'inline',
            'button_style': 'gradient',
            'description_style': 'card',
            'sections_order': ['description', 'video', 'screenshots']
        }

def process_app_data(package_name, language):
    """Получение и обработка данных приложения из Google Play"""
    try:
        logger.info(f"Fetching app data for {package_name} in {language}")
        
        app_data = play_scraper(
            package_name,
            lang=language,
            country='us'
        )
        
        if not app_data:
            logger.error(f"No data received from Google Play for {package_name}")
            return None
        
        app_images_dir = os.path.join(IMAGES_DIR, package_name)
        os.makedirs(app_images_dir, exist_ok=True)
        
        # Получаем ПОЛНОЕ описание
        full_description = app_data.get('descriptionHTML', '') or app_data.get('description', '')
        # Очищаем HTML теги если есть
        full_description = re.sub('<.*?>', '', full_description)
        
        # Получаем краткое описание (summary)
        summary = app_data.get('summary', '')
        
        processed_data = {
            'title': app_data.get('title', 'Unknown App'),
            'developer': app_data.get('developer', 'Unknown Developer'),
            'description': full_description,  # Полное описание
            'summary': summary,  # Краткое описание
            'rating': round(app_data.get('score', 0), 1) if app_data.get('score') else 0,
            'ratings_count': app_data.get('ratings', 0),
            'installs': format_installs(app_data.get('minInstalls', 0)),
            'installs_raw': app_data.get('minInstalls', 0),
            'package_name': package_name,
            'language': language,
            'colors': ['#4285f4', '#34a853', '#fbbc04'],
            'icon': None,
            'cover': None,
            'screenshots': [],
            'video': None,
            'category': app_data.get('genre', ''),
            'category_id': app_data.get('genreId', ''),
            'content_rating': app_data.get('contentRating', ''),
            'price': app_data.get('price', 0),
            'free': app_data.get('free', True),
            'updated': app_data.get('updated', ''),
            'version': app_data.get('version', ''),
            'size': format_size(app_data.get('size', '')),
            'android_version': app_data.get('androidVersion', ''),
            'developer_email': app_data.get('developerEmail', ''),
            'developer_website': app_data.get('developerWebsite', ''),
            'developer_address': app_data.get('developerAddress', ''),
            'similar_apps': [],
            'reviews': [],
            'recent_changes': app_data.get('recentChanges', ''),
            'contains_ads': app_data.get('containsAds', False),
            'in_app_purchases': app_data.get('offersIAP', False)
        }
        
        # Скачиваем иконку
        if app_data.get('icon'):
            icon_path = os.path.join(app_images_dir, 'icon.png')
            if download_image(app_data['icon'], icon_path):
                processed_data['icon'] = 'icon.png'
                processed_data['colors'] = extract_dominant_colors(icon_path)
        
        # Скачиваем обложку
        if app_data.get('headerImage'):
            cover_path = os.path.join(app_images_dir, 'cover.jpg')
            if download_image(app_data['headerImage'], cover_path):
                processed_data['cover'] = 'cover.jpg'
        
        # Скачиваем скриншоты (все доступные)
        screenshots = []
        if app_data.get('screenshots'):
            for i, screenshot_url in enumerate(app_data['screenshots']):
                screenshot_path = os.path.join(app_images_dir, f'screenshot_{i}.jpg')
                if download_image(screenshot_url, screenshot_path):
                    screenshots.append(f'screenshot_{i}.jpg')
        processed_data['screenshots'] = screenshots
        
        # Обрабатываем видео
        if app_data.get('video'):
            processed_data['video'] = get_youtube_embed_url(app_data['video'])
        
        # Получаем похожие приложения
        similar_apps = get_similar_apps(
            package_name, 
            app_data.get('developer'), 
            app_data.get('genreId'),
            max_apps=8
        )
        
        # Скачиваем иконки похожих приложений
        for i, similar_app in enumerate(similar_apps):
            if similar_app.get('icon'):
                similar_icon_path = os.path.join(app_images_dir, f'similar_{i}.png')
                if download_image(similar_app['icon'], similar_icon_path):
                    similar_app['icon_local'] = f'similar_{i}.png'
        
        processed_data['similar_apps'] = similar_apps
        
        # Получаем примеры отзывов (если доступны)
        if app_data.get('comments'):
            reviews = []
            for comment in app_data.get('comments', [])[:5]:
                reviews.append({
                    'author': comment.get('userName', 'User'),
                    'rating': comment.get('score', 5),
                    'text': comment.get('text', ''),
                    'date': comment.get('at', '')
                })
            processed_data['reviews'] = reviews
        
        logger.info(f"Successfully processed app data for {package_name}")
        logger.info(f"Description length: {len(full_description)} characters")
        return processed_data
        
    except Exception as e:
        logger.error(f"Failed to process app data: {str(e)}\n{traceback.format_exc()}")
        return None

# [Здесь идут функции generate_html, generate_privacy_policy, generate_terms_of_service, create_landing_archive - они остаются без изменений]

@app.route('/', methods=['GET'])
def index():
    """Главная страница"""
    logger.info("Index page requested")
    return jsonify({
        'status': 'Landing Generator API is working!',
        'endpoints': {
            'POST /generate-landing': 'Generate landing page',
            'GET /health': 'Health check',
            'GET /config': 'Get configuration'
        },
        'base_url': BASE_URL,
        'version': '2.0'
    }), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'base_url': BASE_URL,
        'timestamp': datetime.now().isoformat()
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

@app.route('/generate-landing', methods=['POST'])
def generate_landing():
    """API endpoint для генерации лендинга"""
    try:
        logger.info(f"Received request: {request.method} {request.path}")
        logger.info(f"Request headers: {dict(request.headers)}")
        
        # Получаем данные из запроса
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        logger.info(f"Request data: {data}")
        
        if not data or 'packageName' not in data:
            error_msg = "Missing packageName in request"
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 400
        
        package_name = data['packageName']
        language = data.get('language', 'en')
        
        logger.info(f"Processing request for {package_name} in {language}")
        
        # Получаем и обрабатываем данные приложения
        app_data = process_app_data(package_name, language)
        
        if not app_data:
            error_msg = f"App not found: {package_name}"
            logger.error(error_msg)
            return jsonify({'error': 'App not found'}), 404
        
        # Генерируем уникальный ID для лендинга
        landing_id = generate_landing_id(package_name, language)
        
        # Создаем директорию для этого лендинга
        landing_dir = os.path.join(LANDINGS_DIR, landing_id)
        os.makedirs(landing_dir, exist_ok=True)
        
        # Копируем изображения в директорию лендинга
        source_images_dir = os.path.join(IMAGES_DIR, package_name)
        if os.path.exists(source_images_dir):
            for filename in os.listdir(source_images_dir):
                src = os.path.join(source_images_dir, filename)
                dst = os.path.join(landing_dir, filename)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                    logger.info(f"Copied image {filename} to landing directory")
        
        # Генерируем HTML
        html_content = generate_html(app_data, landing_id)
        
        # Сохраняем HTML файл
        landing_html_path = os.path.join(landing_dir, 'index.html')
        with open(landing_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Генерируем правовые документы
        privacy_content = generate_privacy_policy(app_data['title'])
        terms_content = generate_terms_of_service(app_data['title'])
        
        with open(os.path.join(landing_dir, 'privacy.html'), 'w', encoding='utf-8') as f:
            f.write(privacy_content)
        
        with open(os.path.join(landing_dir, 'terms.html'), 'w', encoding='utf-8') as f:
            f.write(terms_content)
        
        # Создаем ZIP архив
        archive_path = create_landing_archive(landing_dir, landing_id)
        
        logger.info(f"Landing generated successfully: {landing_id}")
        
        # Формируем URLs
        landing_url = f"{BASE_URL}/landing/{landing_id}/"
        archive_url = f"{BASE_URL}/download/{landing_id}.zip" if archive_path else None
        
        # Возвращаем ссылки
        response_data = {
            'success': True,
            'landing_url': landing_url,
            'landing_id': landing_id,
            'package_name': package_name,
            'language': language,
            'app_title': app_data.get('title', 'Unknown App')
        }
        
        if archive_url:
            response_data['archive_url'] = archive_url
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Internal error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'error': 'An internal error occurred',
            'details': str(e)
        }), 500

@app.route('/landing/<landing_id>/')
@app.route('/landing/<landing_id>/index.html')
def serve_landing(landing_id):
    """Отдача готового лендинга"""
    try:
        landing_dir = os.path.join(LANDINGS_DIR, landing_id)
        return send_from_directory(landing_dir, 'index.html')
    except Exception as e:
        logger.error(f"Error serving landing: {e}")
        abort(404)

@app.route('/landing/<landing_id>/<path:filename>')
def serve_landing_resource(landing_id, filename):
    """Отдача ресурсов лендинга"""
    try:
        landing_dir = os.path.join(LANDINGS_DIR, landing_id)
        return send_from_directory(landing_dir, filename)
    except Exception as e:
        logger.error(f"Error serving resource: {e}")
        abort(404)

@app.route('/download/<filename>')
def download_archive(filename):
    """Скачивание ZIP архива"""
    try:
        return send_from_directory(ARCHIVES_DIR, filename)
    except Exception as e:
        logger.error(f"Error downloading archive: {e}")
        abort(404)

# Обработчик ошибок
@app.errorhandler(404)
def not_found(error):
    logger.error(f"404 error: {request.url}")
    return jsonify({'error': 'Endpoint not found', 'url': request.url}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# Для отладки - выводим все маршруты
logger.info("Registered routes:")
for rule in app.url_map.iter_rules():
    logger.info(f"  {rule.endpoint}: {rule.rule} [{', '.join(rule.methods)}]")

if __name__ == '__main__':
    logger.info("Starting Flask application directly")
    app.run(host='0.0.0.0', port=8080, debug=True)
else:
    logger.info("Flask app created for Gunicorn")
