import os
import json
import logging
import hashlib
import requests
from flask import Flask, request, jsonify, send_from_directory, abort, send_file
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

app = Flask(__name__)

# Конфигурация
BASE_URL = os.environ.get('BASE_URL', 'https://vibe.clickapi.org')
STATIC_DIR = '/app/static'
LANDINGS_DIR = os.path.join(STATIC_DIR, 'landings')
IMAGES_DIR = os.path.join(STATIC_DIR, 'images')
ARCHIVES_DIR = os.path.join(STATIC_DIR, 'archives')
LEGAL_DIR = os.path.join(STATIC_DIR, 'legal')

# Создаем необходимые директории
for directory in [LANDINGS_DIR, IMAGES_DIR, ARCHIVES_DIR, LEGAL_DIR]:
    os.makedirs(directory, exist_ok=True)

logger.info(f"Starting with BASE_URL: {BASE_URL}")

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
        size_mb = float(size_bytes) / (1024 * 1024)
        if size_mb < 1:
            return f"{int(float(size_bytes) / 1024)} KB"
        elif size_mb < 1024:
            return f"{size_mb:.1f} MB"
        else:
            return f"{size_mb / 1024:.1f} GB"
    except:
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
            except:
                pass
        
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
            except:
                pass
        
        return similar_apps[:max_apps]
    except Exception as e:
        logger.error(f"Error getting similar apps: {e}")
        return []

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

def generate_html(app_data, landing_id):
    """Генерация HTML страницы лендинга с улучшенным контентом"""
    try:
        r = generate_randomization_params()
        template_data = {**app_data, **r, 'landing_id': landing_id}
        
        # Обновляем пути к изображениям
        if template_data.get('icon'):
            template_data['icon'] = f"/landing/{landing_id}/{template_data['icon']}"
        if template_data.get('cover'):
            template_data['cover'] = f"/landing/{landing_id}/{template_data['cover']}"
        if template_data.get('screenshots'):
            template_data['screenshots'] = [f"/landing/{landing_id}/{s}" for s in template_data['screenshots']]
        
        # Обновляем пути для похожих приложений
        for similar_app in template_data.get('similar_apps', []):
            if similar_app.get('icon_local'):
                similar_app['icon_local'] = f"/landing/{landing_id}/{similar_app['icon_local']}"
        
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
            --shadow-intensity: {{ shadow_intensity }};
            --animation-speed: {{ animation_speed }}s;
            --border-radius: {{ border_radius }}px;
            --section-spacing: {{ section_spacing }}px;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: {{ font_family }};
            line-height: 1.6;
            color: {% if dark_mode %}#e0e0e0{% else %}#333{% endif %};
            {% if use_gradient_bg %}
            background: linear-gradient({{ gradient_angle }}deg, 
                {{ colors[0] }}22 0%, 
                {{ colors[1] }}22 100%);
            {% else %}
            background: {% if dark_mode %}#121212{% else %}#f5f7fa{% endif %};
            {% endif %}
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: {{ container_padding }}px;
        }
        
        .hero {
            background: {% if dark_mode %}#1e1e1e{% else %}white{% endif %};
            border-radius: var(--border-radius);
            padding: {{ section_spacing }}px;
            margin-bottom: var(--section-spacing);
            box-shadow: 0 10px 40px rgba(0,0,0,calc(var(--shadow-intensity)));
            {% if layout_style == 'modern' %}
            border: 1px solid {{ colors[0] }}22;
            {% elif layout_style == 'bold' %}
            border-left: 5px solid var(--primary-color);
            {% endif %}
        }
        
        .app-header {
            display: flex;
            align-items: center;
            gap: 30px;
            margin-bottom: 30px;
            flex-wrap: wrap;
            {% if hero_layout == 'center-aligned' %}
            justify-content: center;
            text-align: center;
            {% elif hero_layout == 'right-aligned' %}
            flex-direction: row-reverse;
            text-align: right;
            {% endif %}
        }
        
        .app-icon {
            width: 120px;
            height: 120px;
            border-radius: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            transition: transform var(--animation-speed);
        }
        
        .app-icon:hover {
            transform: scale(1.05);
        }
        
        .app-info h1 {
            font-size: {{ title_size }}em;
            font-weight: {{ heading_weight }};
            margin-bottom: 10px;
            color: var(--primary-color);
        }
        
        .developer {
            color: {% if dark_mode %}#999{% else %}#666{% endif %};
            font-size: 1.1em;
            margin-bottom: 15px;
        }
        
        {% if stats_style == 'cards' %}
        .stats {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }
        .stat {
            background: {{ colors[0] }}11;
            padding: 12px 20px;
            border-radius: 12px;
            border: 1px solid {{ colors[0] }}33;
        }
        {% elif stats_style == 'badges' %}
        .stats {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }
        .stat {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: linear-gradient(135deg, {{ colors[0] }}22, {{ colors[1] }}22);
            padding: 8px 16px;
            border-radius: 20px;
        }
        {% else %}
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
        {% endif %}
        
        .stat-label {
            color: {% if dark_mode %}#aaa{% else %}#999{% endif %};
            font-size: 0.9em;
        }
        
        .stat-value {
            font-weight: bold;
            color: var(--primary-color);
            font-size: 1.2em;
        }
        
        .app-meta {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid {% if dark_mode %}#333{% else %}#eee{% endif %};
        }
        
        .meta-item {
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        
        .meta-label {
            font-size: 0.85em;
            color: {% if dark_mode %}#888{% else %}#666{% endif %};
        }
        
        .meta-value {
            font-weight: 600;
            color: {% if dark_mode %}#ddd{% else %}#333{% endif %};
        }
        
        {% if button_style == 'gradient' %}
        .download-button {
            display: inline-block;
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            padding: 15px 40px;
            border-radius: {{ button_radius }};
            text-decoration: none;
            font-size: 1.2em;
            font-weight: bold;
            margin-top: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: all var(--animation-speed);
        }
        {% elif button_style == 'outline' %}
        .download-button {
            display: inline-block;
            background: transparent;
            color: var(--primary-color);
            border: 2px solid var(--primary-color);
            padding: 15px 40px;
            border-radius: {{ button_radius }};
            text-decoration: none;
            font-size: 1.2em;
            font-weight: bold;
            margin-top: 30px;
            transition: all var(--animation-speed);
        }
        .download-button:hover {
            background: var(--primary-color);
            color: white;
        }
        {% else %}
        .download-button {
            display: inline-block;
            background: var(--primary-color);
            color: white;
            padding: 15px 40px;
            border-radius: {{ button_radius }};
            text-decoration: none;
            font-size: 1.2em;
            font-weight: bold;
            margin-top: 30px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.15);
            transition: all var(--animation-speed);
        }
        {% endif %}
        
        .download-button:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.25);
        }
        
        .description {
            background: {% if dark_mode %}#1e1e1e{% else %}white{% endif %};
            padding: 30px;
            border-radius: var(--border-radius);
            margin-bottom: var(--section-spacing);
            box-shadow: 0 5px 20px rgba(0,0,0,calc(var(--shadow-intensity)));
        }
        
        .description h2 {
            color: var(--primary-color);
            margin-bottom: 15px;
            font-weight: {{ heading_weight }};
        }
        
        .description-text {
            color: {% if dark_mode %}#ccc{% else %}#555{% endif %};
            line-height: 1.8;
            white-space: pre-wrap;
        }
        
        .read-more-btn {
            color: var(--primary-color);
            cursor: pointer;
            font-weight: 600;
            margin-left: 5px;
            text-decoration: none;
        }
        
        .description-full {
            display: none;
        }
        
        .description-full.show {
            display: block;
        }
        
        .video-section {
            background: {% if dark_mode %}#1e1e1e{% else %}white{% endif %};
            padding: 30px;
            border-radius: var(--border-radius);
            margin-bottom: var(--section-spacing);
            box-shadow: 0 10px 30px rgba(0,0,0,calc(var(--shadow-intensity)));
        }
        
        .video-section h2 {
            color: var(--primary-color);
            margin-bottom: 20px;
            font-weight: {{ heading_weight }};
        }
        
        .video-wrapper {
            position: relative;
            padding-bottom: 56.25%;
            height: 0;
            overflow: hidden;
            border-radius: calc(var(--border-radius) / 2);
        }
        
        .video-wrapper iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: none;
        }
        
        .screenshots {
            background: {% if dark_mode %}#1e1e1e{% else %}white{% endif %};
            padding: 30px;
            border-radius: var(--border-radius);
            box-shadow: 0 10px 30px rgba(0,0,0,calc(var(--shadow-intensity)));
            margin-bottom: var(--section-spacing);
        }
        
        .screenshots h2 {
            color: var(--primary-color);
            margin-bottom: 20px;
            font-weight: {{ heading_weight }};
        }
        
        {% if screenshot_layout == 'carousel' %}
        .screenshot-grid {
            display: flex;
            gap: 20px;
            overflow-x: auto;
            padding-bottom: 10px;
        }
        .screenshot {
            min-width: 250px;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        {% elif screenshot_layout == 'masonry' %}
        .screenshot-grid {
            columns: 3;
            column-gap: 20px;
        }
        .screenshot {
            break-inside: avoid;
            margin-bottom: 20px;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        {% else %}
        .screenshot-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
        .screenshot {
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform var(--animation-speed);
        }
        {% endif %}
        
        .screenshot:hover {
            transform: scale(1.05);
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        
        .screenshot img {
            width: 100%;
            height: auto;
            display: block;
        }
        
        .similar-apps {
            background: {% if dark_mode %}#1e1e1e{% else %}white{% endif %};
            padding: 30px;
            border-radius: var(--border-radius);
            margin-bottom: var(--section-spacing);
            box-shadow: 0 10px 30px rgba(0,0,0,calc(var(--shadow-intensity)));
        }
        
        .similar-apps h2 {
            color: var(--primary-color);
            margin-bottom: 20px;
            font-weight: {{ heading_weight }};
        }
        
        .similar-apps-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 20px;
        }
        
        .similar-app {
            text-align: center;
            transition: transform var(--animation-speed);
        }
        
        .similar-app:hover {
            transform: translateY(-5px);
        }
        
        .similar-app-icon {
            width: 80px;
            height: 80px;
            border-radius: 20px;
            margin: 0 auto 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .similar-app-title {
            font-size: 0.9em;
            color: {% if dark_mode %}#ccc{% else %}#333{% endif %};
            margin-bottom: 5px;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }
        
        .similar-app-rating {
            font-size: 0.8em;
            color: {% if dark_mode %}#888{% else %}#666{% endif %};
        }
        
        .additional-info {
            background: {% if dark_mode %}#1e1e1e{% else %}white{% endif %};
            padding: 30px;
            border-radius: var(--border-radius);
            margin-bottom: var(--section-spacing);
            box-shadow: 0 5px 20px rgba(0,0,0,calc(var(--shadow-intensity)));
        }
        
        .additional-info h2 {
            color: var(--primary-color);
            margin-bottom: 20px;
            font-weight: {{ heading_weight }};
        }
        
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
        
        .info-item {
            padding: 15px;
            background: {% if dark_mode %}#2a2a2a{% else %}#f8f9fa{% endif %};
            border-radius: 10px;
        }
        
        .info-item-label {
            font-size: 0.9em;
            color: {% if dark_mode %}#888{% else %}#666{% endif %};
            margin-bottom: 5px;
        }
        
        .info-item-value {
            font-weight: 600;
            color: {% if dark_mode %}#ddd{% else %}#333{% endif %};
        }
        
        .badges {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 10px;
        }
        
        .badge {
            display: inline-block;
            padding: 5px 12px;
            background: var(--primary-color);
            color: white;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }
        
        .badge.warning {
            background: #ff9800;
        }
        
        footer {
            background: {% if dark_mode %}#0a0a0a{% else %}#2c3e50{% endif %};
            color: {% if dark_mode %}#ccc{% else %}white{% endif %};
            padding: 40px 0;
            margin-top: 60px;
        }
        
        .footer-content {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
            text-align: center;
        }
        
        .footer-links {
            margin-bottom: 20px;
        }
        
        .footer-links a {
            color: {% if dark_mode %}#aaa{% else %}#ecf0f1{% endif %};
            text-decoration: none;
            margin: 0 15px;
            transition: color 0.3s;
        }
        
        .footer-links a:hover {
            color: var(--primary-color);
        }
        
        .footer-copyright {
            color: {% if dark_mode %}#777{% else %}#95a5a6{% endif %};
            font-size: 0.9em;
            margin-top: 20px;
        }
        
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
            {% if screenshot_layout == 'masonry' %}
            .screenshot-grid {
                columns: 2;
            }
            {% endif %}
            .similar-apps-grid {
                grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
            }
        }
        
        @media (max-width: 480px) {
            {% if screenshot_layout == 'masonry' %}
            .screenshot-grid {
                columns: 1;
            }
            {% endif %}
            .similar-apps-grid {
                grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
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
                        <div class="stat">
                            <span class="stat-label">Reviews:</span>
                            <span class="stat-value">{{ ratings_count|default(0) }}</span>
                        </div>
                    </div>
                    
                    <div class="app-meta">
                        {% if size %}
                        <div class="meta-item">
                            <span class="meta-label">Size</span>
                            <span class="meta-value">{{ size }}</span>
                        </div>
                        {% endif %}
                        {% if version %}
                        <div class="meta-item">
                            <span class="meta-label">Version</span>
                            <span class="meta-value">{{ version }}</span>
                        </div>
                        {% endif %}
                        {% if updated %}
                        <div class="meta-item">
                            <span class="meta-label">Updated</span>
                            <span class="meta-value">{{ updated }}</span>
                        </div>
                        {% endif %}
                        {% if android_version %}
                        <div class="meta-item">
                            <span class="meta-label">Requires</span>
                            <span class="meta-value">Android {{ android_version }}+</span>
                        </div>
                        {% endif %}
                        {% if content_rating %}
                        <div class="meta-item">
                            <span class="meta-label">Content Rating</span>
                            <span class="meta-value">{{ content_rating }}</span>
                        </div>
                        {% endif %}
                    </div>
                    
                    <div class="badges">
                        {% if contains_ads %}
                        <span class="badge warning">Contains Ads</span>
                        {% endif %}
                        {% if in_app_purchases %}
                        <span class="badge warning">In-app purchases</span>
                        {% endif %}
                        {% if free %}
                        <span class="badge">Free</span>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            <a href="https://play.google.com/store/apps/details?id={{ package_name }}" 
               class="download-button" target="_blank">
                Download on Google Play
            </a>
        </div>
        
        {% for section in sections_order %}
            {% if section == 'description' and description %}
            <div class="description">
                <h2>About this app</h2>
                {% if summary %}
                <div style="font-weight: 600; margin-bottom: 15px; color: var(--primary-color);">
                    {{ summary }}
                </div>
                {% endif %}
                <div class="description-text">
                    <span class="description-short">{{ description[:500] }}{% if description|length > 500 %}...{% endif %}</span>
                    {% if description|length > 500 %}
                    <span class="description-full">{{ description }}</span>
                    <a href="#" class="read-more-btn" onclick="toggleDescription(event)">Read more</a>
                    {% endif %}
                </div>
            </div>
            {% endif %}
            
            {% if section == 'video' and video %}
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
            
            {% if section == 'screenshots' and screenshots %}
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
        {% endfor %}
        
        {% if similar_apps %}
        <div class="similar-apps">
            <h2>Similar Apps</h2>
            <div class="similar-apps-grid">
                {% for app in similar_apps %}
                <div class="similar-app">
                    {% if app.icon_local %}
                    <img src="{{ app.icon_local }}" alt="{{ app.title }}" class="similar-app-icon">
                    {% endif %}
                    <div class="similar-app-title">{{ app.title }}</div>
                    {% if app.rating %}
                    <div class="similar-app-rating">⭐ {{ app.rating }}</div>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}
        
        {% if recent_changes or developer_website or developer_email %}
        <div class="additional-info">
            <h2>Additional Information</h2>
            <div class="info-grid">
                {% if category %}
                <div class="info-item">
                    <div class="info-item-label">Category</div>
                    <div class="info-item-value">{{ category }}</div>
                </div>
                {% endif %}
                {% if developer_website %}
                <div class="info-item">
                    <div class="info-item-label">Developer Website</div>
                    <div class="info-item-value">
                        <a href="{{ developer_website }}" target="_blank" style="color: var(--primary-color);">
                            Visit Website
                        </a>
                    </div>
                </div>
                {% endif %}
                {% if developer_email %}
                <div class="info-item">
                    <div class="info-item-label">Developer Email</div>
                    <div class="info-item-value">{{ developer_email }}</div>
                </div>
                {% endif %}
                {% if installs_raw > 1000000 %}
                <div class="info-item">
                    <div class="info-item-label">Popularity</div>
                    <div class="info-item-value">Top Rated App</div>
                </div>
                {% endif %}
            </div>
            
            {% if recent_changes %}
            <div style="margin-top: 30px;">
                <h3 style="color: var(--primary-color); margin-bottom: 15px;">What's New</h3>
                <div style="white-space: pre-wrap; color: {% if dark_mode %}#ccc{% else %}#555{% endif %};">{{ recent_changes }}</div>
            </div>
            {% endif %}
        </div>
        {% endif %}
    </div>
    
    <footer>
        <div class="footer-content">
            <div class="footer-links">
                <a href="/landing/{{ landing_id }}/privacy.html">Privacy Policy</a>
                <a href="/landing/{{ landing_id }}/terms.html">Terms of Service</a>
                <a href="#" class="contact-link">Contact Us</a>
            </div>
            <div class="footer-copyright">
                © 2024 <span class="domain-text">example.com</span>. All rights reserved.<br>
                {{ title }} is a trademark of {{ developer }}.
            </div>
        </div>
    </footer>
    
    <script>
    // Динамическое определение домена
    (function() {
        var domain = window.location.hostname;
        
        // Убираем www. если есть
        if (domain.startsWith('www.')) {
            domain = domain.substring(4);
        }
        
        // Обновляем email ссылку
        var contactLink = document.querySelector('.contact-link');
        if (contactLink) {
            contactLink.href = 'mailto:mail@' + domain;
            contactLink.textContent = 'Contact Us';
        }
        
        // Обновляем текст домена в копирайте
        var domainText = document.querySelector('.domain-text');
        if (domainText) {
            domainText.textContent = domain;
        }
    })();
    
    // Функция для раскрытия описания
    function toggleDescription(e) {
        e.preventDefault();
        var shortDesc = document.querySelector('.description-short');
        var fullDesc = document.querySelector('.description-full');
        var btn = e.target;
        
        if (fullDesc.classList.contains('show')) {
            fullDesc.classList.remove('show');
            shortDesc.style.display = 'inline';
            btn.textContent = 'Read more';
        } else {
            fullDesc.classList.add('show');
            shortDesc.style.display = 'none';
            btn.textContent = 'Read less';
        }
    }
    </script>
</body>
</html>''')
        
        return template.render(**template_data)
    except Exception as e:
        logger.error(f"Error generating HTML: {str(e)}\n{traceback.format_exc()}")
        raise

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

# Остальные функции остаются без изменений (generate_privacy_policy, generate_terms_of_service, 
# create_landing_archive, Flask routes и т.д.)
