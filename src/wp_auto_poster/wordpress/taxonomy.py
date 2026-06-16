"""WordPress Classic Editor taxonomy helpers."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

LogFunc = Callable[[str, str], None]


@dataclass
class TaxonomyRuntime:
    config: dict
    log_func: LogFunc

    def log(self, message: str, level: str = "info") -> None:
        self.log_func(message, level)


def select_first_category(page: Any, runtime: TaxonomyRuntime) -> bool:
    """Tick category cấu hình (hoặc fallback) trong Classic Editor.

    Bulletproof timeout: mọi locator action đều bound timeout (≤ 1.5s) để
    không hang khi DOM checklist có nhiều cấp con / element bị overlap.
    """
    runtime.log("Đang chọn danh mục...", "info")
    deadline = time.time() + 15  # tổng deadline 15s — quá thì bỏ qua

    try:
        def normalize_text(value: str) -> str:
            value = (value or "").strip().lower()
            value = "".join(
                c for c in unicodedata.normalize("NFD", value)
                if unicodedata.category(c) != "Mn"
            )
            return re.sub(r"\s+", " ", value)

        configured_category = (runtime.config.get("category_name") or "Tin tức").strip()
        preferred_names = [configured_category]
        if normalize_text(configured_category) != normalize_text("Tin tức"):
            preferred_names.append("Tin tức")

        # Switch to "All categories" tab to avoid selecting from "Most Used".
        try:
            all_tab = page.locator("#category-tabs a[href='#category-all']").first
            if all_tab.count() > 0:
                all_tab.click(timeout=1500)
                time.sleep(0.3)
        except Exception:
            pass

        # Đọc 1 lần qua JS — nhanh, không bị multiple round-trip locator,
        # không bao giờ hang vì JS chạy synchronously trong page context.
        try:
            rows_data = page.evaluate(
                """() => {
                    const out = [];
                    const lists = ['#categorychecklist', '#categorychecklist-pop'];
                    for (const sel of lists) {
                        const root = document.querySelector(sel);
                        if (!root) continue;
                        const items = root.querySelectorAll('li');
                        items.forEach((li, idx) => {
                            const cb = li.querySelector("input[type='checkbox']");
                            const lb = li.querySelector('label');
                            if (!cb || !lb) return;
                            out.push({
                                listSel: sel,
                                index: idx,
                                cbId: cb.id || '',
                                cbValue: cb.value || '',
                                checked: !!cb.checked,
                                label: (lb.textContent || '').trim(),
                            });
                        });
                    }
                    return out;
                }"""
            ) or []
        except Exception as e:
            runtime.log(f"Không đọc được danh sách category: {e}", "warning")
            return False

        if not rows_data:
            runtime.log("No categories found", "warning")
            return False

        runtime.log(f"Tìm thấy {len(rows_data)} danh mục", "info")

        # Match: ưu tiên exact normalize → contains
        target = None
        for target_name in preferred_names:
            target_norm = normalize_text(target_name)
            target = next(
                (r for r in rows_data if normalize_text(r["label"]) == target_norm),
                None,
            )
            if target:
                break
            target = next(
                (r for r in rows_data if target_norm in normalize_text(r["label"])),
                None,
            )
            if target:
                break

        if time.time() > deadline:
            runtime.log("Category selection vượt deadline — bỏ qua", "warning")
            return False

        if target:
            # Tick + uncheck others bằng JS 1 round-trip — tránh nhiều
            # locator.check() mỗi cái 30s timeout default.
            try:
                ok = page.evaluate(
                    """({ cbId, cbValue }) => {
                        const lists = ['#categorychecklist', '#categorychecklist-pop'];
                        let target = null;
                        const allCbs = [];
                        for (const sel of lists) {
                            const root = document.querySelector(sel);
                            if (!root) continue;
                            root.querySelectorAll("input[type='checkbox']").forEach(cb => {
                                allCbs.push(cb);
                                if ((cbId && cb.id === cbId) ||
                                    (cbValue && cb.value === cbValue)) {
                                    target = cb;
                                }
                            });
                        }
                        if (!target) return { ok: false, reason: 'target not found' };
                        // Uncheck all others, check target
                        for (const cb of allCbs) {
                            const want = (cb === target);
                            if (cb.checked !== want) {
                                cb.checked = want;
                                cb.dispatchEvent(new Event('change', { bubbles: true }));
                                cb.dispatchEvent(new Event('click', { bubbles: true }));
                            }
                        }
                        // Scroll target into view nhẹ nhàng
                        try { target.scrollIntoView({ block: 'center' }); } catch (e) {}
                        return { ok: target.checked, reason: 'set' };
                    }""",
                    {"cbId": target["cbId"], "cbValue": target["cbValue"]},
                )
                if ok and ok.get("ok"):
                    runtime.log(f"Selected category: {target['label']}", "success")
                    return True
                runtime.log(
                    f"JS check fail ({ok.get('reason') if ok else 'no result'}), "
                    f"thử fallback locator",
                    "warning",
                )
            except Exception as e:
                runtime.log(f"JS category set error: {e} — thử fallback", "warning")

            # Fallback locator-based với timeout chặt
            if time.time() > deadline:
                runtime.log("Vượt deadline trước fallback — bỏ qua", "warning")
                return False
            try:
                cb_sel = (
                    f"#{target['cbId']}" if target["cbId"]
                    else f"input[type='checkbox'][value='{target['cbValue']}']"
                )
                cb = page.locator(cb_sel).first
                cb.scroll_into_view_if_needed(timeout=1500)
                cb.check(force=True, timeout=2000)
                runtime.log(f"Selected (locator): {target['label']}", "success")
                return True
            except Exception as e:
                runtime.log(f"Locator check fail: {e}", "warning")

        # Fallback: tick first unchecked — cũng qua JS để tránh hang
        if time.time() > deadline:
            return False
        try:
            picked_label = page.evaluate(
                """() => {
                    const lists = ['#categorychecklist', '#categorychecklist-pop'];
                    for (const sel of lists) {
                        const root = document.querySelector(sel);
                        if (!root) continue;
                        const cbs = root.querySelectorAll("input[type='checkbox']");
                        for (const cb of cbs) {
                            if (!cb.checked) {
                                cb.checked = true;
                                cb.dispatchEvent(new Event('change', { bubbles: true }));
                                cb.dispatchEvent(new Event('click', { bubbles: true }));
                                const li = cb.closest('li');
                                const lb = li ? li.querySelector('label') : null;
                                return (lb && lb.textContent || '').trim();
                            }
                        }
                    }
                    return null;
                }"""
            )
            if picked_label:
                runtime.log(f"Selected fallback category: {picked_label}", "success")
                return True
        except Exception:
            pass

        runtime.log("Category already selected hoặc không có lựa chọn khác", "info")
        return True

    except Exception as e:
        runtime.log(f"Error selecting category: {e}", "warning")
        return False

def add_post_tags(page: Any, tags: str, runtime: TaxonomyRuntime) -> bool:
    """Add tags to WordPress post (Classic Editor).
    
    Args:
        page: Playwright page object
        tags: Comma-separated tags string
    """
    try:
        if not tags or not tags.strip():
            runtime.log("No tags to add", "info")
            return True
        
        runtime.log(f"Adding tags: {tags[:50]}...", "info")
        
        # Scroll to Tags section
        try:
            tags_box = page.locator("#tagsdiv-post_tag, #tagsdiv, .tagsdiv").first
            if tags_box.is_visible(timeout=2000):
                tags_box.scroll_into_view_if_needed()
                time.sleep(0.5)
        except:
            pass
        
        # Find the tags input field
        tag_input_selectors = [
            "#new-tag-post_tag",
            "input.newtag",
            "#newtag",
            "input[name='newtag[post_tag]']",
            ".tagsdiv input[type='text']"
        ]
        
        tag_input = None
        for selector in tag_input_selectors:
            try:
                input_el = page.locator(selector).first
                if input_el.is_visible(timeout=1000):
                    tag_input = input_el
                    runtime.log(f"Found tags input: {selector}", "info")
                    break
            except:
                continue
        
        if not tag_input:
            runtime.log("Could not find tags input field", "warning")
            return False
        
        # Clear and fill the tags input
        tag_input.click()
        tag_input.fill("")
        time.sleep(0.2)
        tag_input.fill(tags.strip())
        time.sleep(0.3)
        
        # Click the "Add" / "Thêm" button
        add_button_selectors = [
            "input.tagadd",
            "button.tagadd",
            "#tagsdiv-post_tag .tagadd",
            "input[value='Thêm']",
            "input[value='Add']",
            ".tagsdiv input[type='button']"
        ]
        
        for selector in add_button_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    runtime.log("Clicked Add tags button", "success")
                    time.sleep(0.5)
                    
                    # Verify tags were added by checking tag cloud
                    try:
                        tag_cloud = page.locator(".tagchecklist, .the-tags").first
                        if tag_cloud.is_visible(timeout=1000):
                            runtime.log("Tags added successfully", "success")
                    except:
                        pass
                    
                    return True
            except:
                continue
        
        # Try JavaScript fallback to click the add button
        try:
            page.evaluate("""
                () => {
                    const addBtn = document.querySelector('.tagadd, input.tagadd');
                    if (addBtn) addBtn.click();
                }
            """)
            runtime.log("Clicked Add tags button via JS", "success")
            time.sleep(0.5)
            return True
        except:
            pass
        
        runtime.log("Could not find Add tags button", "warning")
        return False
        
    except Exception as e:
        runtime.log(f"Error adding tags: {e}", "warning")
        return False
