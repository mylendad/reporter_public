import logging
import argparse
from reporter import config, config_loader
from reporter.browser import BrowserManager
from reporter.data_processor import process_and_generate_reports
from reporter.file_handler import cleanup_files

def main():
    """
    Основная функция для запуска процесса генерации отчетов.
    """
    print("Main function started execution.")
    try:
        # 1. Настройка и парсинг аргументов
        config.setup_logging()
        logging.info("--> main: Script started.")
        
        parser = argparse.ArgumentParser(description="Генератор отчетов по вебинарам.")
        parser.add_argument(
            '-c', '--config',
            type=str,
            default='configs/mts_link_report.yaml',
            help='Путь к файлу конфигурации YAML. По умолчанию: configs/mts_link_report.yaml'
        )
        args = parser.parse_args()
        logging.info("--> main: Parsed arguments.")

        # 2. Загрузка конфигурации
        report_config = config_loader.load_config(args.config)
        if not report_config:
            return
        logging.info("--> main: Loaded report config.")

        if not config.validate_credentials():
            return
        logging.info("--> main: Validated credentials.")

        page_url = input("Пожалуйста, введите URL страницы для парсинга: ").strip()
        if not page_url:
            logging.error("URL страницы не был введен. Выполнение прервано.")
            return
        logging.info("--> main: Received URL.")

        # 3. Инициализация и запуск
        browser_manager = BrowserManager(output_dir=config.OUTPUT_DIR, report_config=report_config)
        logging.info("--> main: BrowserManager initialized.")
        
        try:
            logging.info("--> main: Entering main try block.")
            if not browser_manager.login():
                logging.error("Процесс прерван из-за ошибки авторизации.")
                return
            logging.info("--> main: Login successful.")

            download_data = browser_manager.download_source_files(page_url)
            
            if not download_data:
                logging.error("Не удалось скачать исходные файлы. Обработка прекращена.")
                return
            logging.info("--> main: File download successful.")
                
            statistic_file, chat_file, soup = download_data
            process_and_generate_reports(
                statistic_file_path=statistic_file,
                chat_file_path=chat_file,
                soup=soup,
                report_config=report_config
            )
            logging.info("--> main: Report processing finished.")

        finally:
            logging.info("--> main: Entering finally block.")
            cleanup_files(browser_manager.downloaded_files)
            browser_manager.quit_driver()
            logging.info("Процесс автоматизации отчетов завершен.")

    except SystemExit as e:
        logging.error(f"--> main: Caught SystemExit! Code: {e.code}")
    except Exception as e:
        logging.error(f"--> main: An unexpected error occurred in main: {e}", exc_info=True)



if __name__ == '__main__':
    main()
