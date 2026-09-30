from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from playwright.async_api import async_playwright, Page, Locator, TimeoutError as PlaywrightTimeoutError


APP_NAME = "Roman Urdu RPA"
ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
SHOT_DIR = ROOT / "screenshots"
PROFILE_DIR = ROOT / "browser_profile"
PAUSE_FLAG = ROOT / "PAUSE.flag"
STOP_FLAG = ROOT / "STOP.flag"

LOG_DIR.mkdir(exist_ok=True)
SHOT_DIR.mkdir(exist_ok=True)
PROFILE_DIR.mkdir(exist_ok=True)

logger = logging.getLogger(APP_NAME)


def setup_logging() -> None:
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_DIR / "automation.log", encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def load_config() -> dict:
    config_path = ROOT / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config file: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_ai_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:text)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip().strip('"').strip("'").strip()
    return text


def source_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


@dataclass
class RuntimeState:
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    paused: bool = False
    current_source_hash: Optional[str] = None


class RomanUrduRPA:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.state = RuntimeState()
        self.playwright = None
        self.context = None
        self.app_page: Optional[Page] = None
        self.chat_page: Optional[Page] = None
        self._last_new_chat_at = 0

    async def start(self) -> None:
        self.playwright = await async_playwright().start()

        browser_cfg = self.cfg["browser"]
        args = []
        if browser_cfg.get("start_maximized", True):
            args.append("--start-maximized")

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel=browser_cfg.get("channel", "chrome"),
            headless=browser_cfg.get("headless", False),
            viewport=None if browser_cfg.get("start_maximized", True) else {
                "width": browser_cfg.get("width", 1440),
                "height": browser_cfg.get("height", 900),
            },
            args=args,
        )

        pages = self.context.pages
        self.app_page = pages[0] if pages else await self.context.new_page()
        await self.app_page.goto(self.cfg["application"]["url"], wait_until="domcontentloaded")

        self.chat_page = await self.context.new_page()
        await self.chat_page.goto(self.cfg["chatgpt"]["url"], wait_until="domcontentloaded")

        logger.info("Browser started. Application and ChatGPT tabs opened.")
        logger.info("Pause/resume: create/delete PAUSE.flag in project folder. Stop: create STOP.flag.")
        logger.info("If ChatGPT asks you to log in, log in once in this persistent browser profile.")

    async def stop(self) -> None:
        try:
            if self.context:
                await self.context.close()
        finally:
            if self.playwright:
                await self.playwright.stop()

    async def wait_control_state(self) -> None:
        while True:
            if STOP_FLAG.exists():
                raise KeyboardInterrupt("STOP.flag detected")

            if PAUSE_FLAG.exists():
                if not self.state.paused:
                    self.state.paused = True
                    logger.info("Automation paused.")
                await asyncio.sleep(1)
                continue

            if self.state.paused:
                self.state.paused = False
                logger.info("Automation resumed.")
            return

    async def screenshot(self, page: Page, prefix: str) -> Path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = SHOT_DIR / f"{prefix}_{ts}.png"
        try:
            await page.screenshot(path=str(path), full_page=True)
            logger.info("Error screenshot saved: %s", path)
        except Exception as e:
            logger.error("Screenshot failed: %s", e)
        return path

    async def first_visible(self, page: Page, selectors: list[str], timeout_ms: int = 2500) -> Optional[Locator]:
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                await loc.wait_for(state="visible", timeout=timeout_ms)
                return loc
            except Exception:
                continue
        return None

    async def find_textarea_near_heading(self, page: Page, heading_text: str) -> Optional[Locator]:
        strategies = [
            f"text={heading_text}",
            f"label:has-text('{heading_text}')",
            f"*:has-text('{heading_text}')",
        ]
        for s in strategies:
            try:
                heading = page.locator(s).first
                await heading.wait_for(state="visible", timeout=1800)

                for xpath in [
                    "xpath=ancestor::*[self::div or self::section][1]//textarea",
                    "xpath=ancestor::*[self::div or self::section][2]//textarea",
                    "xpath=following::textarea[1]",
                ]:
                    try:
                        ta = heading.locator(xpath).first
                        await ta.wait_for(state="visible", timeout=1000)
                        return ta
                    except Exception:
                        pass
            except Exception:
                pass
        return None

    async def get_source_locator(self) -> Locator:
        app = self.app_page
        explicit = self.cfg["application"]["selectors"].get("source", [])
        loc = await self.first_visible(app, explicit)
        if loc:
            return loc

        loc = await self.find_textarea_near_heading(
            app, self.cfg["application"]["labels"]["source"]
        )
        if loc:
            return loc

        raise RuntimeError("Could not locate Raw Whisper ASR source field.")

    async def get_target_locator(self) -> Locator:
        app = self.app_page
        explicit = self.cfg["application"]["selectors"].get("target", [])
        loc = await self.first_visible(app, explicit)
        if loc:
            return loc

        loc = await self.find_textarea_near_heading(
            app, self.cfg["application"]["labels"]["target"]
        )
        if loc:
            return loc

        raise RuntimeError("Could not locate Human-Approved Roman Urdu target field.")

    async def get_verify_next_locator(self) -> Locator:
        app = self.app_page
        explicit = self.cfg["application"]["selectors"].get("verify_next", [])
        loc = await self.first_visible(app, explicit)
        if loc:
            return loc

        label = self.cfg["application"]["labels"]["verify_next"]
        candidates = [
            app.get_by_role("button", name=label, exact=True),
            app.locator(f"button:has-text('{label}')"),
            app.locator(f"text={label}"),
        ]
        for loc in candidates:
            try:
                await loc.first.wait_for(state="visible", timeout=1800)
                return loc.first
            except Exception:
                continue

        raise RuntimeError("Could not locate Verify & Next button.")

    async def read_source_text(self) -> str:
        source = await self.get_source_locator()

        tag_name = await source.evaluate(
            "(el) => el.tagName.toLowerCase()"
        )

        if tag_name in ("textarea", "input"):
            value = await source.input_value()
        else:
            value = await source.inner_text()

        return (value or "").strip()

    async def fill_target_text(self, text: str) -> None:
        target = await self.get_target_locator()
        await target.fill(text)

    async def click_verify_next_and_wait(self, old_source: str) -> bool:
        button = await self.get_verify_next_locator()
        await button.click()

        timeout_ms = self.cfg["application"].get("next_record_timeout_ms", 15000)
        deadline = time.monotonic() + timeout_ms / 1000

        while time.monotonic() < deadline:
            await asyncio.sleep(0.35)
            try:
                current = await self.read_source_text()
                if current and current != old_source:
                    return True
            except Exception:
                pass

        return False

    async def ensure_chatgpt_ready(self) -> None:
        page = self.chat_page

        if "login" in page.url.lower():
            raise RuntimeError("ChatGPT is not logged in. Log in once in the Playwright browser profile.")

        composer = await self.first_visible(
            page,
            self.cfg["chatgpt"]["selectors"]["composer"],
            timeout_ms=2500,
        )
        if not composer:
            raise RuntimeError("ChatGPT composer not found. Login may be required or selectors changed.")

    async def start_new_chat_if_needed(self) -> None:
        every = int(self.cfg["chatgpt"].get("new_chat_every", 20))
        if every <= 0:
            return
        if self.state.processed == 0 or (self.state.processed - self._last_new_chat_at) >= every:
            page = self.chat_page
            selectors = self.cfg["chatgpt"]["selectors"].get("new_chat", [])
            loc = await self.first_visible(page, selectors, timeout_ms=1500)
            if loc:
                await loc.click()
                await page.wait_for_timeout(800)
                self._last_new_chat_at = self.state.processed

    async def send_to_chatgpt(self, source_text: str) -> str:
        await self.ensure_chatgpt_ready()
        await self.start_new_chat_if_needed()

        page = self.chat_page
        prompt_template = self.cfg["chatgpt"]["prompt"]
        prompt = prompt_template.replace("{copied_text}", source_text)

        composer = await self.first_visible(
            page,
            self.cfg["chatgpt"]["selectors"]["composer"],
            timeout_ms=3000,
        )
        if not composer:
            raise RuntimeError("ChatGPT composer not found.")

        assistant_before = page.locator(
            self.cfg["chatgpt"]["selectors"]["assistant_message"]
        )
        before_count = await assistant_before.count()

        await composer.click()
        try:
            await composer.fill(prompt)
        except Exception:
            await composer.press("Control+A")
            await composer.type(prompt)

        send_button = await self.first_visible(
            page,
            self.cfg["chatgpt"]["selectors"].get("send_button", []),
            timeout_ms=1200,
        )

        if send_button:
            await send_button.click()
        else:
            await composer.press("Enter")

        response_timeout_ms = int(self.cfg["chatgpt"].get("response_timeout_ms", 120000))
        deadline = time.monotonic() + response_timeout_ms / 1000

        while time.monotonic() < deadline:
            await asyncio.sleep(0.75)

            # Wait until a new assistant message appears.
            current_count = await assistant_before.count()
            if current_count <= before_count:
                continue

            # Prefer waiting until streaming stops, if stop button exists while generating.
            stop_selectors = self.cfg["chatgpt"]["selectors"].get("stop_button", [])
            stop_visible = False
            for ss in stop_selectors:
                try:
                    if await page.locator(ss).first.is_visible():
                        stop_visible = True
                        break
                except Exception:
                    pass

            if stop_visible:
                continue

            last = assistant_before.last
            try:
                text = (await last.inner_text()).strip()
            except Exception:
                text = ""

            text = normalize_ai_text(text)
            if text:
                return text

        raise RuntimeError("Timed out waiting for ChatGPT response.")

    async def process_one(self) -> bool:
        await self.wait_control_state()

        source_text = await self.read_source_text()
        if not source_text:
            self.state.skipped += 1
            logger.warning("Empty source record; skipping.")
            return await self.click_verify_next_and_wait("")

        fp = source_fingerprint(source_text)
        self.state.current_source_hash = fp
        logger.info(
            "Record start | processed=%s failed=%s skipped=%s source_hash=%s",
            self.state.processed,
            self.state.failed,
            self.state.skipped,
            fp,
        )

        retries = int(self.cfg["automation"].get("retries", 3))
        last_error = None

        for attempt in range(1, retries + 1):
            await self.wait_control_state()
            try:
                roman = await self.send_to_chatgpt(source_text)
                if not roman:
                    raise RuntimeError("ChatGPT returned empty output.")

                await self.app_page.bring_to_front()
                await self.fill_target_text(roman)

                if self.cfg["automation"].get("auto_verify_next", True):
                    moved = await self.click_verify_next_and_wait(source_text)
                    if not moved:
                        raise RuntimeError("Verify & Next clicked but next record did not load.")

                self.state.processed += 1
                logger.info(
                    "Record completed | total=%s source_hash=%s",
                    self.state.processed,
                    fp,
                )
                return True

            except Exception as e:
                last_error = e
                logger.exception("Attempt %s/%s failed for source_hash=%s", attempt, retries, fp)
                await self.screenshot(self.app_page, f"app_error_{fp}_try{attempt}")
                await self.screenshot(self.chat_page, f"chatgpt_error_{fp}_try{attempt}")

                if attempt < retries:
                    await asyncio.sleep(self.cfg["automation"].get("retry_delay_seconds", 3))

        self.state.failed += 1
        logger.error("Record failed after %s attempts | source_hash=%s | error=%s", retries, fp, last_error)

        if self.cfg["automation"].get("skip_failed_records", True):
            try:
                old = source_text
                moved = await self.click_verify_next_and_wait(old)
                if moved:
                    logger.warning("Failed record skipped; moved to next record.")
                    return True
            except Exception:
                logger.exception("Could not move past failed record.")

        return False

    async def run(self) -> None:
        max_records = int(self.cfg["automation"].get("max_records", 0))

        logger.info("Automation started.")
        while True:
            await self.wait_control_state()

            if max_records > 0 and self.state.processed >= max_records:
                logger.info("Configured max_records reached: %s", max_records)
                break

            ok = await self.process_one()
            if not ok:
                logger.error("Automation stopped because current record could not be processed or skipped safely.")
                break

            await asyncio.sleep(self.cfg["automation"].get("between_records_delay_seconds", 0.5))


async def main():
    setup_logging()
    cfg = load_config()
    bot = RomanUrduRPA(cfg)

    try:
        await bot.start()
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Automation stopped by user/STOP.flag.")
    except Exception:
        logger.exception("Fatal automation error.")
        if bot.app_page:
            await bot.screenshot(bot.app_page, "fatal_app")
        if bot.chat_page:
            await bot.screenshot(bot.chat_page, "fatal_chatgpt")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())

