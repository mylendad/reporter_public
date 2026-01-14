import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from urllib.parse import urlparse

from . import config
from .downloader import download_file

class BrowserManager:
    """
    Класс для управления Selenium WebDriver, включая авторизацию и скачивание файлов.
    """
    def __init__(self, output_dir="."):
        """
        Инициализирует BrowserManager.
        :param output_dir: Директория для сохранения скачанных файлов.
        """
        self.output_dir = output_dir
        self.driver = None
        self.session = requests.Session()
        self.downloaded_files = []

    def login(self):
        """Выполняет вход на сайт, используя Selenium."""
        try:
            logging.info("Инициализация драйвера Selenium Chrome...")
            options = webdriver.ChromeOptions()
            prefs = {
                "download.default_directory": os.path.abspath(self.output_dir),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            options.add_experimental_option("prefs", prefs)
            # options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            self.driver = webdriver.Chrome(options=options)
            
            login_page_url = "https://my.mts-link.ru/"
            logging.info(f"Перехожу на страницу входа: {login_page_url}")
            self.driver.get(login_page_url)

            wait = WebDriverWait(self.driver, 40)
            
            email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"], input[name="email"]')))
            logging.info("Найдено поле для ввода email. Ввожу email...")
            email_input.send_keys(config.LOGIN)

            submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]')))
            logging.info("Нажимаю кнопку отправки email...")
            submit_button.click()
            
            password_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"], input[name="password"]')))
            logging.info("Найдено поле для ввода пароля. Ввожу пароль...")
            password_input.send_keys(config.PASSWORD)

            login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]')))
            logging.info("Нажимаю кнопку 'Войти'...")
            login_button.click()

            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Мой тариф')]")))
            logging.info("Авторизация через Selenium прошла успешно.")
            
            logging.info("Передаю cookies из Selenium в сессию Requests.")
            selenium_cookies = self.driver.get_cookies()
            for cookie in selenium_cookies:
                self.session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

            return True

        except TimeoutException:
            logging.error("Не удалось выполнить авторизацию через Selenium: время ожидания элемента истекло.")
            if self.driver:
                self.driver.save_screenshot("selenium_login_failure.png")
            return False
        except Exception as e:
            logging.error(f"Произошла ошибка при авторизации через Selenium: {e}")
            if self.driver:
                self.driver.save_screenshot("selenium_login_error.png")
            return False

    def quit_driver(self):
        """Корректно закрывает драйвер Selenium."""
        if self.driver:
            logging.info("Закрываю драйвер Selenium.")
            self.driver.quit()
            self.driver = None

    def download_source_files(self, page_url):
        """
        Кликает на кнопки скачивания и скачивает файлы статистики и чата.
        :param page_url: URL страницы мероприятия.
        :return: Кортеж (путь_к_файлу_статистики, путь_к_файлу_чата, объект_soup) или None.
        """
        if not self.driver:
            logging.error("Драйвер Selenium не инициализирован.")
            return None

        logging.info(f"Перехожу на страницу мероприятия (через Selenium): {page_url}")
        
        final_stats_file_path = None
        final_chat_file_path = None

        try:
            self.driver.get(page_url)
            wait = WebDriverWait(self.driver, 20)
            
            try:
                logging.info("Ищу кнопку для скачивания статистики (xls)...")
                stats_xls_button = wait.until(EC.presence_of_element_located((By.XPATH,
                    "//div[contains(., 'Скачать статистику')]/a[contains(@data-bind, \"'xls', 'stats'\")]")))
                
                self.driver.execute_script("arguments[0].click();", stats_xls_button)
                logging.info("Кликнул на кнопку скачивания статистики.")
                stats_download_url = self._handle_download_notification(wait)

                if stats_download_url:
                    stats_filename = "statistic_" + os.path.basename(urlparse(stats_download_url).path)
                    final_stats_file_path = os.path.join(self.output_dir, stats_filename)
                    if download_file(self.session, stats_download_url, final_stats_file_path):
                        self.downloaded_files.append(final_stats_file_path)
                else:
                    logging.error("Не удалось получить URL для скачивания статистики.")
                    return None

            except TimeoutException:
                logging.error("Не удалось найти кнопку для скачивания статистики.")
                return None

            logging.info("Делаю паузу в 5 секунд перед запросом на скачивание чата...")
            time.sleep(5)

            try:
                logging.info("Ищу кнопку для скачивания чата (xls)...")
                chat_xls_button = wait.until(EC.presence_of_element_located((By.XPATH,
                    "//div[contains(., 'Скачать чат')]/a[contains(@data-bind, \"'xls', 'chat'\")]")))

                self.driver.execute_script("arguments[0].click();", chat_xls_button)
                logging.info("Кликнул на кнопку скачивания чата.")
                chat_download_url = self._handle_download_notification(wait)

                if chat_download_url:
                    chat_filename = "chat_" + os.path.basename(urlparse(chat_download_url).path)
                    final_chat_file_path = os.path.join(self.output_dir, chat_filename)
                    if download_file(self.session, chat_download_url, final_chat_file_path):
                        self.downloaded_files.append(final_chat_file_path)
                else:
                    logging.warning("Не удалось получить URL для скачивания чата.")

            except TimeoutException:
                logging.warning("Не удалось найти кнопку для скачивания чата. Пропускаю.")

            return (final_stats_file_path, final_chat_file_path, BeautifulSoup(self.driver.page_source, "html.parser"))

        except Exception as e:
            logging.error(f"Ошибка при скачивании файлов через Selenium: {e}")
            self.driver.save_screenshot("download_files_error.png")
            return None

    def _handle_download_notification(self, wait):
        """
        Обрабатывает уведомление (Snackbar), извлекает ссылку и закрывает его.
        """
        try:
            snackbar_xpath = "//div[contains(@class, 'MuiSnackbarContent-root') and contains(., 'Файл подготовлен')]"
            logging.info("Ожидаю появления уведомления (Snackbar)...")
            
            snackbar_element = wait.until(EC.presence_of_element_located((By.XPATH, snackbar_xpath)))
            logging.info("Уведомление найдено.")

            download_link_element = snackbar_element.find_element(By.XPATH, ".//a")
            download_url = download_link_element.get_attribute("href")
            logging.info(f"Извлечена ссылка для скачивания: {download_url}")

            close_button = snackbar_element.find_element(By.XPATH, ".//button[contains(@class, 'MuiIconButton-root')]")
            self.driver.execute_script("arguments[0].click();", close_button)
            logging.info("Нажал кнопку закрытия уведомления.")
            
            wait.until(EC.invisibility_of_element(snackbar_element))
            logging.info("Уведомление успешно закрыто.")
            
            return download_url
        except TimeoutException:
            logging.error("Не удалось найти/обработать/закрыть уведомление (Snackbar).")
            self.driver.save_screenshot("snackbar_error.png")
            return None
        except Exception as e:
            logging.error(f"Ошибка при обработке уведомления: {e}")
            self.driver.save_screenshot("snackbar_error.png")
            return None

