import os
import pandas as pd
import logging

from . import config, scraper, config_loader

def process_and_generate_reports(statistic_file_path, chat_file_path, soup, report_config):
    """
    Главная функция обработки данных, управляемая конфигурационным файлом.
    """
    proc_settings = report_config['processing_settings']
    
    if not statistic_file_path or not os.path.exists(statistic_file_path):
        logging.error("Файл статистики не найден. Обработка невозможна.")
        return

    logging.info(f"Начинаю обработку файла статистики: {statistic_file_path}")
    
    try:
        source_df = pd.read_excel(statistic_file_path, sheet_name=proc_settings['sheet_name'])
    except Exception as e:
        logging.error(f"Не удалось прочитать лист '{proc_settings['sheet_name']}' из '{statistic_file_path}'. Ошибка: {e}")
        return

    # Переименовываем столбцы в соответствии с картой для внутреннего использования
    inverted_map = {v: k for k, v in proc_settings['column_map'].items()}
    df = source_df.rename(columns=proc_settings['column_map'])

    # Базовая обработка
    df.drop_duplicates(subset=['first_name', 'last_name'], inplace=True, keep='first')
    df.reset_index(drop=True, inplace=True)

    # Фильтрация
    df = _filter_data(df, report_config)

    webinar_date_str = _get_webinar_date_str(df)
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    
    # Создание основных DF для отчетов
    geography_df = _create_geography_df(df, report_config)
    webinar_df = _create_webinar_df(df, geography_df, soup, report_config)
    chat_df = _create_chat_df(chat_file_path) if chat_file_path and os.path.exists(chat_file_path) else None

    # Генерация выходных файлов на основе конфига
    for report_key, report_details in report_config.get('output_files', {}).items():
        if report_details.get('enabled'):
            logging.info(f"Генерирую отчет '{report_key}'...")
            
            filename = report_details['filename_template'].format(date=webinar_date_str)
            filepath = os.path.join(config.REPORT_DIR, filename)

            if report_details.get('type') == 'attended_emails_only':
                _create_attended_emails_file(geography_df, filepath, report_config)
            else:
                _save_standard_report(filepath, report_details, geography_df, webinar_df, chat_df)
    
    logging.info("Генерация всех отчетов завершена.")


def _save_standard_report(filepath, report_details, base_geography_df, webinar_df, chat_df):
    """Сохраняет стандартный отчет с несколькими листами, как описано в конфиге."""
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        for sheet_info in report_details.get('sheets', []):
            sheet_type = sheet_info['type']
            sheet_name = sheet_info['name']

            if sheet_type == 'geography':
                geo_df = base_geography_df.copy()
                if 'drop_columns' in sheet_info:
                    # Напрямую используем имена из конфига, т.к. в geo_df они уже финальные
                    cols_to_drop = sheet_info['drop_columns']
                    geo_df.drop(columns=cols_to_drop, inplace=True, errors='ignore')
                    logging.info(f"Столбцы {cols_to_drop} удалены для отчета {os.path.basename(filepath)}.")
                
                # Возвращаем оригинальные имена столбцов для записи в Excel
                geo_df.rename(columns=geo_df.attrs['inverted_map']).to_excel(writer, sheet_name=sheet_name, index=False)
            
            elif sheet_type == 'summary':
                webinar_df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)
            
            elif sheet_type == 'chat' and chat_df is not None:
                chat_df.to_excel(writer, sheet_name=sheet_name, index=False)
    logging.info(f"Лист '{sheet_info['name']}' добавлен в отчет {os.path.basename(filepath)}.")


def _create_attended_emails_file(geography_df, filepath, report_config):
    """Создает и сохраняет файл только с email-адресами присутствовавших."""
    attended_df = geography_df[geography_df['Присутствие на вебинаре'] == 'да'].copy()

    # Динамически находим финальные имена нужных столбцов
    proc_settings = report_config.get('processing_settings', {})
    inverted_map = geography_df.attrs.get('inverted_map', {})
    rename_map = proc_settings.get('rename_map', {})

    def get_final_name(internal_name):
        source_name = inverted_map.get(internal_name)
        if source_name:
            return rename_map.get(source_name, source_name)
        return None
    
    first_name_col = get_final_name('first_name')
    last_name_col = get_final_name('last_name')
    email_col = get_final_name('email')

    required_cols = [c for c in [first_name_col, last_name_col, email_col] if c]
    
    if not attended_df.empty and all(k in attended_df.columns for k in required_cols):
        report_df = pd.DataFrame()
        report_df[0] = attended_df[first_name_col] + ' ' + attended_df[last_name_col]
        report_df[1] = attended_df[email_col]
        report_df.to_excel(filepath, index=False, header=False)
        logging.info(f"Файл с email адресами успешно сохранен: {filepath}")
    else:
        missing_cols = [col for col in required_cols if col not in attended_df.columns]
        logging.warning(f"Нет данных для создания файла {os.path.basename(filepath)}. "
                        f"Причина: DataFrame пуст или отсутствуют необходимые столбцы: {missing_cols}")


def _filter_data(df, report_config):
    """Применяет фильтры к DataFrame на основе глобального .env и конфига отчета."""
    proc_settings = report_config['processing_settings']
    
    # 1. Фильтрация по глобальному FILTER_LIST из .env
    if 'email' in df.columns and config.FILTER_LIST:
        initial_rows = len(df)
        # Email уже в нижнем регистре от config.py
        df = df[~df['email'].str.lower().isin(config.FILTER_LIST)]
        if (initial_rows - len(df)) > 0:
            logging.info(f"Отфильтровано {initial_rows - len(df)} строк по глобальному FILTER_LIST.")
    
    # 2. Фильтрация по ролям из конфига отчета
    roles_to_exclude = proc_settings.get('filter', {}).get('roles_to_exclude', [])
    if 'role' in df.columns and roles_to_exclude:
        initial_rows = len(df)
        df = df[~df['role'].isin(roles_to_exclude)]
        if (initial_rows - len(df)) > 0:
            logging.info(f"Отфильтровано {initial_rows - len(df)} строк по ролям из конфига.")
            
    return df


def _create_geography_df(df, report_config):
    """Создает DataFrame для вкладки 'география участников'."""
    proc_settings = report_config['processing_settings']
    column_map = proc_settings['column_map']
    inverted_map = {v: k for k, v in column_map.items()}

    # Создаем DataFrame, используя только те столбцы, что есть в карте
    internal_names_present = [name for name in inverted_map.keys() if name in df.columns]
    report_df = df[internal_names_present].copy()
    
    # Шаг 1: Переименовываем столбцы в их "настоящие" имена для вывода
    report_df.rename(columns=inverted_map, inplace=True)

    # Шаг 2: Применяем дополнительное, финальное переименование из конфига
    if 'rename_map' in proc_settings:
        report_df.rename(columns=proc_settings['rename_map'], inplace=True)
        logging.info("Применено дополнительное переименование столбцов.")

    # Шаг 3: Добавляем столбец присутствия
    if 'entry_time' in df.columns:
        not_attended_values = proc_settings.get('not_attended_values', [])
        report_df['Присутствие на вебинаре'] = df['entry_time'].apply(
            lambda x: 'нет' if pd.isna(x) or str(x).strip() in not_attended_values else 'да'
        )

    # Шаг 4: Применяем порядок столбцов из конфига, если он задан, и отфильтровываем лишние
    defined_order = proc_settings.get('geography_column_order')
    if defined_order:
        # Отфильтровываем report_df, чтобы он содержал только столбцы из defined_order,
        # которые фактически присутствуют в DataFrame, в указанном порядке.
        final_column_order = [col for col in defined_order if col in report_df.columns]
        report_df = report_df[final_column_order]
        logging.info("Порядок столбцов для 'географии' применен из конфигурации и нежелательные столбцы отфильтрованы.")
    else:
        logging.warning("geography_column_order не определен в конфиге. Отчет 'география' может содержать непредсказуемый порядок столбцов.")

    # Сохраняем карты для последующего использования
    report_df.attrs['column_map'] = column_map
    report_df.attrs['inverted_map'] = inverted_map

    return report_df


def _create_webinar_df(df, geography_df, soup, report_config):
    """Создает DataFrame для сводной вкладки 'вебинар'."""
    start_time = pd.to_datetime(df['start_time'].dropna().iloc[0]) if 'start_time' in df.columns and not df['start_time'].dropna().empty else None
    end_time = pd.to_datetime(df['end_time'].dropna().iloc[0]) if 'end_time' in df.columns and not df['end_time'].dropna().empty else None
    
    date_str = start_time.strftime('%d.%m.%y %H:%M по Мск') if start_time else "Нет данных"
    duration_str = _calculate_duration(start_time, end_time)
    topic = df['webinar_topic'].dropna().iloc[0] if 'webinar_topic' in df.columns and not df['webinar_topic'].dropna().empty else "Нет данных"
    presenter = scraper.scrape_presenter(soup, report_config)
    
    registered = len(geography_df)
    attended_count = len(geography_df[geography_df['Присутствие на вебинаре'] == 'да'])
    not_attended = registered - attended_count
    attendance_percentage = f"{round((attended_count / registered * 100), 1)}%" if registered > 0 else "0.0%"
    new_emails = scraper.scrape_new_emails(soup, report_config)

    report_data = [
        ["дата проведения", date_str, None, None],
        ["продолжительность", duration_str, None, None],
        ["тема", topic, None, None],
        ["ведущий", presenter, None, None],
        ["зарегистрировались на вебинар (C)", registered, None, None],
        ["приняли участие (A)", attended_count, attendance_percentage, "явка"],
        ["не посетили вебинар (B)", not_attended, None, None],
        ["новые e-mail адреса в базу подписчиков", new_emails, None, None],
        ["регионы продвижения", "", None, None],
        ["организаторы и ответственные лица", "", None, None]
    ]
    return pd.DataFrame(report_data, columns=["Параметр", "Значение", "Посещаемость %", "Статус"])


def _create_chat_df(chat_file_path):
    """Создает DataFrame для вкладки 'чат'."""
    try:
        logging.info(f"Читаю файл чата: {chat_file_path}")
        return pd.read_excel(chat_file_path, sheet_name='Сообщения чата')
    except Exception as e:
        logging.error(f"Не удалось прочитать файл чата '{chat_file_path}'. Ошибка: {e}")
        return None


def _get_webinar_date_str(df):
    """Извлекает и форматирует дату вебинара."""
    if 'event_date' in df.columns and not df['event_date'].dropna().empty:
        try:
            date_val = df['event_date'].dropna().iloc[0]
            return pd.to_datetime(date_val).strftime('%Y-%m-%d')
        except (IndexError, TypeError): pass
    logging.warning("Дата вебинара не найдена, используется сегодняшняя дата.")
    return pd.Timestamp.now().strftime('%Y-%m-%d')


def _calculate_duration(start, end):
    """Вычисляет продолжительность."""
    if pd.isna(start) or pd.isna(end): return "Нет данных"
    total_minutes = int((end - start).total_seconds() / 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours} час {minutes} минут"