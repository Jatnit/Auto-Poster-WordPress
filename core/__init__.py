"""
Core Package
=============
Core functionality for WordPress Auto Poster.
"""

from core.browser import (
    get_browser,
    get_page,
    close_browser,
    is_playwright_available,
)

__all__ = [
    'get_browser',
    'get_page', 
    'close_browser',
    'is_playwright_available',
]
