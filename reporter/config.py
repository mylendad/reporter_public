import os
import logging
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# Учетные данные
LOGIN = os.getenv("LOGIN")
PASSWORD = os.getenv("PASSWORD")

# Фильтрация
FILTER_LIST_STR = os.getenv("FILTER_LIST", "")
FILTER_LIST = [email.strip().lower() for email in FILTER_LIST_STR.split(',') if email.strip()]

# Настройки путей
OUTPUT_DIR = "."
REPORT_DIR = "Отчет"

# Настройки отчета
REPORT_SHEET_NAME = "Сеансы входов" # Имя листа в файле statistic.xls для обработки

def setup_logging():
    """Настраивает конфигурацию логирования."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.info("Логирование настроено.")

def validate_credentials():
    """Проверяет наличие учетных данных."""
    if not all([LOGIN, PASSWORD]):
        logging.error("Переменные LOGIN и PASSWORD должны быть заданы в .env файле.")
        return False
    return True

if FILTER_LIST:
    logging.info(f"Загружен FILTER_LIST из .env, содержит {len(FILTER_LIST)} адресов для фильтрации.")

