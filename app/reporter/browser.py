import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import config
from .downloader import download_file


class BrowserManager:
    """
    Класс для управления сессией браузера с использованием Selenium WebDriver.
    Отвечает за:
    - Инициализацию и настройку драйвера Chrome.
    - Авторизацию на веб-сайте с использованием учетных данных и селекторов из конфигурации.
    - Навигацию по страницам.
    - Скачивание файлов (статистика, чат) через кнопки на странице и обработку уведомлений.
    - Извлечение cookie для использования с сессией `requests`.
    - Корректное закрытие драйвера.
    """

    def __init__(self, output_dir: str, report_config: Dict[str, Any]) -> None:
        """
        Инициализирует BrowserManager.

        :param output_dir: Директория для сохранения скачанных файлов.
        :param report_config: Загруженный объект конфигурации отчета.
        """
        self.output_dir: str = output_dir
        self.config: Dict[str, Any] = report_config
        self.selectors: Dict[str, Any] = self.config["source_settings"]["selectors"]
        self.driver: Optional[webdriver.Chrome] = None
        self.session: requests.Session = requests.Session()
        self.downloaded_files: List[str] = []

    def login(self) -> bool:
        """
        Выполняет вход на сайт, используя Selenium и селекторы из конфига.

        :return: True, если авторизация успешна, иначе False.
        """
        logging.info("--> Entering login method.")
        try:
            logging.info("Инициализация драйвера Selenium Chrome...")
            options: webdriver.ChromeOptions = webdriver.ChromeOptions()

            # Настройки для обхода обнаружения автоматизации
            options.add_argument(
                "--disable-blink-features=AutomationControlled"
            )  # Убирает свойство navigator.webdriver
            options.add_experimental_option(
                "excludeSwitches", ["enable-automation"]
            )  # Удаляет переключатель "enable-automation"
            options.add_experimental_option(
                "useAutomationExtension", False
            )  # Отключает расширение автоматизации Chrome
            options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
            )  # Подменяет строку User-Agent на обычный браузерный

            # Дополнительные настройки для стабильности и отладки
            options.add_argument(
                "--no-sandbox"
            )  # Отключает песочницу, что может помочь в некоторых окружениях Docker или CI/CD.
            options.add_argument(
                "--disable-extensions"
            )  # Отключает расширения браузера, которые могут мешать или быть обнаружены.
            options.add_argument(
                "--log-level=3"
            )  # Уменьшает детализацию логов Chromedriver в консоли, чтобы избежать загромождения вывода.

            prefs: Dict[str, str] = {
                "download.default_directory": os.path.abspath(self.output_dir)
            }
            options.add_experimental_option("prefs", prefs)
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")

            # Указываем путь для логов Chromedriver
            service: Service = Service(
                log_path=os.path.join(
                    os.path.abspath(self.output_dir), "chromedriver.log"
                )
            )
            self.driver = webdriver.Chrome(service=service, options=options)

            login_url: str = self.config["source_settings"]["login_url"]
            logging.info(f"Перехожу на страницу входа: {login_url}")
            self.driver.get(login_url)

            wait: WebDriverWait = WebDriverWait(self.driver, 40)

            # Используем селекторы из конфига
            login_selectors: Dict[str, str] = self.selectors["login"]
            email_input: WebElement = wait.until(
                EC.presence_of_element_located(  # Ждет когда объект появится в DOM
                    (By.CSS_SELECTOR, login_selectors["email_input"])
                )
            )
            email_input.send_keys(config.LOGIN)

            submit_button: WebElement = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, login_selectors["submit_button"])
                )
            )
            submit_button.click()

            password_input: WebElement = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, login_selectors["password_input"])
                )
            )
            password_input.send_keys(config.PASSWORD)

            login_button: WebElement = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, login_selectors["login_button"])
                )
            )
            login_button.click()

            wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, login_selectors["success_indicator"])
                )
            )
            logging.info("Авторизация через Selenium прошла успешно.")

            selenium_cookies: List[Dict[str, Any]] = self.driver.get_cookies()
            for cookie in selenium_cookies:
                self.session.cookies.set(
                    cookie["name"], cookie["value"], domain=cookie["domain"]
                )

            logging.info("--> Exiting login method successfully.")
            return True

        except TimeoutException as e:
            logging.error(
                f"Не удалось выполнить авторизацию: время ожидания элемента истекло. {e}"
            )
            return False
        except Exception as e:
            logging.error(f"Произошла ошибка при авторизации через Selenium: {e}")
            return False

    def download_source_files(
        self, page_url: str
    ) -> Optional[Tuple[str, Optional[str], BeautifulSoup]]:
        """
        Кликает на кнопки скачивания и скачивает файлы (статистика, чат).

        :param page_url: URL страницы, с которой нужно скачать файлы.
        :return: Кортеж с путями к скачанным файлам (статистика, чат) и объектом BeautifulSoup страницы,
                 или None в случае ошибки.
        """
        logging.info("--> Entering download_source_files method.")
        if not self.driver:
            return None

        logging.info(f"Перехожу на страницу мероприятия: {page_url}")

        final_stats_file_path: Optional[str] = None
        final_chat_file_path: Optional[str] = None
        dl_selectors: Dict[str, str] = self.selectors["download"]

        try:
            self.driver.get(page_url)
            wait: WebDriverWait = WebDriverWait(self.driver, 40)

            # Скачиваем СТАТИСТИКУ
            try:
                logging.info("Ищу кнопку для скачивания статистики...")
                stats_button: WebElement = wait.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            dl_selectors["stats_button"],
                        )  # presence_of_element_located элемент есть в DOM
                    )
                )
                self.driver.execute_script("arguments[0].click();", stats_button)
                stats_url: Optional[str] = self._handle_download_notification(
                    wait
                )  # Извлекаем ссылку скачивания статистики из кнопки

                if stats_url:
                    stats_filename: str = "statistic_" + os.path.basename(
                        urlparse(stats_url).path
                    )
                    final_stats_file_path = os.path.join(
                        self.output_dir, stats_filename
                    )
                    if download_file(self.session, stats_url, final_stats_file_path):
                        self.downloaded_files.append(final_stats_file_path)
                else:
                    return None
            except TimeoutException:
                logging.error("Не удалось найти кнопку для скачивания статистики.")
                return None

            # Скачиваем ЧАТ
            try:
                logging.info("Ищу кнопку для скачивания чата...")
                chat_button: WebElement = wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH, dl_selectors["chat_button"])
                    )
                )
                self.driver.execute_script("arguments[0].click();", chat_button)
                chat_url: Optional[str] = self._handle_download_notification(wait)

                if chat_url:
                    chat_filename: str = "chat_" + os.path.basename(
                        urlparse(chat_url).path
                    )
                    final_chat_file_path = os.path.join(self.output_dir, chat_filename)
                    if download_file(self.session, chat_url, final_chat_file_path):
                        self.downloaded_files.append(final_chat_file_path)
            except TimeoutException:
                logging.warning(
                    "Не удалось найти кнопку для скачивания чата. Пропускаю."
                )

            logging.info("--> Exiting download_source_files method successfully.")
            return (
                final_stats_file_path,
                final_chat_file_path,
                BeautifulSoup(self.driver.page_source, "html.parser"),
            )

        except Exception as e:
            logging.error(f"Ошибка при скачивании файлов: {e}")
            return None

    def _handle_download_notification(self, wait: WebDriverWait) -> Optional[str]:
        """
        Обрабатывает уведомление (Snackbar) о начале скачивания и извлекает URL для прямого скачивания.

        :param wait: Объект WebDriverWait для явного ожидания элементов.
        :return: URL скачиваемого файла, если успешно извлечен, иначе None.
        """
        dl_selectors: Dict[str, str] = self.selectors["download"]
        try:
            snackbar: WebElement = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, dl_selectors["snackbar_notification"])
                )
            )
            download_url: str | None = snackbar.find_element(
                By.XPATH, dl_selectors["snackbar_link"]
            ).get_attribute("href")  # href (URL файла)
            logging.info(f"Извлечена ссылка для скачивания: {download_url}")

            close_button: WebElement = snackbar.find_element(
                By.XPATH, dl_selectors["snackbar_close_button"]
            )
            self.driver.execute_script("arguments[0].click();", close_button)
            wait.until(
                EC.invisibility_of_element(snackbar)
            )  # ждем пока уведомление пропадет со страницы
            logging.info("Уведомление успешно закрыто.")

            return download_url
        except TimeoutException:
            logging.error("Не удалось найти/обработать/закрыть уведомление (Snackbar).")
            return None
        except Exception as e:
            logging.error(f"Ошибка при обработке уведомления: {e}")
            return None

    def quit_driver(self) -> None:
        """
        Корректно закрывает драйвер Selenium и освобождает связанные ресурсы.
        """
        if self.driver:
            logging.info("Закрываю драйвер Selenium.")
            self.driver.quit()
            self.driver = None
