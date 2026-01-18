import requests
from typing import Optional
from config.prompts import PROMPT_PART1, PROMPT_PART2, CONTACT_SECTION


def check_ollama() -> bool:
    try:
        response = requests.get("http://localhost:11434/api/version", timeout=2)
        return response.status_code == 200
    except:
        return False


OLLAMA_AVAILABLE = check_ollama()


def call_ollama_api(prompt: str, model: str) -> Optional[str]:
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.6, "num_predict": 6000, "num_ctx": 8192}
            },
            timeout=600
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("response", "")
            
            if content.startswith("```html"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            return content.strip()
        return None
    except:
        return None


def generate_content_ollama(title: str, keyword: str, config: dict, log_func) -> Optional[str]:
    try:
        model = config.get("ollama_model", "llama3.1:8b")
        
        if not model or model == "llama3.2":
            model = "llama3.1:8b"
        
        log_func(f"Generating content with Ollama ({model})...", "info")
        log_func("Generating Part 1/2 (800+ words)...", "info")
        
        prompt_part1 = PROMPT_PART1.format(title=title, keyword=keyword)
        part1 = call_ollama_api(prompt_part1, model)
        
        if not part1:
            log_func("Could not generate Part 1", "error")
            return None
        
        word_count_1 = len(part1.split())
        log_func(f"Part 1: {word_count_1} words", "info")
        
        log_func("Generating Part 2/2 (800+ words)...", "info")
        
        prompt_part2 = PROMPT_PART2.format(title=title, keyword=keyword)
        part2 = call_ollama_api(prompt_part2, model)
        
        if not part2:
            log_func("Could not generate Part 2", "error")
            return None
        
        word_count_2 = len(part2.split())
        log_func(f"Part 2: {word_count_2} words", "info")
        
        contact = CONTACT_SECTION.format(keyword=keyword)
        full_content = part1 + "\n\n" + part2 + "\n\n" + contact
        
        total_words = len(full_content.split())
        log_func(f"Total: {total_words} words", "success")
        
        if total_words < 1200:
            log_func(f"Content shorter than expected ({total_words} words)", "warning")
        
        log_func(f"Generated content for: {title}", "success")
        return full_content
        
    except requests.exceptions.Timeout:
        log_func("Ollama timeout - content generation took too long", "error")
        return None
    except Exception as e:
        log_func(f"Ollama error: {e}", "error")
        return None
