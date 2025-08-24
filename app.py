# ... (начало скрипта app.py без изменений) ...

# 3. Основной маршрут для генерации лендинга
@app.route('/generate-landing', methods=['POST'])
def generate_landing():
    # ... (код для получения packageName и language) ...

    try:
        # 4. Получаем информацию о приложении из Google Play
        app_details = gp_app(package_name, lang=language, country='US')
        
        # 5. Извлекаем цвета из иконки приложения
        primary_color, secondary_color = get_palette_from_url(app_details['icon'])

        # 6. Готовим данные для шаблона (РАСШИРЕННАЯ ВЕРСИЯ)
        context = {
            'lang': language,
            'title': app_details['title'],
            'developer': app_details['developer'],
            'icon_url': app_details['icon'],
            'cover_image': app_details.get('cover', app_details['screenshots'][0]), # Фон = обложка, или первый скриншот
            'screenshots': app_details['screenshots'],
            'description': app_details['description'],
            'store_url': app_details['url'],
            'rating': f"{app_details.get('score', 0):.1f}", # Рейтинг с одним знаком после запятой
            'downloads': app_details.get('realInstalls', 0), # Точное число установок
            'video_url': app_details.get('video', '').replace('watch?v=', 'embed/'), # Преобразуем ссылку YT для встраивания
            'primary_color': primary_color,
            'secondary_color': secondary_color
        }

        # ... (остальной код для рендеринга и отправки без изменений) ...
        template = env.get_template('template.html')
        html_output = template.render(context)
        
        return html_output, 200, {'Content-Type': 'text/html; charset=utf-8'}

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ... (конец скрипта) ...