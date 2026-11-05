from pathlib import Path
from bs4 import BeautifulSoup
from pydantic import BaseModel

class ParsedDocument(BaseModel):
    title: str
    raw_html_path: str
    parsed_content: str
    image_urls: list[str] = []  # Tracks embedded component images/diagrams

class UniversalExtractor:
    def __init__(self):
        pass

    def extract_from_html(self, file_path: str) -> dict:
        """
        Parses a local raw HTML file using lxml and extracts clean text,
        page title, embedded image sources, and content sections validated via Pydantic.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"HTML file not found: {file_path}")

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()

        # Switched to 'lxml' parser for superior speed and robustness
        soup = BeautifulSoup(html_content, "lxml")

        # 1. Extract image sources BEFORE stripping out tags
        image_urls = []
        for img in soup.find_all("img", src=True):
            src = img["src"].strip()
            if src and src not in image_urls:
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

        # Validate extraction payload via Pydantic including image references
        document = ParsedDocument(
            title=title or path.stem,
            raw_html_path=str(path),
            parsed_content=parsed_text,
            image_urls=image_urls
        )

        return document.model_dump()
