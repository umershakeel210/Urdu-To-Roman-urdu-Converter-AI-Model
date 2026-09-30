# Deployment Guide

## Recommended first deployment

Do not begin with thousands of records.

Use this sequence:

1. Run 5 records.
2. Verify all Roman Urdu outputs went into the correct textbox.
3. Verify `Verify & Next` moved to the correct next record.
4. Run 25 records.
5. Inspect logs and screenshots.
6. Run 100 records.
7. Only after successful validation, remove the processing limit.

For testing:

```yaml
automation:
  max_records: 5
```

Then:

```yaml
max_records: 25
```

Then:

```yaml
max_records: 100
```

Finally:

```yaml
max_records: 0
```

## Visible mode

Recommended during development:

```yaml
browser:
  headless: false
```

## Headless mode

Technically supported:

```yaml
browser:
  headless: true
```

However, ChatGPT web sessions, authentication prompts, and website changes are easier to diagnose in visible mode. For production-scale unattended processing, the official OpenAI API is more reliable than browser automation of the ChatGPT website.

## Selector hardening

Before a large run, replace generic auto-detection with exact selectors from your application.

Best examples:

```html
<textarea data-testid="raw-whisper-asr">
<textarea data-testid="human-approved-roman-urdu">
<button data-testid="verify-next">
```

Then configure:

```yaml
source:
  - "textarea[data-testid='raw-whisper-asr']"

target:
  - "textarea[data-testid='human-approved-roman-urdu']"

verify_next:
  - "button[data-testid='verify-next']"
```

Stable `data-testid` or ID selectors are much safer than screen coordinates or generic text matching.

## Production recommendation

For several thousand records, use the official OpenAI API rather than ChatGPT website automation.

Advantages:

- no dependency on ChatGPT webpage HTML
- no browser login session
- more predictable retries
- faster processing
- easier logging
- easier concurrency controls
- cleaner failure handling

The application-side Playwright automation can remain the same; only the `send_to_chatgpt()` step would be replaced with an API call.
