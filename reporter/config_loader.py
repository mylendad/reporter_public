import yaml
import logging
from collections import namedtuple

def load_config(config_path):
    """
    Загружает и парсит YAML файл конфигурации.
    :param config_path: Путь к YAML файлу.
    :return: Объект с конфигурацией или None в случае ошибки.
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # Преобразуем вложенные словари в объекты для удобного доступа
        # config_obj = json.loads(json.dumps(config_data), object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))
        
        logging.info(f"Конфигурация '{config_data.get('report_name')}' успешно загружена из {config_path}")
        return config_data
    except FileNotFoundError:
        logging.error(f"Файл конфигурации не найден по пути: {config_path}")
        return None
    except yaml.YAMLError as e:
        logging.error(f"Ошибка парсинга YAML файла {config_path}: {e}")
        return None
    except Exception as e:
        logging.error(f"Неожиданная ошибка при загрузке конфигурации: {e}")
        return None

def get_column_name(config, internal_name):
    """
    Находит реальное имя столбца по его внутреннему имени из карты столбцов.
    :param config: Загруженный объект конфигурации.
    :param internal_name: Внутреннее имя столбца (e.g., 'first_name').
    :return: Реальное имя столбца (e.g., 'Имя').
    """
    column_map = config['processing_settings']['column_map']
    for real_name, internal in column_map.items():
        if internal == internal_name:
            return real_name
    logging.warning(f"Внутреннее имя столбца '{internal_name}' не найдено в карте столбцов.")
    return None

def get_internal_column_names(config, real_names):
    """
    Преобразует список реальных имен столбцов в список внутренних имен.
    """
    column_map = config['processing_settings']['column_map']
    internal_names = [column_map.get(name) for name in real_names if column_map.get(name)]
    return internal_names

def get_all_real_column_names(config):
    """Возвращает список всех реальных имен столбцов из конфига."""
    return list(config['processing_settings']['column_map'].keys())
