"""
Image metadata reading and writing using pyexiv2.
"""

from dataclasses import dataclass
from pathlib import Path

import pyexiv2


@dataclass
class KeywordResult:
    """Result of keyword read/write operation."""

    success: bool
    keywords: list[str]
    error: str | None = None


# Tags for keyword storage
IPTC_KEYWORDS_TAG = 'Iptc.Application2.Keywords'
XMP_SUBJECT_TAG = 'Xmp.dc.subject'

# Formats that support IPTC
IPTC_FORMATS = {'.jpg', '.jpeg', '.tiff', '.tif'}


def read_keywords(image_path: str) -> KeywordResult:
    """
    Read existing keywords from image metadata.

    Checks both IPTC and XMP, merges and deduplicates.
    """
    try:
        img = pyexiv2.Image(image_path)

        keywords = set()

        # Read IPTC keywords
        iptc = img.read_iptc()
        if IPTC_KEYWORDS_TAG in iptc:
            value = iptc[IPTC_KEYWORDS_TAG]
            if isinstance(value, list):
                keywords.update(value)
            elif isinstance(value, str):
                keywords.add(value)

        # Read XMP subject
        xmp = img.read_xmp()
        if XMP_SUBJECT_TAG in xmp:
            value = xmp[XMP_SUBJECT_TAG]
            if isinstance(value, list):
                keywords.update(value)
            elif isinstance(value, str):
                keywords.add(value)

        img.close()

        return KeywordResult(success=True, keywords=list(keywords))

    except Exception as e:
        return KeywordResult(success=False, keywords=[], error=str(e))


def write_keywords(
    image_path: str, keywords: list[str], append: bool = True
) -> KeywordResult:
    """
    Write keywords to image metadata.

    Args:
        image_path: Path to image file
        keywords: Keywords to write
        append: If True, merge with existing keywords; if False, replace

    Writes to both IPTC and XMP for maximum compatibility.
    PNG files only get XMP (IPTC not supported).
    """
    path = Path(image_path)
    suffix = path.suffix.lower()

    try:
        img = pyexiv2.Image(image_path)

        # Get existing keywords if appending
        if append:
            existing = read_keywords(image_path)
            if existing.success:
                all_keywords = list(set(existing.keywords + keywords))
            else:
                all_keywords = keywords
        else:
            all_keywords = keywords

        # Deduplicate and sort
        all_keywords = sorted(set(kw.lower().strip() for kw in all_keywords))

        # Write XMP (works for all formats)
        img.modify_xmp({XMP_SUBJECT_TAG: all_keywords})

        # Write IPTC (only for supported formats)
        if suffix in IPTC_FORMATS:
            img.modify_iptc({IPTC_KEYWORDS_TAG: all_keywords})

        img.close()

        return KeywordResult(success=True, keywords=all_keywords)

    except Exception as e:
        return KeywordResult(success=False, keywords=[], error=str(e))
