# Copyright 2026 Maxence Faldor
"""Draw scenes with three.js in headless Chromium, through Playwright's asyncio API.

The renderer serves its page and the vendored three.js from package data on a private
origin and refuses every other request, so renders work offline and never touch the
network.
"""

import asyncio
from collections.abc import Sequence
from functools import cache
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Final, Self

from playwright.async_api import Browser, Page, Playwright, Route, async_playwright
from playwright.async_api import Error as PlaywrightError

from bricky.errors import BrickyError
from bricky.render.scene import Scene, View

ORIGIN: Final = "https://bricky.invalid/"
"""The private origin of the renderer's page; the ``.invalid`` domain never resolves."""

_TYPES: Final = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}
_LAUNCH_ARGUMENTS: Final = ("--enable-unsafe-swiftshader",)


class Renderer:
    """Draws scenes with three.js in headless Chromium.

    Launching the browser and compiling shaders take the most time, so a renderer keeps
    one page open for every render. A renderer starts once and serves many renders, as
    an async context manager or through :meth:`start` and :meth:`close`. Renders on one
    renderer run one at a time.
    """

    def __init__(self, browser: Path | None = None) -> None:
        """Create a renderer.

        Args:
            browser: The Chromium executable to use; Playwright's own browser when
                ``None``.
        """
        self._executable = browser
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._problems: list[str] = []
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        """Start the browser."""
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the browser."""
        await self.close()

    async def start(self) -> None:
        """Launch the browser, unless it is already running.

        Raises:
            BrickyError: If Chromium cannot be started.
        """
        if self._browser is not None:
            return
        playwright = await async_playwright().start()
        try:
            self._browser = await playwright.chromium.launch(
                executable_path=self._executable, args=list(_LAUNCH_ARGUMENTS)
            )
        except PlaywrightError as error:
            await playwright.stop()
            raise BrickyError(_launch_failure(error, self._executable)) from None
        self._playwright = playwright

    async def close(self) -> None:
        """Close the page and the browser."""
        if self._page is not None:
            await self._page.close()
            self._page = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def render(
        self, scene: Scene, views: Sequence[View], *, width: int, height: int
    ) -> list[bytes]:
        """Draw each view of a scene and return PNG images, in the same order.

        Raises:
            BrickyError: If the browser cannot start or the page fails to draw.
        """
        async with self._lock:
            page = await self._open_page()
            self._problems.clear()
            images: list[bytes] = []
            try:
                await page.set_viewport_size({"width": width, "height": height})
                await page.evaluate(
                    "scene => window.bricky.load(scene)", scene.model_dump(mode="json")
                )
                for view in views:
                    await page.evaluate(
                        (
                            "([view, width, height]) => "
                            "window.bricky.draw(view, width, height)"
                        ),
                        [view.value, width, height],
                    )
                    images.append(await page.locator("#sheet").screenshot(type="png"))
            except PlaywrightError as error:
                # The renderer discards a page that failed once.
                await page.close()
                self._page = None
                detail = "; ".join(self._problems) or str(error).strip().splitlines()[0]
                message = f"rendering failed: {detail}"
                raise BrickyError(message) from None
            return images

    async def _open_page(self) -> Page:
        if self._page is not None:
            return self._page
        await self.start()
        if (
            self._browser is None
        ):  # pragma: no cover - start() either launches or raises
            message = "the renderer has no browser"
            raise BrickyError(message)
        page = await self._browser.new_page(device_scale_factor=1)
        page.on("pageerror", lambda error: self._problems.append(str(error)))
        page.on(
            "console",
            lambda console: (
                self._problems.append(console.text) if console.type == "error" else None
            ),
        )
        await page.route("**/*", _serve)
        try:
            await page.goto(ORIGIN + "render.html")
            await page.wait_for_function("() => window.bricky?.ready === true")
        except PlaywrightError as error:
            await page.close()
            detail = "; ".join(self._problems) or str(error).strip().splitlines()[0]
            message = f"the render page failed to load: {detail}"
            raise BrickyError(message) from None
        self._page = page
        return page


async def _serve(route: Route) -> None:
    """Answer the page's requests from package data and refuse everything else."""
    url = route.request.url
    if url.startswith(ORIGIN):
        name = url.removeprefix(ORIGIN).split("?", 1)[0]
        body = _asset(name)
        if body is not None:
            content_type = _TYPES.get(
                PurePosixPath(name).suffix, "application/octet-stream"
            )
            await route.fulfill(status=200, body=body, content_type=content_type)
            return
    await route.abort()


@cache
def _asset(name: str) -> bytes | None:
    parts = PurePosixPath(name).parts
    if not parts or any(part in {"..", "."} for part in parts):
        return None
    resource = files("bricky.render").joinpath("assets", *parts)
    try:
        return resource.read_bytes()
    except FileNotFoundError, IsADirectoryError:
        return None


def _launch_failure(error: PlaywrightError, executable: Path | None) -> str:
    first = str(error).strip().splitlines()[0]
    hint = (
        (
            "Point BRICKY_RENDER_BROWSER at a Chromium executable, "
            "or unset it to use Playwright's own browser."
        )
        if executable is not None
        else (
            "Install Playwright's browser with `uv run playwright install chromium`, "
            "or point BRICKY_RENDER_BROWSER at a Chromium executable."
        )
    )
    return f"cannot start Chromium for renders: {first}. {hint}"
