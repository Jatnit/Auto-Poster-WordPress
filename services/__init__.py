"""
Services Package
=================
Business logic services for WordPress Auto Poster.
"""

from services.content import (
    generate_content,
    batch_generate_content,
)

__all__ = [
    'generate_content',
    'batch_generate_content',
]
