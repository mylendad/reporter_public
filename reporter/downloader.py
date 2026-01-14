import logging
import requests

def download_file(session, url, file_path):
    """
    Скачивает один файл по URL, используя аутентифицированную сессию requests.
    :param session: Объект requests.Session с cookies после авторизации.
    :param url: URL для скачивания файла.
    :param file_path: Локальный путь для сохранения файла.
    :return: True, если скачивание успешно, иначе False.
    """
    logging.info(f"Скачиваю {url} -> {file_path}")
    try:
        resp = session.get(url)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        # Проверяем, что контент похож на Excel или бинарный файл
        if "excel" in content_type or "vnd.ms-excel" in content_type or "application/octet-stream" in content_type:
            with open(file_path, "wb") as f:
                f.write(resp.content)
            logging.info(f"Файл успешно сохранен: {file_path}")
            return True
        else:
            logging.warning(f"Пропущено скачивание (неверный Content-Type): {url}. Content-Type: {content_type}")
            return False
    except requests.RequestException as e:
        logging.error(f"Ошибка при скачивании {url}: {e}")
        return False
