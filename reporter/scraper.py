import logging
import re

def scrape_presenter(soup, report_config):
    """Парсит имя ведущего со страницы, используя селекторы из конфига."""
    if not soup: return "Не удалось получить"
    
    scraper_selectors = report_config['source_settings']['selectors']['scraper']
    presenter_text = scraper_selectors.get('presenter')
    
    if not presenter_text:
        logging.warning("Селектор для имени ведущего не найден в конфиге.")
        return "Не настроено"
        
    try:
        presenter_tag = soup.find(string=re.compile(presenter_text))
        if presenter_tag:
            next_sibling = presenter_tag.find_next(string=True)
            if next_sibling and next_sibling.strip():
                name = next_sibling.strip()
                parts = name.split()
                return " ".join(parts[:3]) if len(parts) > 3 else name
    except Exception as e:
        logging.warning(f"Не удалось извлечь имя ведущего: {e}")
    return "Не найдено"

def scrape_new_emails(soup, report_config):
    """Парсит количество новых email'ов, используя селекторы из конфига."""
    if not soup: return "Не удалось получить"
    
    scraper_selectors = report_config['source_settings']['selectors']['scraper']
    email_selector = scraper_selectors.get('new_emails')

    if not email_selector:
        logging.warning("Селектор для новых email не найден в конфиге.")
        return "Не настроено"
        
    try:
        email_tag = soup.select_one(email_selector)
        if email_tag:
            return email_tag.text.strip()
    except Exception as e:
        logging.warning(f"Не удалось извлечь количество новых email: {e}")
    return "Не найдено"