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
from dotenv import load_dotenv
from google import genai
from playwright.async_api import async_playwright, Page, Locator


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

        load_dotenv(ROOT / ".env")

        self.gemini_client = genai.Client()
        self.gemini_model = (
            self.cfg.get("gemini", {}).get(
                "model",
                "gemini-3.5-flash-lite"
            )
        )

    async def start(self) -> None:
        self.playwright = await async_playwright().start()

        browser_cfg = self.cfg["browser"]
        args = []
        if browser_cfg.get("start_maximized", True):
            args.extend([
                "--start-maximized",
                "--window-position=0,0",
                "--window-size=1920,1080"
            ])

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

        try:
            cdp = await self.context.new_cdp_session(self.app_page)

            window_info = await cdp.send(
                "Browser.getWindowForTarget"
            )

            await cdp.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_info["windowId"],
                    "bounds": {
                        "windowState": "maximized"
                    }
                }
            )

            logger.info(
                "Browser window maximized successfully."
            )

        except Exception as e:
            logger.warning(
                "Could not maximize browser window: %s",
                e
            )

        try:
            cdp = await self.context.new_cdp_session(self.app_page)

            window_info = await cdp.send(
                "Browser.getWindowForTarget"
            )

            await cdp.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_info["windowId"],
                    "bounds": {
                        "windowState": "maximized"
                    }
                }
            )

            logger.info(
                "Browser window maximized successfully."
            )

        except Exception as e:
            logger.warning(
                "Could not maximize browser window: %s",
                e
            )

        try:
            cdp = await self.context.new_cdp_session(self.app_page)
            window_info = await cdp.send("Browser.getWindowForTarget")
            await cdp.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_info["windowId"],
                    "bounds": {"windowState": "maximized"}
                }
            )
        except Exception:
            pass

        try:
            cdp = await self.context.new_cdp_session(self.app_page)
            window_info = await cdp.send("Browser.getWindowForTarget")
            await cdp.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_info["windowId"],
                    "bounds": {"windowState": "maximized"}
                }
            )
        except Exception:
            pass
        await self.app_page.goto(
            self.cfg["application"]["url"],
            wait_until="domcontentloaded"
        )

        logger.info(
            "Waiting for application login/review page..."
        )
        logger.info(
            "Login manually in the opened Chrome window and open the "
            "Transcript Review page. Automation will continue automatically."
        )

        login_wait_seconds = int(
            self.cfg["application"].get(
                "login_wait_seconds",
                600
            )
        )

        deadline = time.monotonic() + login_wait_seconds

        while time.monotonic() < deadline:
            try:
                source = self.app_page.locator(
                    "#reviewRawText"
                ).first

                if await source.is_visible():
                    logger.info(
                        "Transcript Review page detected. Starting automation."
                    )
                    break
            except Exception:
                pass

            await asyncio.sleep(1)

        else:
            raise RuntimeError(
                "Transcript Review page was not detected within "
                f"{login_wait_seconds} seconds."
            )

        logger.info("Browser started. Application tab opened.")
        logger.info(
            "Gemini model: %s",
            self.gemini_model,
        )
        logger.info(
            "Pause/resume: create/delete PAUSE.flag in project folder. "
            "Stop: create STOP.flag."
        )

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

    async def mark_audio_unclear(self) -> None:
        candidates = [
            self.app_page.get_by_label(
                "Audio is unclear / unsuitable"
            ),
            self.app_page.locator(
                "label:has-text('Audio is unclear / unsuitable') input[type='checkbox']"
            ),
            self.app_page.locator(
                "input[type='checkbox']"
            ).filter(
                has=self.app_page.locator(
                    "text=Audio is unclear / unsuitable"
                )
            ),
        ]

        for candidate in candidates:
            try:
                checkbox = candidate.first
                await checkbox.wait_for(
                    state="visible",
                    timeout=1500
                )

                if not await checkbox.is_checked():
                    await checkbox.check()

                logger.info(
                    "Marked current segment as unclear / unsuitable."
                )
                return

            except Exception:
                continue

        raise RuntimeError(
            "Could not locate Audio is unclear / unsuitable checkbox."
        )

    async def mark_audio_unclear(self) -> None:
        candidates = [
            self.app_page.get_by_label(
                "Audio is unclear / unsuitable"
            ),
            self.app_page.locator(
                "label:has-text('Audio is unclear / unsuitable') input[type='checkbox']"
            ),
            self.app_page.locator(
                "input[type='checkbox']"
            ).filter(
                has=self.app_page.locator(
                    "text=Audio is unclear / unsuitable"
                )
            ),
        ]

        for candidate in candidates:
            try:
                checkbox = candidate.first
                await checkbox.wait_for(
                    state="visible",
                    timeout=1500
                )

                if not await checkbox.is_checked():
                    await checkbox.check()

                logger.info(
                    "Marked current segment as unclear / unsuitable."
                )
                return

            except Exception:
                continue

        raise RuntimeError(
            "Could not locate Audio is unclear / unsuitable checkbox."
        )

    async def get_record_marker(self) -> str:
        try:
            body_text = await self.app_page.locator("body").inner_text()

            match = re.search(
                r"\bSegment\s*#?\s*(\d+)\b",
                body_text,
                flags=re.IGNORECASE,
            )

            if match:
                return f"segment:{match.group(1)}"

        except Exception:
            pass

        return ""

    async def click_verify_next_and_wait(self, old_source: str) -> bool:
        old_url = self.app_page.url
        old_marker = await self.get_record_marker()

        button = await self.get_verify_next_locator()
        await button.click()

        timeout_ms = self.cfg["application"].get(
            "next_record_timeout_ms",
            60000
        )

        deadline = time.monotonic() + timeout_ms / 1000

        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)

            try:
                current_url = self.app_page.url

                if current_url != old_url:
                    logger.info(
                        "Next record detected by URL change."
                    )
                    return True

                current_marker = await self.get_record_marker()

                if (
                    old_marker
                    and current_marker
                    and current_marker != old_marker
                ):
                    logger.info(
                        "Next record detected by segment change: %s -> %s",
                        old_marker,
                        current_marker,
                    )
                    return True

                current_source = await self.read_source_text()

                if (
                    current_source
                    and current_source != old_source
                ):
                    logger.info(
                        "Next record detected by source text change."
                    )
                    return True

            except Exception:
                pass

        logger.warning(
            "Next record detection timed out | old_marker=%s | old_url=%s",
            old_marker,
            old_url,
        )

        return False

    async def send_to_gemini(self, source_text: str) -> str:
        prompt = f"""
Convert the following Urdu or mixed Urdu text into natural Roman Urdu.

STRICT RULES:
- Convert the ENTIRE input text.
- Do not omit any sentence, phrase, clause, word, or important detail.
- Do not shorten the text.
- Do not summarize.
- Do not translate the Urdu meaning into English.
- Preserve the original meaning exactly.
- Preserve the original sentence order.
- If the input contains multiple sentences, convert ALL of them.
- Use natural, readable Roman Urdu spelling.
- Preserve names exactly.
- Preserve IDs exactly.
- Preserve numbers exactly.
- Preserve dates exactly.
- Preserve percentages exactly.
- Preserve email addresses exactly.
- Preserve URLs exactly.
- Preserve software names exactly.
- Preserve English technical terms where appropriate.
- Preserve abbreviations exactly.
- Return ONLY the complete Roman Urdu conversion.
- Do not add headings.
- Do not add explanations.
- Do not use quotation marks around the answer.

IMPORTANT COMPLETENESS CHECK:
Before answering, internally verify that every part of the source text
has been represented in the Roman Urdu output.

Text:
{source_text}
""".strip()

        def call_gemini():
            interaction = self.gemini_client.interactions.create(
                model=self.gemini_model,
                input=prompt,
            )
            return interaction.output_text

        response_text = await asyncio.to_thread(call_gemini)

        response_text = normalize_ai_text(
            response_text or ""
        )

        if not response_text:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        # ----------------------------------------------------
        # Completeness / quality validation
        # ----------------------------------------------------
        source_words = [
            x for x in re.split(r"\s+", source_text.strip())
            if x
        ]

        output_words = [
            x for x in re.split(r"\s+", response_text.strip())
            if x
        ]

        source_chars = len(
            re.sub(r"\s+", "", source_text)
        )

        output_chars = len(
            re.sub(r"\s+", "", response_text)
        )

        word_ratio = (
            len(output_words) / len(source_words)
            if source_words
            else 1.0
        )

        char_ratio = (
            output_chars / source_chars
            if source_chars
            else 1.0
        )

        logger.info(
            "Gemini quality check | source_words=%s output_words=%s "
            "word_ratio=%.2f char_ratio=%.2f",
            len(source_words),
            len(output_words),
            word_ratio,
            char_ratio,
        )

        # For meaningful multi-word source text, very short output
        # almost certainly means Gemini omitted content.
        if len(source_words) >= 8:
            if word_ratio < 0.60:
                raise RuntimeError(
                    "Gemini output appears incomplete: "
                    f"word ratio {word_ratio:.2f}"
                )

            if char_ratio < 0.45:
                raise RuntimeError(
                    "Gemini output appears incomplete: "
                    f"character ratio {char_ratio:.2f}"
                )

        return response_text

    async def process_one(self) -> bool:
        await self.wait_control_state()

        source_text = await self.read_source_text()

        if not source_text:
            self.state.skipped += 1
            logger.warning("Empty source record; skipping.")
            return await self.click_verify_next_and_wait("")

        normalized_source = source_text.strip().lower()

        unclear_values = {
            "[unclear audio]",
            "unclear audio",
            "[inaudible]",
            "inaudible",
        }

        if normalized_source in unclear_values:
            logger.warning(
                "Unclear audio segment detected. "
                "Skipping Gemini and marking segment unsuitable."
            )

            await self.mark_audio_unclear()

            moved = await self.click_verify_next_and_wait(
                source_text
            )

            if moved:
                self.state.skipped += 1
                logger.info(
                    "Unclear audio segment handled successfully."
                )
                return True

            raise RuntimeError(
                "Unclear audio segment was marked, "
                "but next record did not load."
            )

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

        roman = None

        for attempt in range(1, retries + 1):
            await self.wait_control_state()

            try:
                if roman is None:
                    roman = await self.send_to_gemini(source_text)

                    if not roman:
                        raise RuntimeError(
                            "Gemini returned empty output."
                        )

                    await self.app_page.bring_to_front()
                    await self.fill_target_text(roman)

                if self.cfg["automation"].get(
                    "auto_verify_next",
                    True
                ):
                    moved = await self.click_verify_next_and_wait(
                        source_text
                    )

                    if not moved:
                        raise RuntimeError(
                            "Verify & Next clicked but next record did not load."
                        )

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
                await self.screenshot(
                    self.app_page,
                    f"app_error_{fp}_try{attempt}"
                )

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
            await bot.screenshot(
                bot.app_page,
                "fatal_app"
            )
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())















