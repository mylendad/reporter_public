import logging
import re

def scrape_presenter(soup):
    """Парсит имя ведущего со страницы."""
    if not soup:
        return "Не удалось получить"
    try:
        presenter_tag = soup.find(string=re.compile(r'Ведущий вебинара:'))
        if presenter_tag:
            # Ищем следующий текстовый узел или строку, которая не пустая
            next_sibling = presenter_tag.find_next(string=True)
            if next_sibling and next_sibling.strip():
                name = next_sibling.strip()
                # Обрезаем после третьего пробела, если он есть
                parts = name.split()
                if len(parts) > 3:
                    return " ".join(parts[:3])
                return name
    except Exception as e:
        logging.warning(f"Не удалось извлечь имя ведущего: {e}")
    return "Не найдено"

def scrape_new_emails(soup):
    """Парсит количество новых email'ов со страницы."""
    if not soup:
        return "Не удалось получить"
    try:
        email_tag = soup.find('td', attrs={'data-testid': 'PlotPie.LabelNumber.visitorsChart.0'})
        if email_tag:
            return email_tag.text.strip()
    except Exception as e:
        logging.warning(f"Не удалось извлечь количество новых email: {e}")
    return "Не найдено"
