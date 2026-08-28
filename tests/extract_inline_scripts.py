from pathlib import Path
from bs4 import BeautifulSoup

html = Path('static/index.html').read_text(encoding='utf-8')
soup = BeautifulSoup(html, 'html.parser')
for index, tag in enumerate(soup.find_all('script'), start=1):
    if tag.get('src'):
        continue
    Path(f'/tmp/nfse-inline-{index}.js').write_text(tag.string or tag.get_text(), encoding='utf-8')
