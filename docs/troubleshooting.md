# Troubleshooting

## Pytest Missing

Install project dependencies in the active virtual environment:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Then rerun:

```bash
./scripts/check.sh
```

## Playwright Browser Missing

Install Playwright browsers:

```bash
playwright install
```

## Static Assets Do Not Load

If the UI opens but buttons do not work or the design looks unstyled, verify the static files exist:

```bash
ls static/css static/js
```

Then run the app through Flask, not by opening `templates/index.html` directly:

```bash
python app.py
```

The template expects these files:

- `static/css/app.css`
- `static/js/core.js`
- `static/js/checklist.js`
- `static/js/dialogs.js`
- `static/js/presets.js`
- `static/js/content-list.js`
- `static/js/config.js`
- `static/js/topics.js`
- `static/js/schedule.js`
- `static/js/automation.js`

## Generated Content Fails Minimum Words

The minimum-word validation is centralized in `src/wp_auto_poster/content/validation.py`. If content is below the configured threshold, the generation flow retries before marking the item as failed. Failed items should still appear in the content list so they can be rerendered manually.

Check:

- The configured minimum word count in the UI.
- Provider output length and prompt quality.
- The progress checklist for retry attempts and final failure reason.

## AI Content Contains Logos Or Link Images

Generated content cleanup is centralized in `src/wp_auto_poster/content/cleanup.py`. It removes AI-sourced image/media tags such as `img`, `picture`, `figure`, and `svg` so link logos do not pass the WordPress image check accidentally.

If logos still appear, save the generated HTML snippet and add a regression test in `tests/unit/test_content_cleanup.py` before changing cleanup rules.

## Inline Images Are Missing After Publish

The inline-image workflow is in `src/wp_auto_poster/wordpress/inline_images.py` and image placement policy is in `src/wp_auto_poster/wordpress/image_policy.py`.

Check the UI log for these messages:

- `No images in media library`
- `Select image fail`
- `DOM count mismatch sau Insert`
- final scan/repair messages

Likely causes:

- WordPress media modal loaded slowly.
- Attachment elements exist but are outside the viewport.
- WordPress navigated away while the media modal was still active.
- The content has too few eligible H2/H3 targets before the contact section.
- The selected media was not a valid user-library image.

Mitigation path:

1. Keep browser visible and watch whether the media modal fully loads.
2. Confirm the WordPress media library has enough images for no-repeat selection.
3. Confirm final image placement is above the contact section.
4. Add a focused fake-page test if the issue can be reduced to a helper behavior.

## Images Cluster Near The Top Of The Article

Image target selection is intentionally inset:

- The first image skips the first eligible H2 from the top.
- The final image skips the first eligible H2 from the bottom.
- Contact sections are excluded so images are not inserted below contact information.

If layout still clusters, inspect `src/wp_auto_poster/wordpress/image_policy.py` and add a new policy test before changing behavior.

## WordPress Publish Timestamp Click Times Out

The publish flow is in `src/wp_auto_poster/wordpress/publisher.py`. Timeout symptoms often happen when WordPress reports an element as visible but keeps it outside the viewport or shifts layout during scrolling.

Check:

- Browser zoom level.
- WordPress admin language/theme/plugin overlays.
- Whether another modal or notice is covering the publish box.
- The last route URL after the click attempt.

## Automation Is Slow

Common causes:

- Large media library and no-repeat image search across many attachments.
- Slow WordPress admin responses.
- Provider web UI delays.
- Repeated image repair attempts after DOM mismatch.

Use the progress log to identify whether time is spent in generation, media selection, image insertion, taxonomy, or publish confirmation.

## Python Warnings During Tests

Some warnings are dependency/environment warnings, especially with older Python/OpenSSL combinations. If `./scripts/check.sh` passes, these warnings are not currently blocking. Upgrade Python/dependencies separately from the refactor unless the warning is tied to a failing test.
