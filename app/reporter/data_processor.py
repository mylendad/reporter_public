import os
import pandas as pd
import logging
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from . import config, scraper, config_loader

def process_and_generate_reports(statistic_file_path: str, chat_file_path: Optional[str], soup: BeautifulSoup, report_config: Dict[str, Any]) -> None:
    """
    Главная функция обработки данных и генерации отчетов, управляемая конфигурационным файлом.
    Осуществляет чтение исходных файлов, базовую очистку, фильтрацию и создание различных отчетов.

    :param statistic_file_path: Путь к файлу Excel со статистикой вебинара.
    :param chat_file_path: Опциональный путь к файлу Excel с данными чата.
    :param soup: Объект BeautifulSoup, содержащий HTML страницы для скрапинга дополнительных данных.
    :param report_config: Загруженный объект конфигурации отчета.
    """
    proc_settings: Dict[str, Any] = report_config['processing_settings']
    
    if not statistic_file_path or not os.path.exists(statistic_file_path):
        logging.error("Файл статистики не найден. Обработка невозможна.")
        return

    logging.info(f"Начинаю обработку файла статистики: {statistic_file_path}")
    
    try:
        source_df: pd.DataFrame = pd.read_excel(statistic_file_path, sheet_name=proc_settings['sheet_name'])
    except Exception as e:
        logging.error(f"Не удалось прочитать лист '{proc_settings['sheet_name']}' из '{statistic_file_path}'. Ошибка: {e}")
        return

    # Переименовываем столбцы в соответствии с картой для внутреннего использования
    inverted_map: Dict[str, str] = {v: k for k, v in proc_settings['column_map'].items()}
    df: pd.DataFrame = source_df.rename(columns=proc_settings['column_map'])

    # Базовая обработка
    df.drop_duplicates(subset=['first_name', 'last_name'], inplace=True, keep='first')
    df.reset_index(drop=True, inplace=True)

    # Фильтрация
    df = _filter_data(df, report_config)

    webinar_date_str: str = _get_webinar_date_str(df)
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    
    # Создание основных DF для отчетов
    geography_df: pd.DataFrame = _create_geography_df(df, report_config)
    webinar_df: pd.DataFrame = _create_webinar_df(df, geography_df, soup, report_config)
    chat_df: Optional[pd.DataFrame] = _create_chat_df(chat_file_path) if chat_file_path and os.path.exists(chat_file_path) else None

    # Генерация выходных файлов на основе конфига
    for report_key, report_details in report_config.get('output_files', {}).items():
        if report_details.get('enabled'):
            logging.info(f"Генерирую отчет '{report_key}'...")
            
            filename: str = report_details['filename_template'].format(date=webinar_date_str)
            filepath: str = os.path.join(config.REPORT_DIR, filename)

            if report_details.get('type') == 'attended_emails_only':
                _create_attended_emails_file(geography_df, filepath, report_config)
            else:
                _save_standard_report(filepath, report_details, geography_df, webinar_df, chat_df)
    
    logging.info("Генерация всех отчетов завершена.")


def _save_standard_report(filepath: str, report_details: Dict[str, Any], base_geography_df: pd.DataFrame, webinar_df: pd.DataFrame, chat_df: Optional[pd.DataFrame]) -> None:
    """
    Сохраняет стандартный отчет в формате Excel с несколькими листами,
    структура которых описывается в конфигурационном файле.

    :param filepath: Полный путь, по которому будет сохранен файл отчета.
    :param report_details: Детали отчета из конфигурации, включающие информацию о листах.
    :param base_geography_df: DataFrame с географическими данными участников.
    :param webinar_df: DataFrame со сводной информацией о вебинаре.
    :param chat_df: Опциональный DataFrame с данными чата.
    """
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        for sheet_info in report_details.get('sheets', []):
            sheet_type: str = sheet_info['type']
            sheet_name: str = sheet_info['name']

            if sheet_type == 'geography':
                geo_df: pd.DataFrame = base_geography_df.copy()
                if 'drop_columns' in sheet_info:
                    # Напрямую используем имена из конфига, т.к. в geo_df они уже финальные
                    cols_to_drop: List[str] = sheet_info['drop_columns']
                    geo_df.drop(columns=cols_to_drop, inplace=True, errors='ignore')
                    logging.info(f"Столбцы {cols_to_drop} удалены для отчета {os.path.basename(filepath)}.")
                
                # Возвращаем оригинальные имена столбцов для записи в Excel
                geo_df.rename(columns=geo_df.attrs['inverted_map']).to_excel(writer, sheet_name=sheet_name, index=False)
            
            elif sheet_type == 'summary':
                webinar_df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)
            
            elif sheet_type == 'chat' and chat_df is not None:
                chat_df.to_excel(writer, sheet_name=sheet_name, index=False)
    logging.info(f"Лист '{sheet_info['name']}' добавлен в отчет {os.path.basename(filepath)}.")


def _create_attended_emails_file(geography_df: pd.DataFrame, filepath: str, report_config: Dict[str, Any]) -> None:
    """
    Создает и сохраняет отдельный файл Excel, содержащий только имена и email-адреса
    участников, которые присутствовали на вебинаре.

    :param geography_df: DataFrame с географическими данными участников, включая статус присутствия.
    :param filepath: Полный путь, по которому будет сохранен файл.
    :param report_config: Загруженный объект конфигурации отчета.
    """
    attended_df: pd.DataFrame = geography_df[geography_df['Присутствие на вебинаре'] == 'да'].copy()

    # Динамически находим финальные имена нужных столбцов
    proc_settings: Dict[str, Any] = report_config.get('processing_settings', {})
    inverted_map: Dict[str, str] = geography_df.attrs.get('inverted_map', {})
    rename_map: Dict[str, str] = proc_settings.get('rename_map', {})

    def get_final_name(internal_name: str) -> Optional[str]:
        source_name: Optional[str] = inverted_map.get(internal_name)
        if source_name:
            return rename_map.get(source_name, source_name)
        return None
    
    first_name_col: Optional[str] = get_final_name('first_name')
    last_name_col: Optional[str] = get_final_name('last_name')
    email_col: Optional[str] = get_final_name('email')

    required_cols: List[str] = [c for c in [first_name_col, last_name_col, email_col] if c]
    
    if not attended_df.empty and all(k in attended_df.columns for k in required_cols):
        report_df: pd.DataFrame = pd.DataFrame()
        report_df[0] = attended_df[first_name_col] + ' ' + attended_df[last_name_col]
        report_df[1] = attended_df[email_col]
        report_df.to_excel(filepath, index=False, header=False)
        logging.info(f"Файл с email адресами успешно сохранен: {filepath}")
    else:
        missing_cols: List[str] = [col for col in required_cols if col not in attended_df.columns]
        logging.warning(f"Нет данных для создания файла {os.path.basename(filepath)}. "
                        f"Причина: DataFrame пуст или отсутствуют необходимые столбцы: {missing_cols}")

def _filter_data(df: pd.DataFrame, report_config: Dict[str, Any]) -> pd.DataFrame:
    """
    Применяет различные фильтры к DataFrame с исходными данными на основе
    глобального списка исключений из .env и ролей для исключения из конфига отчета.

    :param df: Исходный DataFrame для фильтрации.
    :param report_config: Загруженный объект конфигурации отчета.
    :return: Отфильтрованный DataFrame.
    """
    proc_settings: Dict[str, Any] = report_config['processing_settings']
    
    # 1. Фильтрация по глобальному FILTER_LIST из .env
    if 'email' in df.columns and config.FILTER_LIST:
        initial_rows: int = len(df)
        # Email уже в нижнем регистре от config.py
        df = df[~df['email'].str.lower().isin(config.FILTER_LIST)]
        if (initial_rows - len(df)) > 0:
            logging.info(f"Отфильтровано {initial_rows - len(df)} строк по глобальному FILTER_LIST.")
    
    # 2. Фильтрация по ролям из конфига отчета
    roles_to_exclude: List[str] = proc_settings.get('filter', {}).get('roles_to_exclude', [])
    if 'role' in df.columns and roles_to_exclude:
        initial_rows: int = len(df)
        df = df[~df['role'].isin(roles_to_exclude)]
        if (initial_rows - len(df)) > 0:
            logging.info(f"Отфильтровано {initial_rows - len(df)} строк по ролям из конфига.")
            
    return df


def _create_geography_df(df: pd.DataFrame, report_config: Dict[str, Any]) -> pd.DataFrame:
    """
    Создает DataFrame для вкладки 'география участников' в выходном отчете.
    Выполняет переименование столбцов, добавление статуса присутствия и применение порядка столбцов.

    :param df: DataFrame с исходными данными участников.
    :param report_config: Загруженный объект конфигурации отчета.
    :return: DataFrame, подготовленный для вкладки 'география'.
    """
    proc_settings: Dict[str, Any] = report_config['processing_settings']
    column_map: Dict[str, str] = proc_settings['column_map']
    inverted_map: Dict[str, str] = {v: k for k, v in column_map.items()}

    # Создаем DataFrame, используя только те столбцы, что есть в карте
    internal_names_present: List[str] = [name for name in inverted_map.keys() if name in df.columns]
    report_df: pd.DataFrame = df[internal_names_present].copy()
    
    # Шаг 1: Переименовываем столбцы в их "настоящие" имена для вывода
    report_df.rename(columns=inverted_map, inplace=True)

    # Шаг 2: Применяем дополнительное, финальное переименование из конфига
    if 'rename_map' in proc_settings:
        report_df.rename(columns=proc_settings['rename_map'], inplace=True)
        logging.info("Применено дополнительное переименование столбцов.")

    # Шаг 3: Добавляем столбец присутствия
    if 'entry_time' in df.columns:
        not_attended_values: List[str] = proc_settings.get('not_attended_values', [])
        report_df['Присутствие на вебинаре'] = df['entry_time'].apply(
            lambda x: 'нет' if pd.isna(x) or str(x).strip() in not_attended_values else 'да'
        )

    # Шаг 4: Применяем порядок столбцов из конфига, если он задан, и отфильтровываем лишние
    defined_order: Optional[List[str]] = proc_settings.get('geography_column_order')
    if defined_order:
        # Отфильтровываем report_df, чтобы он содержал только столбцы из defined_order,
        # которые фактически присутствуют в DataFrame, в указанном порядке.
        final_column_order: List[str] = [col for col in defined_order if col in report_df.columns]
        report_df = report_df[final_column_order]
        logging.info("Порядок столбцов для 'географии' применен из конфигурации и нежелательные столбцы отфильтрованы.")
    else:
        logging.warning("geography_column_order не определен в конфиге. Отчет 'география' может содержать непредсказуемый порядок столбцов.")

    # Сохраняем карты для последующего использования
    report_df.attrs['column_map'] = column_map
    report_df.attrs['inverted_map'] = inverted_map

    return report_df


def _create_webinar_df(df: pd.DataFrame, geography_df: pd.DataFrame, soup: BeautifulSoup, report_config: Dict[str, Any]) -> pd.DataFrame:
    """
    Создает DataFrame для сводной вкладки 'вебинар' в выходном отчете.
    Извлекает данные о дате, продолжительности, теме, ведущем, количестве зарегистрированных и присутствовавших.

    :param df: DataFrame с исходными данными, содержащий временные метки и тему вебинара.
    :param geography_df: DataFrame с данными географии участников, используется для подсчета присутствовавших.
    :param soup: Объект BeautifulSoup для скрапинга дополнительных данных (например, новых email).
    :param report_config: Загруженный объект конфигурации отчета.
    :return: DataFrame, подготовленный для сводной вкладки вебинара.
    """
    start_time: Optional[pd.Timestamp] = pd.to_datetime(df['start_time'].dropna().iloc[0]) if 'start_time' in df.columns and not df['start_time'].dropna().empty else None
    end_time: Optional[pd.Timestamp] = pd.to_datetime(df['end_time'].dropna().iloc[0]) if 'end_time' in df.columns and not df['end_time'].dropna().empty else None
    
    date_str: str = start_time.strftime('%d.%m.%y %H:%M по Мск') if start_time else "Нет данных"
    duration_str: str = _calculate_duration(start_time, end_time)
    topic: str = df['webinar_topic'].dropna().iloc[0] if 'webinar_topic' in df.columns and not df['webinar_topic'].dropna().empty else "Нет данных"
    presenter: str = scraper.scrape_presenter(soup, report_config)
    
    registered: int = len(geography_df)
    attended_count: int = len(geography_df[geography_df['Присутствие на вебинаре'] == 'да'])
    not_attended: int = registered - attended_count
    attendance_percentage: str = f"{round((attended_count / registered * 100), 1)}%" if registered > 0 else "0.0%"
    new_emails: int = scraper.scrape_new_emails(soup, report_config)

    report_data: List[List[Any]] = [
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


def _create_chat_df(chat_file_path: Optional[str]) -> Optional[pd.DataFrame]:
    """
    Создает DataFrame из файла Excel, содержащего сообщения чата вебинара.

    :param chat_file_path: Путь к файлу Excel с данными чата.
    :return: DataFrame с сообщениями чата или None, если файл не найден или произошла ошибка чтения.
    """
    try:
        logging.info(f"Читаю файл чата: {chat_file_path}")
        return pd.read_excel(chat_file_path, sheet_name='Сообщения чата')
    except Exception as e:
        logging.error(f"Не удалось прочитать файл чата '{chat_file_path}'. Ошибка: {e}")
        return None


def _get_webinar_date_str(df: pd.DataFrame) -> str:
    """
    Извлекает и форматирует дату вебинара из DataFrame.
    Если дата не найдена, используется текущая дата.

    :param df: DataFrame с данными вебинара, ожидается столбец 'event_date'.
    :return: Строка с датой вебинара в формате 'YYYY-MM-DD'.
    """
    if 'event_date' in df.columns and not df['event_date'].dropna().empty:
        try:
            date_val: pd.Timestamp = df['event_date'].dropna().iloc[0]
            return pd.to_datetime(date_val).strftime('%Y-%m-%d')
        except (IndexError, TypeError): pass
    logging.warning("Дата вебинара не найдена, используется сегодняшняя дата.")
    return pd.Timestamp.now().strftime('%Y-%m-%d')

def _calculate_duration(start: Optional[pd.Timestamp], end: Optional[pd.Timestamp]) -> str:
    """
    Вычисляет и форматирует продолжительность вебинара в виде строки "X час Y минут".

    :param start: Начальное время вебинара (объект pd.Timestamp).
    :param end: Конечное время вебинара (объект pd.Timestamp).
    :return: Строка с продолжительностью или "Нет данных", если время не указано.
    """
    if pd.isna(start) or pd.isna(end): return "Нет данных"
    total_minutes: int = int((end - start).total_seconds() / 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours} час {minutes} минут"