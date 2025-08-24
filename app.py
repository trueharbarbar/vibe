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
ARCHIVES_DIR = os.path.join(STATIC_DIR, 'archives')
LEGAL_DIR = os.path.join(STATIC_DIR, 'legal')

# Создаем необходимые директории
for directory in [LANDINGS_DIR, IMAGES_DIR, ARCHIVES_DIR, LEGAL_DIR]:
    os.makedirs(directory, exist_ok=True)

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

def vary_color(hex_color, variation=0.15):
    """Варьирование цвета для создания уникальности"""
    # Конвертируем hex в RGB
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    # Конвертируем в HSV
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    
    # Варьируем оттенок, насыщенность и яркость
    h = (h + random.uniform(-variation, variation)) % 1
    s = max(0, min(1, s + random.uniform(-variation/2, variation/2)))
    v = max(0.3, min(1, v + random.uniform(-variation/2, variation/2)))
    
    # Обратно в RGB
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    
    # Обратно в hex
    return '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b*255))

def extract_dominant_colors(image_path, num_colors=3):
    """Извлечение доминирующих цветов из изображения"""
    try:
        color_thief = ColorThief(image_path)
        palette = color_thief.get_palette(color_count=num_colors, quality=1)
        
        colors = []
        for rgb in palette[:num_colors]:
            hex_color = '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
            # Добавляем вариацию к извлеченным цветам
            colors.append(vary_color(hex_color, 0.1))
        
        # Заполняем недостающие цвета дефолтными с вариацией
        default_colors = ['#4285f4', '#34a853', '#fbbc04']
        while len(colors) < 3:
            colors.append(vary_color(random.choice(default_colors)))
        
        return colors
    except Exception as e:
        logger.error(f"Failed to extract colors: {str(e)}")
        # Возвращаем варьированные дефолтные цвета
        return [vary_color(c) for c in ['#4285f4', '#34a853', '#fbbc04']]

def generate_landing_id(package_name, language):
    """Генерация уникального ID для лендинга"""
    # Добавляем случайную компоненту для уникальности
    content = f"{package_name}_{language}_{datetime.now().isoformat()}_{random.randint(1000, 9999)}"
    return hashlib.md5(content.encode()).hexdigest()[:12]

def get_domain_from_url(url):
    """Извлечение домена из URL"""
    parsed = urlparse(url)
    return parsed.netloc or 'localhost'

def generate_randomization_params():
    """Генерация параметров для рандомизации дизайна"""
    params = {
        # Layouts - различные варианты расположения элементов
        'layout_style': random.choice(['classic', 'modern', 'minimal', 'bold', 'elegant']),
        'hero_layout': random.choice(['left-aligned', 'center-aligned', 'right-aligned']),
        'screenshot_layout': random.choice(['grid', 'carousel', 'masonry', 'staggered']),
        
        # Typography variations
        'font_family': random.choice([
            '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, sans-serif',
            '"SF Pro Display", -apple-system, BlinkMacSystemFont, sans-serif',
            'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
            '"Google Sans", Roboto, Arial, sans-serif',
            'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
        ]),
        'heading_weight': random.choice(['600', '700', '800', '900']),
        'title_size': random.uniform(2.2, 3.0),
        
        # Spacing and sizing
        'container_padding': random.randint(20, 40),
        'section_spacing': random.randint(30, 50),
        'border_radius': random.randint(10, 25),
        'button_radius': random.choice(['50px', '15px', '25px', '10px']),
        
        # Visual effects
        'shadow_intensity': random.uniform(0.05, 0.2),
        'gradient_angle': random.randint(90, 180),
        'gradient_stops': random.choice(['0%, 100%', '0%, 50%, 100%', '20%, 80%']),
        'animation_speed': random.uniform(0.2, 0.5),
        
        # Color variations
        'use_gradient_bg': random.choice([True, False]),
        'dark_mode': random.choice([False, False, False, True]),  # 25% chance for dark mode
        'accent_usage': random.choice(['subtle', 'moderate', 'bold']),
        
        # Component variations
        'stats_style': random.choice(['inline', 'cards', 'badges']),
        'button_style': random.choice(['solid', 'gradient', 'outline-glow']),
        'description_style': random.choice(['card', 'transparent', 'bordered']),
        
        # Order variations
        'sections_order': random.sample(['description', 'video', 'screenshots'], 3)
    }
    
    return params

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
                processed_data['colors'] = [vary_color(c) for c in ['#4285f4', '#34a853', '#fbbc04']]
        
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

def generate_html(app_data, landing_id, domain):
    """Генерация HTML страницы лендинга с рандомизацией"""
    
    # Генерируем параметры рандомизации
    r = generate_randomization_params()
    
    # Добавляем domain в данные
    app_data['domain'] = domain
    app_data['landing_id'] = landing_id
    
    # Объединяем все параметры
    template_data = {**app_data, **r}
    
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
                {{ colors[0] }}22 {{ gradient_stops.split(',')[0] }}, 
                {{ colors[1] }}22 {{ gradient_stops.split(',')[-1] }});
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
            width: {{ 100 + random.randint(0, 40) }}px;
            height: {{ 100 + random.randint(0, 40) }}px;
            border-radius: {{ random.choice([20, 25, 30, 50]) }}%;
            box-shadow: 0 10px 30px rgba(0,0,0,calc(var(--shadow-intensity) * 1.5));
            transition: transform var(--animation-speed);
        }
        
        .app-icon:hover {
            transform: scale(1.05) rotate({{ random.choice([-2, 0, 2]) }}deg);
        }
        
        .app-info h1 {
            font-size: {{ title_size }}em;
            font-weight: {{ heading_weight }};
            margin-bottom: 10px;
            color: var(--primary-color);
            {% if layout_style == 'elegant' %}
            letter-spacing: -0.02em;
            {% endif %}
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
        {% elif button_style == 'outline-glow' %}
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
            position: relative;
        }
        
        .download-button:hover {
            background: var(--primary-color);
            color: white;
            box-shadow: 0 0 30px var(--primary-color);
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
        
        {% if description_style == 'card' %}
        .description {
            background: {% if dark_mode %}#1e1e1e{% else %}white{% endif %};
            padding: 30px;
            border-radius: var(--border-radius);
            margin-bottom: var(--section-spacing);
            box-shadow: 0 5px 20px rgba(0,0,0,calc(var(--shadow-intensity)));
        }
        {% elif description_style == 'bordered' %}
        .description {
            background: {% if dark_mode %}#1a1a1a{% else %}#fafafa{% endif %};
            padding: 30px;
            border-radius: var(--border-radius);
            margin-bottom: var(--section-spacing);
            border: 2px solid {{ colors[0] }}33;
        }
        {% else %}
        .description {
            background: {{ colors[0] }}08;
            padding: 30px;
            border-radius: var(--border-radius);
            margin-bottom: var(--section-spacing);
        }
        {% endif %}
        
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
        {% elif screenshot_layout == 'staggered' %}
        .screenshot-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
        
        .screenshot:nth-child(odd) {
            transform: translateY(10px);
        }
        
        .screenshot {
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform var(--animation-speed);
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
                <a href="/legal/privacy/{{ landing_id }}.html">Privacy Policy</a>
                <a href="/legal/terms/{{ landing_id }}.html">Terms of Service</a>
                <a href="mailto:mail@{{ domain }}">Contact Us</a>
            </div>
            <div class="footer-copyright">
                © 2024 {{ domain }}. All rights reserved.<br>
                {{ title }} is a trademark of {{ developer }}.
            </div>
        </div>
    </footer>
</body>
</html>''')
    
    return template.render(**template_data)

def generate_privacy_policy(app_title, domain):
    """Генерация политики конфиденциальности"""
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
        <p>Welcome to {app_title}. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our mobile application. Please read this privacy policy carefully.</p>
        
        <h2>Information We Collect</h2>
        <p>We may collect information about you in a variety of ways. The information we may collect via the Application includes:</p>
        <ul>
            <li><strong>Personal Data:</strong> Demographic and other personally identifiable information that you voluntarily give to us when choosing to participate in various activities related to the Application.</li>
            <li><strong>Derivative Data:</strong> Information our servers automatically collect when you access the Application, such as your native actions that are integral to the Application.</li>
            <li><strong>Mobile Device Access:</strong> We may request access or permission to certain features from your mobile device.</li>
        </ul>
        
        <h2>Use of Your Information</h2>
        <p>We may use information collected about you via the Application to:</p>
        <ul>
            <li>Create and manage your account</li>
            <li>Email you regarding your account or order</li>
            <li>Fulfill and manage purchases, orders, payments, and other transactions</li>
            <li>Generate a personal profile about you</li>
            <li>Increase the efficiency and operation of the Application</li>
            <li>Monitor and analyze usage and trends</li>
            <li>Notify you of updates to the Application</li>
        </ul>
        
        <h2>Disclosure of Your Information</h2>
        <p>We may share information we have collected about you in certain situations:</p>
        <ul>
            <li><strong>By Law or to Protect Rights:</strong> If we believe the release of information is necessary to respond to legal process</li>
            <li><strong>Third-Party Service Providers:</strong> We may share your information with third parties that perform services for us</li>
            <li><strong>Marketing Communications:</strong> With your consent, we may share your information with third parties for marketing purposes</li>
        </ul>
        
        <h2>Security of Your Information</h2>
        <p>We use administrative, technical, and physical security measures to help protect your personal information. While we have taken reasonable steps to secure the personal information you provide to us, please be aware that despite our efforts, no security measures are perfect or impenetrable.</p>
        
        <h2>Contact Us</h2>
        <p>If you have questions or comments about this Privacy Policy, please contact us at:</p>
        <p>Email: <a href="mailto:privacy@{domain}">privacy@{domain}</a></p>
        <p>Website: <a href="http://{domain}">{domain}</a></p>
    </div>
</body>
</html>'''

def generate_terms_of_service(app_title, domain):
    """Генерация пользовательского соглашения"""
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
        <h1>Terms of Service</h1>
        <p class="date">Effective Date: {datetime.now().strftime('%B %d, %Y')}</p>
        
        <h2>Agreement to Terms</h2>
        <p>These Terms of Service constitute a legally binding agreement made between you and {domain} concerning your access to and use of the {app_title} application.</p>
        
        <h2>Intellectual Property Rights</h2>
        <p>Unless otherwise indicated, the Application is our proprietary property and all source code, databases, functionality, software, designs, audio, video, text, photographs, and graphics on the Application are owned or controlled by us.</p>
        
        <h2>User Representations</h2>
        <p>By using the Application, you represent and warrant that:</p>
        <ul>
            <li>You have the legal capacity and you agree to comply with these Terms of Service</li>
            <li>You are not under the age of 13</li>
            <li>You will not access the Application through automated or non-human means</li>
            <li>You will not use the Application for any illegal or unauthorized purpose</li>
        </ul>
        
        <h2>Prohibited Activities</h2>
        <p>You may not access or use the Application for any purpose other than that for which we make the Application available. The Application may not be used in connection with any commercial endeavors except those that are specifically endorsed or approved by us.</p>
        
        <h2>Contribution License</h2>
        <p>You and the Application agree that we may access, store, process, and use any information and personal data that you provide following the terms of the Privacy Policy and your choices.</p>
        
        <h2>Privacy Policy</h2>
        <p>We care about data privacy and security. Please review our <a href="/legal/privacy/{domain}.html">Privacy Policy</a>.</p>
        
        <h2>Termination</h2>
        <p>These Terms of Service remain in full force and effect while you use the Application. We reserve the right to deny access to and use of the Application.</p>
        
        <h2>Disclaimer</h2>
        <p>THE APPLICATION IS PROVIDED ON AN AS-IS AND AS-AVAILABLE BASIS. YOU AGREE THAT YOUR USE OF THE APPLICATION WILL BE AT YOUR SOLE RISK.</p>
        
        <h2>Limitation of Liability</h2>
        <p>IN NO EVENT WILL WE OR OUR DIRECTORS, EMPLOYEES, OR AGENTS BE LIABLE TO YOU OR ANY THIRD PARTY FOR ANY DIRECT, INDIRECT, CONSEQUENTIAL, EXEMPLARY, INCIDENTAL, SPECIAL, OR PUNITIVE DAMAGES.</p>
        
        <h2>Governing Law</h2>
        <p>These Terms shall be governed by and defined following the laws of the country where {domain} is registered.</p>
        
        <h2>Contact Information</h2>
        <p>If you have any questions about these Terms of Service, please contact us at:</p>
        <p>Email: <a href="mailto:legal@{domain}">legal@{domain}</a></p>
        <p>Website: <a href="http://{domain}">{domain}</a></p>
    </div>
</body>
</html>'''
