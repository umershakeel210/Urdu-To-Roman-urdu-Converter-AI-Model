import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    p = await async_playwright().start()

    context = await p.chromium.launch_persistent_context(
        user_data_dir=str(Path("browser_profile").resolve()),
        channel="chrome",
        headless=False,
        viewport=None,
        args=["--start-maximized"],
    )

    page = await context.new_page()
    await page.goto("https://chatgpt.com/")

    input(
        "\nChatGPT mein login complete karein.\n"
        "Login ke baad isi PowerShell window mein Enter press karein..."
    )

    await context.close()
    await p.stop()

asyncio.run(main())