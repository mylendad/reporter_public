import logging
from reporter import config
from reporter.browser import BrowserManager
from reporter.data_processor import process_and_generate_reports
from reporter.file_handler import cleanup_files

def main():
    """
    Основная функция для запуска процесса генерации отчетов.
    """
    # 1. Настройка
    config.setup_logging()
    if not config.validate_credentials():
        return

    page_url = input("Пожалуйста, введите URL страницы для парсинга: ").strip()
    if not page_url:
        logging.error("URL страницы не был введен. Выполнение прервано.")
        return

    # 2. Инициализация менеджера браузера
    browser_manager = BrowserManager(output_dir=config.OUTPUT_DIR)
    
    try:
        # 3. Авторизация
        if not browser_manager.login():
            logging.error("Процесс прерван из-за ошибки авторизации.")
            return

        # 4. Скачивание исходных файлов
        download_data = browser_manager.download_source_files(page_url)
        
        if not download_data:
            logging.error("Не удалось скачать исходные файлы. Обработка прекращена.")
            return
            
        # 5. Обработка данных и создание отчетов
        statistic_file, chat_file, soup = download_data
        process_and_generate_reports(statistic_file, chat_file, soup)

    finally:
        # 6. Очистка
        cleanup_files(browser_manager.downloaded_files)
        browser_manager.quit_driver()
        logging.info("Процесс автоматизации отчетов завершен.")


if __name__ == '__main__':
    main()