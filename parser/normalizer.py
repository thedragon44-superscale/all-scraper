from pydantic import BaseModel, Field
from utils import URLUtils

class UniversalMetadata(BaseModel):
    source_path: str
    path_segments: list[str]
    category_name: str
    category_path: str

class UniversalNormalizer:
    def __init__(self):
        pass

    def normalize_metadata(self, url: str, extracted_title: str = "") -> dict:
        """
        Extracts universal structural path segments and breadcrumbs from any URL or path string,
        utilizing centralized URL utility functions for robust parsing and normalization consistency.
        """
        try:
            clean_url = URLUtils.sanitize_url(url)
            from yarl import URL
            url_obj = URL(clean_url)
            path = url_obj.path
        except Exception:
            path = url.split("#")[0]

        path_segments = [seg for seg in path.strip("/").split("/") if seg]

        # Generate a clean readable category name from path segments
        if path_segments:
            category_name = " / ".join(path_segments).replace("_", " ").replace("-", " ").title()
        else:
            category_name = "Root"

        # Validate structure via Pydantic model
        metadata = UniversalMetadata(
            source_path=path,
            path_segments=path_segments,
            category_name=category_name,
            category_path=path
        )
        
        return metadata.model_dump()
