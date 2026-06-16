from wp_auto_poster.wordpress.image_policy import (
    get_inline_image_random_pool_size,
    get_inset_heading_candidates,
    pick_evenly_spaced_indices,
    pick_inset_evenly_spaced_indices,
    select_even_candidates,
)


def test_inline_image_pool_size_covers_ten_posts_thirty_images():
    assert get_inline_image_random_pool_size(topic_count=10, images_per_post=3) == 50


def test_inline_image_pool_size_scales_with_large_batches_and_caps():
    assert get_inline_image_random_pool_size(topic_count=100, images_per_post=3) == 310
    assert get_inline_image_random_pool_size(topic_count=200, images_per_post=3) == 500


def test_inset_heading_candidates_avoid_edges_when_possible():
    assert get_inset_heading_candidates(0) == []
    assert get_inset_heading_candidates(2) == [0, 1]
    assert get_inset_heading_candidates(5) == [1, 2, 3]


def test_pick_inset_evenly_spaced_indices_matches_expected_distribution():
    assert pick_inset_evenly_spaced_indices(7, 3) == [1, 3, 5]
    assert pick_inset_evenly_spaced_indices(8, 3) == [1, 4, 6]
    assert pick_inset_evenly_spaced_indices(9, 3) == [1, 4, 7]


def test_select_even_candidates_deduplicates_and_limits_evenly():
    assert pick_evenly_spaced_indices(7, 3) == [0, 3, 6]
    assert select_even_candidates([5, 1, 1, 3, 7], 3) == [1, 5, 7]
