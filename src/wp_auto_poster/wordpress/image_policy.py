"""Pure image placement and media-pool policy helpers."""

from __future__ import annotations

INLINE_IMAGE_RANDOM_POOL_MIN_SIZE = 50
INLINE_IMAGE_RANDOM_POOL_BUFFER = 10
INLINE_IMAGE_RANDOM_POOL_MAX_SIZE = 500


def get_inline_image_random_pool_size(
    topic_count: int,
    images_per_post: int = 3,
    min_pool: int = INLINE_IMAGE_RANDOM_POOL_MIN_SIZE,
    buffer: int = INLINE_IMAGE_RANDOM_POOL_BUFFER,
    max_pool: int = INLINE_IMAGE_RANDOM_POOL_MAX_SIZE,
) -> int:
    """Return the media scan pool size needed for no-repeat inline images."""
    needed = max(0, int(topic_count) * int(images_per_post))
    desired = max(min_pool, needed + buffer)
    return min(desired, max_pool)


def pick_evenly_spaced_indices(total: int, slots: int) -> list[int]:
    if total <= 0 or slots <= 0:
        return []
    if total <= slots:
        return list(range(total))
    if slots == 1:
        return [total // 2]

    picked: list[int] = []
    used: set[int] = set()
    for pos in range(slots):
        raw = int((pos * (total - 1) / (slots - 1)) + 0.5)
        candidates = [raw]
        for offset in range(1, total):
            candidates.append(raw - offset)
            candidates.append(raw + offset)
        for candidate in candidates:
            if 0 <= candidate < total and candidate not in used:
                picked.append(candidate)
                used.add(candidate)
                break
    return sorted(picked)


def get_inset_heading_candidates(total: int) -> list[int]:
    """Return heading indices that avoid the first and last safe headings."""
    if total <= 0:
        return []
    if total <= 2:
        return list(range(total))
    return list(range(1, total - 1))


def pick_inset_evenly_spaced_indices(total: int, slots: int) -> list[int]:
    candidates = get_inset_heading_candidates(total)
    if slots <= 0 or not candidates:
        return []
    if len(candidates) <= slots:
        return candidates
    return [
        candidates[idx]
        for idx in pick_evenly_spaced_indices(len(candidates), slots)
    ]


def select_even_candidates(indices: list[int], limit: int) -> list[int]:
    ordered = sorted(set(indices))
    if limit <= 0 or not ordered:
        return []
    if len(ordered) <= limit:
        return ordered
    return [ordered[idx] for idx in pick_evenly_spaced_indices(len(ordered), limit)]
