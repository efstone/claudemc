"""
Main processor that orchestrates Claude analysis and metadata writing.
"""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from .claude import analyze_image
from .metadata import write_keywords
from .models import ProcessedImage


SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp'}


@dataclass
class ProcessingResult:
    """Result of processing a single image."""

    file_path: str
    success: bool
    keywords: list[str]
    was_skipped: bool = False
    error: str | None = None


def get_file_hash(file_path: str) -> str:
    """Calculate SHA-256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def process_image(
    image_path: str,
    is_minecraft: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> ProcessingResult:
    """
    Process a single image: analyze with Claude, write keywords to metadata.

    Args:
        image_path: Path to image file
        is_minecraft: Use Minecraft-specific analysis
        force: Reprocess even if already processed
        dry_run: Don't actually write, just analyze

    Returns:
        ProcessingResult with status and keywords
    """
    path = Path(image_path)

    if not path.exists():
        return ProcessingResult(
            file_path=str(path), success=False, keywords=[], error="File not found"
        )

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return ProcessingResult(
            file_path=str(path),
            success=False,
            keywords=[],
            error=f"Unsupported format: {path.suffix}",
        )

    file_hash = get_file_hash(str(path))
    file_size = path.stat().st_size

    # Check if already processed (by path only - use --force to reprocess)
    if not force:
        existing = ProcessedImage.objects.filter(
            file_path=str(path), success=True
        ).first()

        if existing:
            return ProcessingResult(
                file_path=str(path),
                success=True,
                keywords=existing.keywords,
                was_skipped=True,
            )

    # Analyze with Claude
    analysis = analyze_image(str(path), is_minecraft=is_minecraft)

    if not analysis.success:
        ProcessedImage.objects.update_or_create(
            file_path=str(path),
            defaults={
                'file_hash': file_hash,
                'file_size': file_size,
                'keywords': [],
                'is_minecraft': is_minecraft,
                'success': False,
                'error_message': analysis.error,
                'tokens_used': analysis.tokens_used,
            },
        )
        return ProcessingResult(
            file_path=str(path), success=False, keywords=[], error=analysis.error
        )

    # Write metadata (unless dry run)
    if not dry_run:
        write_result = write_keywords(str(path), analysis.keywords, append=True)

        if not write_result.success:
            ProcessedImage.objects.update_or_create(
                file_path=str(path),
                defaults={
                    'file_hash': file_hash,
                    'file_size': file_size,
                    'keywords': analysis.keywords,
                    'is_minecraft': is_minecraft,
                    'success': False,
                    'error_message': f"Metadata write failed: {write_result.error}",
                    'tokens_used': analysis.tokens_used,
                },
            )
            return ProcessingResult(
                file_path=str(path),
                success=False,
                keywords=analysis.keywords,
                error=f"Metadata write failed: {write_result.error}",
            )

        final_keywords = write_result.keywords
    else:
        final_keywords = analysis.keywords

    # Record success in DB (dry-run skips both file metadata and DB writes)
    if not dry_run:
        ProcessedImage.objects.update_or_create(
            file_path=str(path),
            defaults={
                'file_hash': file_hash,
                'file_size': file_size,
                'keywords': final_keywords,
                'is_minecraft': is_minecraft,
                'success': True,
                'error_message': None,
                'tokens_used': analysis.tokens_used,
            },
        )

    return ProcessingResult(file_path=str(path), success=True, keywords=final_keywords)


def process_folder(
    folder_path: str,
    is_minecraft: bool = False,
    recursive: bool = True,
    force: bool = False,
    dry_run: bool = False,
    delay: float = 0.5,
    callback=None,
) -> list[ProcessingResult]:
    """
    Process all images in a folder.

    Args:
        folder_path: Path to folder
        is_minecraft: Use Minecraft analysis mode
        recursive: Process subdirectories
        force: Reprocess already-processed images
        dry_run: Don't write metadata
        delay: Seconds between API calls
        callback: Optional callback(result) called after each image

    Returns:
        List of ProcessingResult for each image
    """
    path = Path(folder_path)

    if not path.is_dir():
        return [
            ProcessingResult(
                file_path=str(path), success=False, keywords=[], error="Not a directory"
            )
        ]

    # Find all images
    pattern = '**/*' if recursive else '*'
    images = [
        f
        for f in path.glob(pattern)
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    results = []
    for i, img_path in enumerate(sorted(images)):
        result = process_image(
            str(img_path), is_minecraft=is_minecraft, force=force, dry_run=dry_run
        )
        results.append(result)

        if callback:
            callback(result)

        # Rate limiting (skip delay for skipped images)
        if not result.was_skipped and i < len(images) - 1:
            time.sleep(delay)

    return results
