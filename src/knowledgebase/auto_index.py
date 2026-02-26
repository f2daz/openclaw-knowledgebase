"""Auto-indexing: Watch a folder for new documents and add them to the KB."""

import os
import time
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from knowledgebase.client import KnowledgeBase
from knowledgebase.ingest.docling_parser import parse_document
from knowledgebase.ingest.chunker import chunk_text


# Supported file extensions
SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt', '.md', '.html', '.epub'}

# Default inbox path
DEFAULT_INBOX = Path.home() / "clawd" / "kb-inbox"


class IndexedFilesTracker:
    """Track which files have been indexed to avoid duplicates."""
    
    def __init__(self, tracker_path: Path | None = None):
        self.tracker_path = tracker_path or (DEFAULT_INBOX / ".indexed.json")
        self.indexed: dict[str, dict] = self._load()
    
    def _load(self) -> dict:
        if self.tracker_path.exists():
            try:
                return json.loads(self.tracker_path.read_text())
            except Exception:
                return {}
        return {}
    
    def _save(self):
        self.tracker_path.parent.mkdir(parents=True, exist_ok=True)
        self.tracker_path.write_text(json.dumps(self.indexed, indent=2))
    
    def _file_hash(self, path: Path) -> str:
        """Get hash of file content for change detection."""
        return hashlib.md5(path.read_bytes()).hexdigest()
    
    def is_indexed(self, path: Path) -> bool:
        """Check if file is already indexed (and unchanged)."""
        key = str(path.absolute())
        if key not in self.indexed:
            return False
        
        # Check if file changed
        current_hash = self._file_hash(path)
        return self.indexed[key].get('hash') == current_hash
    
    def mark_indexed(self, path: Path, source_id: str | int):
        """Mark file as indexed."""
        key = str(path.absolute())
        self.indexed[key] = {
            'hash': self._file_hash(path),
            'source_id': str(source_id),
            'indexed_at': datetime.now().isoformat(),
        }
        self._save()
    
    def get_source_id(self, path: Path) -> str | None:
        """Get source_id for an indexed file."""
        key = str(path.absolute())
        return self.indexed.get(key, {}).get('source_id')


class InboxHandler(FileSystemEventHandler):
    """Handle new files in the inbox folder."""
    
    def __init__(
        self,
        kb: KnowledgeBase,
        tracker: IndexedFilesTracker,
        on_indexed: Callable[[Path, int], None] | None = None,
        on_error: Callable[[Path, Exception], None] | None = None,
    ):
        self.kb = kb
        self.tracker = tracker
        self.on_indexed = on_indexed
        self.on_error = on_error
        self._processing = set()  # Prevent duplicate processing
    
    def _should_process(self, path: Path) -> bool:
        """Check if file should be processed."""
        if not path.is_file():
            return False
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False
        if path.name.startswith('.'):
            return False
        if str(path) in self._processing:
            return False
        return True
    
    def _process_file(self, path: Path):
        """Process a single file and add to KB."""
        if not self._should_process(path):
            return
        
        # Check if already indexed
        if self.tracker.is_indexed(path):
            return
        
        self._processing.add(str(path))
        
        try:
            # Parse document
            content, metadata = parse_document(str(path))
            if not content or not content.strip():
                raise ValueError(f"No content extracted from {path.name}")
            
            # Create source
            source = self.kb.add_source(
                url=f"file://{path.absolute()}",
                title=metadata.get('title') or path.stem,
                source_type="document",
                metadata={
                    'filename': path.name,
                    'extension': path.suffix,
                    'auto_indexed': True,
                    **metadata,
                },
            )
            
            if not source:
                raise ValueError("Failed to create source")
            
            # Chunk and add
            chunks = chunk_text(content, source_url=str(path))
            chunk_count = 0
            
            for chunk_data in chunks:
                chunk = self.kb.add_chunk(
                    source_id=source.id,
                    content=chunk_data['content'],
                    chunk_index=chunk_data.get('chunk_index', 0),
                )
                if chunk:
                    chunk_count += 1
            
            # Mark as indexed
            self.tracker.mark_indexed(path, source.id)
            
            if self.on_indexed:
                self.on_indexed(path, chunk_count)
                
        except Exception as e:
            if self.on_error:
                self.on_error(path, e)
        finally:
            self._processing.discard(str(path))
    
    def on_created(self, event):
        if isinstance(event, FileCreatedEvent):
            # Wait a moment for file to be fully written
            time.sleep(0.5)
            self._process_file(Path(event.src_path))
    
    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent):
            path = Path(event.src_path)
            # Re-index if file changed
            if not self.tracker.is_indexed(path):
                time.sleep(0.5)
                self._process_file(path)


def watch_inbox(
    inbox_path: Path | str | None = None,
    on_indexed: Callable[[Path, int], None] | None = None,
    on_error: Callable[[Path, Exception], None] | None = None,
) -> Observer:
    """
    Start watching an inbox folder for new documents.
    
    Args:
        inbox_path: Path to watch (default: ~/clawd/kb-inbox)
        on_indexed: Callback(path, chunk_count) when file is indexed
        on_error: Callback(path, exception) on errors
        
    Returns:
        Observer instance (call .stop() to stop watching)
        
    Example:
        >>> def on_new(path, chunks):
        ...     print(f"Indexed {path.name}: {chunks} chunks")
        >>> observer = watch_inbox(on_indexed=on_new)
        >>> # ... later ...
        >>> observer.stop()
    """
    inbox = Path(inbox_path) if inbox_path else DEFAULT_INBOX
    inbox.mkdir(parents=True, exist_ok=True)
    
    kb = KnowledgeBase()
    tracker = IndexedFilesTracker(inbox / ".indexed.json")
    handler = InboxHandler(kb, tracker, on_indexed, on_error)
    
    observer = Observer()
    observer.schedule(handler, str(inbox), recursive=False)
    observer.start()
    
    return observer


def index_inbox_once(
    inbox_path: Path | str | None = None,
    on_indexed: Callable[[Path, int], None] | None = None,
    on_error: Callable[[Path, Exception], None] | None = None,
) -> tuple[int, int]:
    """
    Index all unindexed files in inbox (one-shot, no watching).
    
    Returns:
        Tuple of (files_indexed, files_failed)
    """
    inbox = Path(inbox_path) if inbox_path else DEFAULT_INBOX
    if not inbox.exists():
        inbox.mkdir(parents=True, exist_ok=True)
        return 0, 0
    
    kb = KnowledgeBase()
    tracker = IndexedFilesTracker(inbox / ".indexed.json")
    handler = InboxHandler(kb, tracker, on_indexed, on_error)
    
    indexed = 0
    failed = 0
    
    for path in inbox.iterdir():
        if path.suffix.lower() in SUPPORTED_EXTENSIONS and not path.name.startswith('.'):
            if not tracker.is_indexed(path):
                try:
                    handler._process_file(path)
                    indexed += 1
                except Exception:
                    failed += 1
    
    return indexed, failed


if __name__ == "__main__":
    # CLI for testing
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto-index documents")
    parser.add_argument("--inbox", help="Inbox path", default=str(DEFAULT_INBOX))
    parser.add_argument("--watch", action="store_true", help="Watch for new files")
    parser.add_argument("--once", action="store_true", help="Index once and exit")
    args = parser.parse_args()
    
    def on_indexed(path, chunks):
        print(f"✅ Indexed: {path.name} ({chunks} chunks)")
    
    def on_error(path, e):
        print(f"❌ Error: {path.name}: {e}")
    
    if args.once:
        indexed, failed = index_inbox_once(args.inbox, on_indexed, on_error)
        print(f"\nDone: {indexed} indexed, {failed} failed")
    elif args.watch:
        print(f"👀 Watching {args.inbox} for new documents...")
        print("   Press Ctrl+C to stop")
        observer = watch_inbox(args.inbox, on_indexed, on_error)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            observer.join()
            print("\nStopped.")
    else:
        parser.print_help()
