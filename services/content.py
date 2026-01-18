"""
Content Generation Service
===========================
Unified interface for content generation across different AI providers.
"""

from typing import Optional, Callable
from config.settings import state, add_log
from config.prompts import clean_gemini_content


def generate_content(
    title: str, 
    keyword: str, 
    page=None,
    provider: str = None
) -> Optional[str]:
    """
    Generate content using the configured AI provider.
    
    Args:
        title: Post title
        keyword: SEO keyword
        page: Playwright page (required for gemini_web)
        provider: Override AI provider (optional)
    
    Returns:
        Generated HTML content or None
    """
    ai_provider = provider or state.config.get("ai_provider", "gemini_api")
    
    add_log(f"Generating content with {ai_provider}...", "info")
    
    content = None
    
    if ai_provider == "gemini_api":
        content = _generate_with_gemini_api(title, keyword)
    elif ai_provider == "gemini_web":
        if page is None:
            add_log("Page required for Gemini Web", "error")
            return None
        content = _generate_with_gemini_web(page, title, keyword)
    elif ai_provider == "ollama":
        content = _generate_with_ollama(title, keyword)
    else:
        add_log(f"Unknown AI provider: {ai_provider}", "error")
        return None
    
    # Clean content if from Gemini
    if content and "gemini" in ai_provider:
        content = clean_gemini_content(content)
    
    return content


def _generate_with_gemini_api(title: str, keyword: str) -> Optional[str]:
    """Generate content using Gemini API."""
    try:
        from ai_providers.gemini_api import generate_content_gemini, GEMINI_AVAILABLE
        
        if not GEMINI_AVAILABLE:
            add_log("Gemini API not available", "error")
            return None
        
        api_key = state.config.get("gemini_api_key", "")
        if not api_key:
            add_log("Gemini API key not configured", "error")
            return None
        
        return generate_content_gemini(title, keyword, api_key, add_log)
        
    except Exception as e:
        add_log(f"Gemini API error: {e}", "error")
        return None


def _generate_with_ollama(title: str, keyword: str) -> Optional[str]:
    """Generate content using Ollama."""
    try:
        from ai_providers.ollama import generate_content_ollama, OLLAMA_AVAILABLE
        
        if not OLLAMA_AVAILABLE:
            add_log("Ollama not available", "error")
            return None
        
        return generate_content_ollama(title, keyword, state.config, add_log)
        
    except Exception as e:
        add_log(f"Ollama error: {e}", "error")
        return None


def _generate_with_gemini_web(page, title: str, keyword: str) -> Optional[str]:
    """Generate content using Gemini Web interface."""
    # This will be imported from app.py later
    # For now, return None and let app.py handle it
    add_log("Gemini Web generation delegated to app.py", "info")
    return None


def batch_generate_content(
    topics: list,
    page=None,
    on_progress: Callable[[int, int], None] = None
) -> list:
    """
    Generate content for multiple topics.
    
    Args:
        topics: List of topic dicts with 'title' and 'keyword'
        page: Playwright page (for gemini_web)
        on_progress: Callback(current, total) for progress updates
    
    Returns:
        List of generated contents (None for failed ones)
    """
    contents = []
    total = len(topics)
    
    for i, topic in enumerate(topics):
        title = topic.get("title", "")
        keyword = topic.get("keyword", "")
        
        if on_progress:
            on_progress(i + 1, total)
        
        if not title or not keyword:
            add_log(f"Skipping topic {i + 1}: missing title/keyword", "warning")
            contents.append(None)
            continue
        
        content = generate_content(title, keyword, page)
        contents.append(content)
    
    return contents
