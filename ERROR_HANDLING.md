# Error Handling

The automation uses three layers of protection.

## 1. Per-record retries

Each record is attempted up to:

```yaml
automation:
  retries: 3
```

On failure the bot waits and tries again.

## 2. Screenshots

On every failed attempt, screenshots are written to:

```text
screenshots\
```

The bot captures both:

- the application tab
- the ChatGPT tab

Examples:

```text
app_error_17db082b7b21_try1_20260924_160900.png
chatgpt_error_17db082b7b21_try1_20260924_160900.png
```

## 3. Activity logs

Logs are stored in:

```text
logs\automation.log
```

For privacy, the default log records a short SHA-256 fingerprint of the source text instead of logging the full Urdu text.

## Common failures

### ChatGPT composer not found

Likely causes:

- ChatGPT is logged out
- ChatGPT changed its webpage structure
- the page did not load

Actions:

1. Inspect the ChatGPT browser tab.
2. Log in if required.
3. If the UI changed, update the selectors in `config.yaml`.

### Raw Whisper ASR field not found

Add the exact selector to:

```yaml
application:
  selectors:
    source:
```

### Target textbox not found

Add the exact selector to:

```yaml
application:
  selectors:
    target:
```

### Verify & Next not found

Add the exact selector to:

```yaml
application:
  selectors:
    verify_next:
```

### ChatGPT response timeout

Increase:

```yaml
chatgpt:
  response_timeout_ms: 180000
```

### Verify & Next clicked but record did not change

Possible reasons:

- validation error in your application
- network request failed
- button selector matched the wrong button
- next-record load takes longer

Check the screenshot and browser developer console.

## Failed record behavior

By default:

```yaml
skip_failed_records: false
```

This is safer because the bot stops rather than accidentally skipping a record.

If your application has a reliable skip behavior and you explicitly want unattended operation, you can set it to `true`.
