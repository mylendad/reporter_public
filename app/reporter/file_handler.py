import os
import logging
from typing import List, Optional

def cleanup_files(files: List[Optional[str]]) -> None:
    """
    Удаляет список временных скачанных файлов, которые больше не нужны.
    Проверяет существование файла перед удалением, чтобы избежать ошибок.

    :param files: Список путей к файлам для удаления. Элементы могут быть None.
    """
    logging.info("Удаляю временные скачанные файлы...")
    for file_path in files:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Удален файл: {file_path}")
        except Exception as e:
            logging.warning(f"Не удалось удалить файл {file_path}: {e}")
