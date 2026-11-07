from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Pydantic models for strict validation and schema enforcement
class DimensionsModel(BaseModel):
    width: int
    height: int


class TextBlockModel(BaseModel):
    block_id: str
    block_type: str = "text"
    text_content: str
    confidence: Optional[int] = None
    spatial_coordinates: List[int] = Field(..., min_length=4, max_length=4)


class FigureBlockModel(BaseModel):
    figure_id: str
    image_file_path: str
    spatial_coordinates: List[int] = Field(..., min_length=4, max_length=4)
    dimensions: DimensionsModel
    associated_caption_id: Optional[str] = None


class PageModel(BaseModel):
    page_number: int
    page_dimensions: DimensionsModel
    page_topics: List[str] = Field(default_factory=list)
    page_summary: str = ""
    intent_category: str = "specification"
    key_concepts: List[str] = Field(default_factory=list)
    text_blocks: List[TextBlockModel] = Field(default_factory=list)
    figure_blocks: List[FigureBlockModel] = Field(default_factory=list)


class DocumentSchemaModel(BaseModel):
    document_name: str
    total_pages: int
    pages: List[PageModel] = Field(default_factory=list)


class SchemaMapper:

    def __init__(self, document_name: str, total_pages: int):
        """Initializes the schema mapper for a specific document."""
        self.document_name = document_name
        self.total_pages = total_pages
        self.pages_data: Dict[int, Dict[str, Any]] = {}

    def add_page_data(
        self,
        page_number: int,
        page_dimensions: Dict[str, int],
        text_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        analysis_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Aggregates parsed text, layout figures, and analysis metadata for a specific page."""
        analysis = analysis_metadata or {}

        self.pages_data[page_number] = {
            "page_number": page_number,
            "page_dimensions": page_dimensions,
            "page_topics": analysis.get("page_topics", []),
            "page_summary": analysis.get("page_summary", ""),
            "intent_category": analysis.get("intent_category", "specification"),
            "key_concepts": analysis.get("key_concepts", []),
            "text_blocks": text_blocks,
            "figure_blocks": figure_blocks,
        }

    def build_document_schema(self) -> Dict[str, Any]:
        """Validates and compiles all page data into the final normalized document schema dictionary."""
        sorted_pages = [
            self.pages_data[p] for p in sorted(self.pages_data.keys())
        ]

        raw_document = {
            "document_name": self.document_name,
            "total_pages": self.total_pages,
            "pages": sorted_pages,
        }

        # Validate against the strict Pydantic schema model
        validated_doc = DocumentSchemaModel(**raw_document)
        return validated_doc.model_dump()

    def save_json(self, output_path: str | Path) -> None:
        """Serializes and writes the validated schema out to a JSON file."""
        import json

        schema_dict = self.build_document_schema()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(schema_dict, f, indent=2, ensure_ascii=False)
