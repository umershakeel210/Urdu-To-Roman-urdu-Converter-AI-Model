# Roman Urdu RPA

Automates:

```text
Raw Whisper ASR
    ↓
ChatGPT Roman Urdu conversion
    ↓
Human-Approved Roman Urdu + English
    ↓
Verify & Next
    ↓
Next record
```

## Important

This version automates the ChatGPT website because that is the requested workflow.

For production-scale processing of thousands of records, the official OpenAI API is more robust than automating the ChatGPT webpage.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

Read:

- `INSTALLATION.md`
- `ERROR_HANDLING.md`
- `DEPLOYMENT.md`
- `config.yaml`

before a large run.
