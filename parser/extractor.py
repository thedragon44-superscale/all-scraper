from pathlib import Path
from bs4 import BeautifulSoup
from pydantic import BaseModel
from yarl import URL
from utils import URLUtils

class ParsedDocument(BaseModel):
    title: str
    raw_html_path: str
    parsed_content: str
    image_urls: list[str] = []  # Tracks embedded component images/diagrams

class UniversalExtractor:
    def __init__(self, base_url: str = ""):
        self.base_url = base_url

    def extract_from_html(self, file_path: str) -> dict:
        """
        Parses a local raw HTML file using lxml and extracts clean text,
        page title, fully qualified absolute image sources, and content sections validated via Pydantic.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"HTML file not found: {file_path}")

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()

        # Switched to 'lxml' parser for superior speed and robustness
        soup = BeautifulSoup(html_content, "lxml")

        # Auto-detect base URL from document metadata if not explicitly provided
        doc_base_url = self.base_url
        if not doc_base_url:
            base_tag = soup.find("base", href=True)
            if base_tag:
                doc_base_url = base_tag["href"]
            else:
                canonical = soup.find("link", rel="canonical")
                if canonical and canonical.get("href"):
                    doc_base_url = canonical["href"]
                else:
                    for tag in soup.find_all(["a", "img"], href=True) or soup.find_all("img", src=True):
                        link = tag.get("href") or tag.get("src")
                        if link and link.startswith("http"):
                            parsed_link = URL(link)
                            doc_base_url = f"{parsed_link.scheme}://{parsed_link.host}"
                            break

        # 1. Extract and fully qualify image sources BEFORE stripping out tags
        image_urls = []
        for img in soup.find_all("img", src=True):
            src = img["src"].strip()
            if src and not src.startswith("data:"):
                try:
                    if not src.startswith("http") and doc_base_url:
                        abs_src = str(URL(doc_base_url).join(URL(src)))
                    else:
                        abs_src = src
                    
                    clean_img = URLUtils.sanitize_url(abs_src)
                    if clean_img not in image_urls:
                        image_urls.append(clean_img)
                except Exception:
                    if src not in image_urls:
                        image_urls.append(src)

        # Strip out non-content elements
        for element in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
            element.decompose()

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.h1:
            title = soup.h1.get_text(strip=True)

        # Main content extraction
        main_container = soup.find("main") or soup.find("article") or soup.find("div", id="content") or soup.body

        if main_container:
            parsed_text = main_container.get_text(separator="\n", strip=True)
        else:
            parsed_text = soup.get_text(separator="\n", strip=True)

        # Validate extraction payload via Pydantic including fully qualified image references
        document = ParsedDocument(
            title=title or path.stem,
            raw_html_path=str(path),
            parsed_content=parsed_text,
            image_urls=image_urls
        )

        return document.model_dump()
