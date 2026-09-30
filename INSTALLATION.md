# Installation Guide

## 1. Install Python

Install Python 3.11 or 3.12 for Windows 10/11.

During installation, enable:

- Add Python to PATH

Check:

```powershell
python --version
```

## 2. Open PowerShell in this project folder

Example:

```powershell
cd "D:\RomanUrduRPA"
```

## 3. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again.

## 4. Install Python packages

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Install Playwright browser support

Because the project uses your installed Chrome channel, normally Chrome should already exist.

It is still useful to install Playwright's Chromium:

```powershell
python -m playwright install chromium
```

## 6. Configure your application

Open `config.yaml`.

Change:

```yaml
application:
  url: "http://127.0.0.1:3000"
```

to the real URL of your transcript review application.

If exact DOM selectors are known, put them under:

```yaml
application:
  selectors:
```

The automation includes label-based fallbacks for:

- Raw Whisper ASR
- Human-Approved Roman Urdu + English
- Verify & Next

## 7. First ChatGPT login

Run:

```powershell
python main.py
```

A Chrome window opens with two tabs:

1. Your application
2. ChatGPT

If ChatGPT asks you to log in, log in manually once.

The project uses a persistent browser profile at:

```text
browser_profile\
```

Future runs will reuse that session until ChatGPT requires authentication again.

## 8. Start automation

```powershell
python main.py
```

## Pause / Resume

Create a file named:

```text
PAUSE.flag
```

in the project folder.

The bot pauses after reaching a safe checkpoint.

Delete `PAUSE.flag` to resume.

## Stop

Create:

```text
STOP.flag
```

The bot stops safely at the next control checkpoint.

Before the next run, delete `STOP.flag`.
