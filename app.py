import os
import json
import logging
import hashlib
import requests
from flask import Flask, request, jsonify, send_from_directory, abort, send_file
from google_play_scraper import app as play_scraper
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
        
        processed_data = {
            'title': app_data.get('title', 'Unknown App'),
            'developer': app_data.get('developer', 'Unknown Developer'),
            'description': app_data.get('description', ''),
            'rating': round(app_data.get('score', 0), 1) if app_data.get('score') else 0,
            'installs': format_installs(app_data.get('minInstalls', 0)),
            'package_name': package_name,
            'language': language,
            'colors': ['#4285f4', '#34a853', '#fbbc04'],
            'icon': None,
            'cover': None,
            'screenshots': [],
            'video': None
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
        
        # Скачиваем скриншоты
        screenshots = []
        if app_data.get('screenshots'):
            for i, screenshot_url in enumerate(app_data['screenshots'][:6]):
                screenshot_path = os.path.join(app_images_dir, f'screenshot_{i}.jpg')
                if download_image(screenshot_url, screenshot_path):
                    screenshots.append(f'screenshot_{i}.jpg')
        processed_data['screenshots'] = screenshots
        
        # Обрабатываем видео
        if app_data.get('video'):
            processed_data['video'] = get_youtube_embed_url(app_data['video'])
        
        logger.info(f"Successfully processed app data for {package_name}")
        return processed_data
        
    except Exception as e:
        logger.error(f"Failed to process app data: {str(e)}\n{traceback.format_exc()}")
        return None

def generate_html(app_data, landing_id):
    """Генерация HTML страницы лендинга с рандомизацией и JS для динамического домена"""
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
        }
        
        @media (max-width: 480px) {
            {% if screenshot_layout == 'masonry' %}
            .screenshot-grid {
                columns: 1;
            }
            {% endif %}
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
        
        {% for section in sections_order %}
            {% if section == 'description' and description %}
            <div class="description">
                <h2>About this app</h2>
                <div class="description-text">{{ description[:1000] }}{% if description|length > 1000 %}...{% endif %}</div>
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
    </script>
</body>
</html>''')
        
        return template.render(**template_data)
    except Exception as e:
        logger.error(f"Error generating HTML: {str(e)}\n{traceback.format_exc()}")
        raise

def generate_privacy_policy(app_title):
    """Генерация политики конфиденциальности с JS для динамического домена"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy - {app_title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
        .date {{
            color: #7f8c8d;
            font-style: italic;
        }}
        a {{
            color: #3498db;
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Privacy Policy</h1>
        <p class="date">Last updated: {datetime.now().strftime('%B %d, %Y')}</p>
        
        <h2>Introduction</h2>
        <p>Welcome to {app_title}. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our mobile application.</p>
        
        <h2>Information We Collect</h2>
        <p>We may collect information about you in a variety of ways:</p>
        <ul>
            <li><strong>Personal Data:</strong> Information that you voluntarily provide to us</li>
            <li><strong>Usage Data:</strong> Information our servers automatically collect</li>
            <li><strong>Device Data:</strong> Information about your mobile device</li>
        </ul>
        
        <h2>Contact Us</h2>
        <p>If you have questions about this Privacy Policy, please contact us at:</p>
        <p>
            Email: <a href="#" class="email-link">mail@example.com</a><br>
            Website: <a href="#" class="website-link">example.com</a>
        </p>
    </div>
    
    <script>
    (function() {{
        var domain = window.location.hostname;
        if (domain.startsWith('www.')) {{
            domain = domain.substring(4);
        }}
        
        var emailLink = document.querySelector('.email-link');
        if (emailLink) {{
            emailLink.href = 'mailto:privacy@' + domain;
            emailLink.textContent = 'privacy@' + domain;
        }}
        
        var websiteLink = document.querySelector('.website-link');
        if (websiteLink) {{
            websiteLink.href = 'https://' + domain;
            websiteLink.textContent = domain;
        }}
    }})();
    </script>
</body>
</html>'''

def generate_terms_of_service(app_title):
    """Генерация пользовательского соглашения с JS для динамического домена"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terms of Service - {app_title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Terms of Service</h1>
        <p>Effective Date: {datetime.now().strftime('%B %d, %Y')}</p>
        
        <h2>Agreement to Terms</h2>
        <p>These Terms of Service constitute a legally binding agreement made between you and <span class="domain-text">example.com</span>.</p>
        
        <h2>Contact Information</h2>
        <p>If you have any questions about these Terms of Service, please contact us at:</p>
        <p>
            Email: <a href="#" class="email-link">mail@example.com</a><br>
            Website: <a href="#" class="website-link">example.com</a>
        </p>
    </div>
    
    <script>
    (function() {{
        var domain = window.location.hostname;
        if (domain.startsWith('www.')) {{
            domain = domain.substring(4);
        }}
        
        var domainTexts = document.querySelectorAll('.domain-text');
        domainTexts.forEach(function(el) {{
            el.textContent = domain;
        }});
        
        var emailLink = document.querySelector('.email-link');
        if (emailLink) {{
            emailLink.href = 'mailto:legal@' + domain;
            emailLink.textContent = 'legal@' + domain;
        }}
        
        var websiteLink = document.querySelector('.website-link');
        if (websiteLink) {{
            websiteLink.href = 'https://' + domain;
            websiteLink.textContent = domain;
        }}
    }})();
    </script>
</body>
</html>'''

def create_landing_archive(landing_dir, landing_id):
    """Создание ZIP архива с лендингом и всеми ресурсами"""
    try:
        archive_path = os.path.join(ARCHIVES_DIR, f"{landing_id}.zip")
        
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(landing_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, landing_dir)
                    zipf.write(file_path, arcname)
        
        return archive_path
    except Exception as e:
        logger.error(f"Failed to create archive: {str(e)}")
        return None

@app.route('/', methods=['GET'])
def index():
    """Главная страница"""
    return jsonify({
        'status': 'Landing Generator API is working!',
        'endpoints': {
            'POST /generate-landing': 'Generate landing page',
            'GET /health': 'Health check',
            'GET /config': 'Get configuration'
        }
    }), 200

@app.route('/generate-landing', methods=['POST'])
def generate_landing():
    """API endpoint для генерации лендинга"""
    try:
        data = request.get_json()
        
        if not data or 'packageName' not in data:
            error_msg = "Missing packageName in request"
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 400
        
        package_name = data['packageName']
        language = data.get('language', 'en')
        
        logger.info(f"Received request for {package_name} in {language}")
        
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
            'language': language
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
    """Скачивание ZIP архива"""
    try:
        return send_from_directory(ARCHIVES_DIR, filename)
    except:
        abort(404)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
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
