import os
import logging
from dotenv import load_dotenv
from typing import List, Optional

# Загружаем переменные из .env файла
load_dotenv()

 # Глобальные переменные окружения
LOGIN: Optional[str] = os.getenv("LOGIN")
PASSWORD: Optional[str] = os.getenv("PASSWORD")
FILTER_LIST_STR: str = os.getenv("FILTER_LIST", "")
FILTER_LIST: List[str] = [email.strip().lower() for email in FILTER_LIST_STR.split(',') if email.strip()]

 # Настройки путей (остаются здесь, т.к. они не зависят от типа отчета)
OUTPUT_DIR: str = "."
REPORT_DIR: str = "Отчет"

def setup_logging() -> None:
    """Настраивает конфигурацию логирования."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.info("Логирование настроено.")

def validate_credentials() -> bool:
    """Проверяет наличие учетных данных в .env."""
    if not all([LOGIN, PASSWORD]):
        logging.error("Переменные LOGIN и PASSWORD должны быть заданы в .env файле.")
        return False
    logging.info("Учетные данные успешно загружены.")
    return True

setup_logging()

if FILTER_LIST:
    logging.info(f"Загружен глобальный FILTER_LIST из .env, содержит {len(FILTER_LIST)} адресов для фильтрации.")