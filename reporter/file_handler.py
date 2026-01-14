import os
import logging

def cleanup_files(files):
    """
    Удаляет список временных файлов.
    :param files: Список путей к файлам для удаления.
    """
    logging.info("Удаляю временные скачанные файлы...")
    for file_path in files:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Удален файл: {file_path}")
        except Exception as e:
            logging.warning(f"Не удалось удалить файл {file_path}: {e}")
