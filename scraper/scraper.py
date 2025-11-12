import os
import time
import json
import hashlib
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

# ================= CONFIG =================
BASE_URL = 'https://docs.python.org/3/'
OUTPUT_JSON = './data/scraped_pages.json'
LOG_FILE = './data/scraper.log'
MAX_PAGES = 200
DELAY = 1.0
TIMEOUT = 15
USER_AGENT = 'HajarRAGScraper/3.0 (+https://github.com/HajarElbehairy)'

# ================= Logging =================
os.makedirs(Path(OUTPUT_JSON).parent, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ================= Helper Functions =================
def setup_selenium_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument(f'user-agent={USER_AGENT}')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.set_page_load_timeout(TIMEOUT)
    return driver

def fetch_robots_txt(base_url: str):
    rp = RobotFileParser()
    rp.set_url(urljoin(base_url, '/robots.txt'))
    try:
        rp.read()
    except:
        logger.warning('robots.txt not found, proceeding cautiously')
        return None
    return rp

def can_fetch(rp: RobotFileParser, url: str) -> bool:
    if rp is None:
        return True
    try:
        return rp.can_fetch(USER_AGENT, url)
    except:
        return True

def normalize_url(url: str, base_url: str) -> str:
    url, _ = urldefrag(url)
    if not url.startswith('http'):
        url = urljoin(base_url, url)
    return url.rstrip('/')

def extract_canonical(soup: BeautifulSoup, current_url: str) -> str:
    canonical = soup.find('link', rel='canonical')
    return canonical['href'] if canonical and canonical.get('href') else current_url

def clean_content(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(['script','style','nav','header','footer','aside','iframe']):
        tag.decompose()
    main_content = soup.find('main') or soup.find('article') or soup.find('div', {'id':'main'}) or soup.find('body')
    return main_content.get_text(separator='\n', strip=True) if main_content else soup.get_text(separator='\n', strip=True)

def extract_links(soup: BeautifulSoup, current_url: str, base_url: str):
    links = set()
    base_domain = urlparse(base_url).netloc
    for a in soup.find_all('a', href=True):
        href = a['href']
        if any(href.startswith(prefix) for prefix in ['#','javascript:','mailto:','tel:']):
            continue
        abs_url = normalize_url(href, current_url)
        if urlparse(abs_url).netloc == base_domain:
            links.add(abs_url)
    return links

# ================= Main Scraper =================
class HybridScraper:
    def __init__(self):
        self.to_visit = [BASE_URL]
        self.visited = set()
        self.failed = set()
        self.pages_data = []
        self.robots_parser = fetch_robots_txt(BASE_URL)
        self.driver = setup_selenium_driver()

    def scrape(self, url: str):
        if url in self.visited or url in self.failed:
            return
        if not can_fetch(self.robots_parser, url):
            logger.warning(f'Blocked by robots.txt: {url}')
            self.failed.add(url)
            return

        logger.info(f'Fetching: {url}')
        html = None
        # Try requests first
        try:
            resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except Exception:
            # Fallback to Selenium for JS-heavy
            try:
                self.driver.get(url)
                time.sleep(1)
                html = self.driver.page_source
            except (TimeoutException, WebDriverException) as e:
                logger.error(f'Failed (timeout/Selenium): {url} - {e}')
                self.failed.add(url)
                return

        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else ''
        canonical = extract_canonical(soup, url)
        content = clean_content(soup)
        checksum = hashlib.md5(content.encode()).hexdigest()

        page_data = {
            'url': url,
            'canonical_url': canonical,
            'title': title,
            'content': content,
            'html': html,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'checksum': checksum
        }

        self.pages_data.append(page_data)
        self.visited.add(url)
        for link in extract_links(soup, url, BASE_URL):
            if link not in self.visited and link not in self.to_visit:
                self.to_visit.append(link)
        time.sleep(DELAY)

    def run(self):
        pbar = tqdm(total=MAX_PAGES, desc='Scraping pages')
        try:
            while self.to_visit and len(self.visited) < MAX_PAGES:
                url = self.to_visit.pop(0)
                self.scrape(url)
                pbar.update(1)
        except KeyboardInterrupt:
            logger.info('Scraping interrupted')
        finally:
            pbar.close()
            self.driver.quit()
            # Save all pages in one JSON file
            with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.pages_data, f, ensure_ascii=False, indent=2)
            logger.info(f'Finished. Pages scraped: {len(self.visited)}, Failed: {len(self.failed)}')
            logger.info(f'All data saved to {OUTPUT_JSON}')

# ================= Run Scraper =================
if __name__ == '__main__':
    scraper = HybridScraper()
    scraper.run()
