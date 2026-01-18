"""
Gemini API Provider
===================
Content generation using Google Gemini API.
"""

import time
from typing import Optional

from config.prompts import PROMPT_PART1, PROMPT_PART2, CONTACT_SECTION

# Check Gemini availability
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def clean_markdown_code_block(content: str) -> str:
    """Remove markdown code block markers from content."""
    if content.startswith("```html"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()

# ============================================================================
# CONTENT GENERATION
# ============================================================================

def generate_content_gemini(
    title: str, 
    keyword: str, 
    api_key: str,
    log_func,
    max_retries: int = 3
) -> Optional[str]:
    """Generate blog content using Google Gemini API in 2 parts."""
    if not GEMINI_AVAILABLE:
        log_func("Gemini library not available", "error")
        return None
    
    genai.configure(api_key=api_key)
    
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # Generate Part 1
            log_func("Generating Part 1/2 with Gemini...", "info")
            prompt_part1 = PROMPT_PART1.format(title=title, keyword=keyword)
            response1 = model.generate_content(
                prompt_part1,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                )
            )
            part1 = clean_markdown_code_block(response1.text.strip())
            
            word_count_1 = len(part1.split())
            log_func(f"Part 1: {word_count_1} words", "info")
            
            # Generate Part 2
            log_func("Generating Part 2/2 with Gemini...", "info")
            prompt_part2 = PROMPT_PART2.format(title=title, keyword=keyword)
            response2 = model.generate_content(
                prompt_part2,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                )
            )
            part2 = clean_markdown_code_block(response2.text.strip())
            
            word_count_2 = len(part2.split())
            log_func(f"Part 2: {word_count_2} words", "info")
            
            # Combine parts + contact section
            contact = CONTACT_SECTION.format(keyword=keyword)
            full_content = part1 + "\n\n" + part2 + "\n\n" + contact
            
            total_words = len(full_content.split())
            log_func(f"Total: {total_words} words", "success")
            log_func(f"Generated content for: {title}", "success")
            
            return full_content
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                wait_time = 60 * (attempt + 1)
                log_func(f"Rate limit hit. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...", "warning")
                time.sleep(wait_time)
            else:
                log_func(f"Error generating content: {e}", "error")
                return None
    
    log_func(f"Failed to generate content after {max_retries} retries", "error")
    return None
