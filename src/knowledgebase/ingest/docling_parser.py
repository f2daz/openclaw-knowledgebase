"""Document parsing with Docling for OpenClaw Knowledgebase."""

import csv
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Optional import - Docling is heavy (ML models)
try:
    from docling.document_converter import DocumentConverter
    HAS_DOCLING = True
except ImportError:
    HAS_DOCLING = False


@dataclass
class ParsedDocument:
    """A parsed document."""
    path: str
    title: str | None
    content: str  # Markdown content
    format: str  # pdf, docx, etc.
    metadata: dict = field(default_factory=dict)


# Formats we can handle natively (no Docling needed)
NATIVE_TEXT_FORMATS = {".txt", ".md", ".markdown", ".rst", ".json", ".yaml", ".yml", ".csv", ".tsv"}

# Formats that need Docling
DOCLING_FORMATS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".html", ".htm"}

# All supported formats
ALL_FORMATS = NATIVE_TEXT_FORMATS | DOCLING_FORMATS


def check_docling() -> tuple[bool, str]:
    """Check if Docling is available."""
    if HAS_DOCLING:
        return True, "Docling available"
    return False, "Docling not installed. Install with: pip install docling"


def get_supported_formats(include_docling: bool = True) -> set[str]:
    """Get all supported file formats."""
    formats = set(NATIVE_TEXT_FORMATS)
    if include_docling and HAS_DOCLING:
        formats.update(DOCLING_FORMATS)
    return formats


def parse_plain_text(path: Path) -> ParsedDocument:
    """Parse a plain text file."""
    content = path.read_text(encoding="utf-8", errors="ignore")
    
    # Try to extract title from first line (for markdown)
    title = None
    lines = content.split("\n")
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
    
    return ParsedDocument(
        path=str(path),
        title=title or path.stem,
        content=content,
        format=path.suffix.lower().lstrip("."),
        metadata={
            "size_bytes": path.stat().st_size,
            "filename": path.name,
        },
    )


def parse_csv(path: Path, delimiter: str = ",") -> ParsedDocument:
    """Parse a CSV/TSV file to markdown table."""
    content = path.read_text(encoding="utf-8", errors="ignore")
    
    try:
        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        rows = list(reader)
        
        if not rows:
            return ParsedDocument(
                path=str(path),
                title=path.stem,
                content="(empty file)",
                format="csv",
                metadata={"filename": path.name, "rows": 0},
            )
        
        # Convert to markdown table
        md_lines = []
        
        # Header
        header = rows[0]
        md_lines.append("| " + " | ".join(header) + " |")
        md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        
        # Data rows
        for row in rows[1:]:
            # Pad row if needed
            while len(row) < len(header):
                row.append("")
            md_lines.append("| " + " | ".join(row[:len(header)]) + " |")
        
        markdown = "\n".join(md_lines)
        
        return ParsedDocument(
            path=str(path),
            title=path.stem,
            content=markdown,
            format="csv" if delimiter == "," else "tsv",
            metadata={
                "filename": path.name,
                "rows": len(rows) - 1,
                "columns": len(header),
                "headers": header,
            },
        )
    except Exception as e:
        # Fallback to plain text
        return ParsedDocument(
            path=str(path),
            title=path.stem,
            content=content,
            format="csv",
            metadata={"filename": path.name, "parse_error": str(e)},
        )


def parse_json(path: Path) -> ParsedDocument:
    """Parse a JSON file to readable format."""
    content = path.read_text(encoding="utf-8", errors="ignore")
    
    try:
        data = json.loads(content)
        
        # Pretty-print JSON as code block
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        markdown = f"```json\n{formatted}\n```"
        
        # Try to extract title from common fields
        title = None
        if isinstance(data, dict):
            title = data.get("title") or data.get("name") or data.get("id")
        
        return ParsedDocument(
            path=str(path),
            title=str(title) if title else path.stem,
            content=markdown,
            format="json",
            metadata={
                "filename": path.name,
                "type": type(data).__name__,
                "size_bytes": path.stat().st_size,
            },
        )
    except json.JSONDecodeError as e:
        return ParsedDocument(
            path=str(path),
            title=path.stem,
            content=content,
            format="json",
            metadata={"filename": path.name, "parse_error": str(e)},
        )


def parse_with_docling(path: Path) -> ParsedDocument | None:
    """Parse a document using Docling (PDF, DOCX, XLSX, PPTX, HTML)."""
    if not HAS_DOCLING:
        return None
    
    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
        
        # Export to markdown
        content = result.document.export_to_markdown()
        
        # Get metadata
        metadata = {
            "filename": path.name,
            "size_bytes": path.stat().st_size,
        }
        
        # Try to get title from document metadata
        title = None
        if hasattr(result.document, "title") and result.document.title:
            title = result.document.title
        
        return ParsedDocument(
            path=str(path),
            title=title or path.stem,
            content=content,
            format=path.suffix.lower().lstrip("."),
            metadata=metadata,
        )
        
    except Exception as e:
        # Return error document instead of None for debugging
        return ParsedDocument(
            path=str(path),
            title=path.stem,
            content=f"Error parsing document: {e}",
            format=path.suffix.lower().lstrip("."),
            metadata={"filename": path.name, "error": str(e)},
        )


def parse_document(path: str | Path) -> ParsedDocument | None:
    """
    Parse a document file.
    
    Supports natively:
    - Plain text: .txt, .md, .rst
    - Data: .json, .yaml, .yml, .csv, .tsv
    
    With Docling:
    - Office: .pdf, .docx, .doc, .pptx, .xlsx, .xls
    - Web: .html, .htm
    
    Args:
        path: Path to document
        
    Returns:
        ParsedDocument or None on error
    """
    path = Path(path)
    
    if not path.exists():
        return None
    
    suffix = path.suffix.lower()
    
    # CSV/TSV
    if suffix == ".csv":
        try:
            return parse_csv(path, delimiter=",")
        except Exception:
            return None
    
    if suffix == ".tsv":
        try:
            return parse_csv(path, delimiter="\t")
        except Exception:
            return None
    
    # JSON
    if suffix == ".json":
        try:
            return parse_json(path)
        except Exception:
            return None
    
    # Plain text formats
    if suffix in NATIVE_TEXT_FORMATS:
        try:
            return parse_plain_text(path)
        except Exception:
            return None
    
    # Docling formats
    if suffix in DOCLING_FORMATS:
        if not HAS_DOCLING:
            # Fallback: try to read as text for HTML
            if suffix in {".html", ".htm"}:
                try:
                    return parse_plain_text(path)
                except:
                    pass
            return None
        return parse_with_docling(path)
    
    # Unknown format - try plain text
    try:
        return parse_plain_text(path)
    except:
        return None


def parse_directory(
    directory: str | Path,
    recursive: bool = True,
    extensions: set[str] | None = None,
) -> Iterator[ParsedDocument]:
    """
    Parse all documents in a directory.
    
    Args:
        directory: Directory path
        recursive: Search subdirectories
        extensions: File extensions to include (default: all supported)
        
    Yields:
        ParsedDocument objects
    """
    directory = Path(directory)
    
    if not directory.is_dir():
        return
    
    extensions = extensions or get_supported_formats()
    
    # Normalize extensions
    extensions = {ext.lower().lstrip(".") for ext in extensions}
    
    pattern = "**/*" if recursive else "*"
    
    for path in directory.glob(pattern):
        if path.is_file():
            suffix = path.suffix.lower().lstrip(".")
            if suffix in extensions:
                doc = parse_document(path)
                if doc:
                    yield doc


def estimate_parse_time(path: str | Path) -> float:
    """Estimate parsing time in seconds based on file size and type."""
    path = Path(path)
    if not path.exists():
        return 0
    
    size_mb = path.stat().st_size / (1024 * 1024)
    suffix = path.suffix.lower()
    
    # Base estimates (seconds per MB)
    if suffix in NATIVE_TEXT_FORMATS:
        return size_mb * 0.1  # Very fast
    elif suffix == ".pdf":
        return size_mb * 3.0 + 2.0  # PDFs are slow, plus model loading
    elif suffix in {".docx", ".doc"}:
        return size_mb * 1.5 + 1.0
    elif suffix in {".pptx", ".ppt"}:
        return size_mb * 2.0 + 1.0
    elif suffix in {".xlsx", ".xls"}:
        return size_mb * 1.5 + 1.0
    else:
        return size_mb * 0.5


# Format descriptions for UI
FORMAT_INFO = {
    ".txt": ("Text", "Plain text file"),
    ".md": ("Markdown", "Markdown document"),
    ".markdown": ("Markdown", "Markdown document"),
    ".rst": ("reStructuredText", "Python documentation format"),
    ".json": ("JSON", "JavaScript Object Notation"),
    ".yaml": ("YAML", "YAML configuration"),
    ".yml": ("YAML", "YAML configuration"),
    ".csv": ("CSV", "Comma-separated values"),
    ".tsv": ("TSV", "Tab-separated values"),
    ".pdf": ("PDF", "Portable Document Format"),
    ".docx": ("Word", "Microsoft Word document"),
    ".doc": ("Word", "Microsoft Word document (legacy)"),
    ".pptx": ("PowerPoint", "Microsoft PowerPoint"),
    ".ppt": ("PowerPoint", "Microsoft PowerPoint (legacy)"),
    ".xlsx": ("Excel", "Microsoft Excel spreadsheet"),
    ".xls": ("Excel", "Microsoft Excel spreadsheet (legacy)"),
    ".html": ("HTML", "Web page"),
    ".htm": ("HTML", "Web page"),
}
