from urllib.parse import urlparse
from pydantic import BaseModel, Field

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
        Extracts universal structural path segments and breadcrumbs from any URL,
        leaving domain-specific mapping entirely to the ingestion layer.
        """
        parsed_url = urlparse(url)
        path_segments = [seg for seg in parsed_url.path.strip("/").split("/") if seg]

        # Generate a clean readable category name from path segments
        if path_segments:
            category_name = " / ".join(path_segments).replace("_", " ").replace("-", " ").title()
        else:
            category_name = "Root"

        # Validate structure via Pydantic model
        metadata = UniversalMetadata(
            source_path=parsed_url.path,
            path_segments=path_segments,
            category_name=category_name,
            category_path=parsed_url.path
        )
        
        return metadata.model_dump()
