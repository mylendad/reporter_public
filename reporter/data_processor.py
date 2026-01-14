import os
import pandas as pd
import logging

from . import config
from . import scraper

def process_and_generate_reports(statistic_file_path, chat_file_path, soup):
    """
    Обрабатывает скачанные файлы и создает итоговые отчеты.
    :param statistic_file_path: Путь к файлу статистики.
    :param chat_file_path: Путь к файлу чата.
    :param soup: Объект BeautifulSoup для скрапинга данных со страницы.
    """
    if not statistic_file_path or not os.path.exists(statistic_file_path):
        logging.error("Файл статистики не найден. Обработка невозможна.")
        return

    logging.info(f"Начинаю обработку файла статистики: {statistic_file_path}")
    
    try:
        source_df = pd.read_excel(statistic_file_path, sheet_name=config.REPORT_SHEET_NAME)
    except Exception as e:
        logging.error(f"Не удалось прочитать лист '{config.REPORT_SHEET_NAME}' из файла '{statistic_file_path}'. Ошибка: {e}")
        return

    source_df.drop_duplicates(subset=['Имя', 'Фамилия'], inplace=True, keep='first')
    source_df.reset_index(drop=True, inplace=True)

    # Фильтрация данных
    source_df = _filter_data(source_df)

    webinar_date_str = _get_webinar_date_str(source_df)
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    
    report_filename = f"Отчет по вебинару {webinar_date_str}.xlsx"
    report_filepath = os.path.join(config.REPORT_DIR, report_filename)

    # Создаем DataFrames для всех листов
    geography_df = _create_geography_df(source_df)
    webinar_df = _create_webinar_df(source_df, geography_df, soup)
    chat_df = _create_chat_df(chat_file_path) if chat_file_path and os.path.exists(chat_file_path) else None

    # 1. Сохранение основного отчета
    _save_report(report_filepath, geography_df, webinar_df, chat_df)
    logging.info(f"Основной отчет успешно сохранен: {report_filepath}")

    # 2. Создание файла для рассылки
    rasylka_filename = f"Рассылка {webinar_date_str}.xlsx"
    rasylka_filepath = os.path.join(config.REPORT_DIR, rasylka_filename)
    rasylka_geography_df = geography_df.copy()
    if "Откуда узнали" in rasylka_geography_df.columns:
        rasylka_geography_df = rasylka_geography_df.drop(columns=["Откуда узнали"])
    _save_report(rasylka_filepath, rasylka_geography_df, webinar_df, chat_df)
    logging.info(f"Файл для рассылки успешно сохранен: {rasylka_filepath}")

    # 3. Создание файла "data1.xlsx"
    _create_data1_file(geography_df, webinar_date_str)


def _filter_data(df):
    """Применяет фильтры к DataFrame."""
    # Фильтрация по email
    if 'Email' in df.columns and config.FILTER_LIST:
        initial_rows = len(df)
        df['Email_lower'] = df['Email'].str.lower()
        df = df[~df['Email_lower'].isin(config.FILTER_LIST)]
        df = df.drop(columns=['Email_lower'])
        filtered_rows = initial_rows - len(df)
        if filtered_rows > 0:
            logging.info(f"Отфильтровано {filtered_rows} строк по списку FILTER_LIST.")
    
    # Фильтрация по роли
    if 'Роль' in df.columns:
        initial_rows = len(df)
        df = df[~df['Роль'].isin(['Администратор', 'Ведущий'])]
        filtered_rows = initial_rows - len(df)
        if filtered_rows > 0:
            logging.info(f"Отфильтровано {filtered_rows} строк по роли 'Администратор' или 'Ведущий'.")
            
    return df

def _save_report(filepath, geography_df, webinar_df, chat_df):
    """Сохраняет один Excel файл с несколькими листами."""
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        geography_df.to_excel(writer, sheet_name='география участников', index=False)
        webinar_df.to_excel(writer, sheet_name='вебинар', index=False, header=False)
        if chat_df is not None:
            chat_df.to_excel(writer, sheet_name='чат', index=False)

def _create_data1_file(geography_df, webinar_date_str):
    """Создает и сохраняет файл data1.xlsx."""
    data1_filename = "data1.xlsx"
    data1_filepath = os.path.join(config.REPORT_DIR, data1_filename)

    attended_df = geography_df[geography_df['Присутствие на вебинаре'] == 'да'].copy()
    
    data1_df = pd.DataFrame()
    if 'Имя' in attended_df.columns and 'Фамилия' in attended_df.columns:
        data1_df[0] = attended_df['Имя'] + ' ' + attended_df['Фамилия']
    if 'Почта' in attended_df.columns:
        data1_df[1] = attended_df['Почта']

    if not data1_df.empty:
        data1_df.to_excel(data1_filepath, index=False, header=False)
        logging.info(f"Файл data1.xlsx успешно сохранен: {data1_filepath}")
    else:
        logging.warning("Нет данных для создания файла data1.xlsx.")

def _create_webinar_df(source_df, geography_df, soup):
    """Создает DataFrame для вкладки 'вебинар'."""
    start_time = pd.to_datetime(source_df['Время старта мероприятия'].dropna().iloc[0]) if 'Время старта мероприятия' in source_df.columns and not source_df['Время старта мероприятия'].dropna().empty else None
    end_time = pd.to_datetime(source_df['Время завершения мероприятия'].dropna().iloc[0]) if 'Время завершения мероприятия' in source_df.columns and not source_df['Время завершения мероприятия'].dropna().empty else None
    
    date_str = start_time.strftime('%d.%m.%y %H:%M по Мск') if start_time else "Нет данных"
    duration_str = _calculate_duration(start_time, end_time)
    topic = source_df['Вебинар'].dropna().iloc[0] if 'Вебинар' in source_df.columns and not source_df['Вебинар'].dropna().empty else "Нет данных"
    presenter = scraper.scrape_presenter(soup)
    
    registered = len(geography_df)
    attended_count = len(geography_df[geography_df['Присутствие на вебинаре'] == 'да'])
    not_attended = registered - attended_count
    attendance_percentage = f"{round((attended_count / registered * 100), 1)}%" if registered > 0 else "0.0%"
    new_emails = scraper.scrape_new_emails(soup)

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

def _create_geography_df(source_df):
    """Создает DataFrame для вкладки 'география участников'."""
    report_df = pd.DataFrame()
    col_map = {"Имя": "Имя", "Фамилия": "Фамилия", "Email": "Почта", "Регион": "Регион", "Город": "Город"}
    for source_col, target_col in col_map.items():
        if source_col in source_df.columns:
            report_df[target_col] = source_df[source_col]
        else:
            logging.warning(f"Столбец '{source_col}' не найден.")

    if 'Время входа' in source_df.columns:
        report_df['Присутствие на вебинаре'] = source_df['Время входа'].apply(
            lambda x: 'нет' if pd.isna(x) or str(x).strip() in ['', 'Не посетил'] else 'да'
        )
    else:
        logging.warning("Столбец 'Время входа' не найден.")
    
    source_col_origin = "Откуда вы о нас узнали?"
    if source_col_origin in source_df.columns:
        report_df["Откуда узнали"] = source_df[source_col_origin]
    else:
        logging.warning(f"Столбец '{source_col_origin}' не найден.")
    
    return report_df

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
    if 'Дата проведения' in df.columns and not df['Дата проведения'].dropna().empty:
        try:
            date_val = df['Дата проведения'].dropna().iloc[0]
            return pd.to_datetime(date_val).strftime('%Y-%m-%d')
        except (IndexError, TypeError):
            pass
    logging.warning("Дата вебинара не найдена, используется сегодняшняя дата.")
    return pd.Timestamp.now().strftime('%Y-%m-%d')

def _calculate_duration(start, end):
    """Вычисляет продолжительность."""
    if pd.isna(start) or pd.isna(end):
        return "Нет данных"
    duration = end - start
    total_minutes = int(duration.total_seconds() / 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours} час {minutes} минут"
