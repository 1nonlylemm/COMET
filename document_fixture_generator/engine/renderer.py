"""Document rendering engine using Jinja2 and Playwright/Chromium."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import jinja2


class DocumentRenderer:
    """Renders HTML templates into PDF documents with exact A4 geometry."""

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        if templates_dir is None:
            self.templates_dir = Path(__file__).resolve().parent.parent / "templates"
        else:
            self.templates_dir = Path(templates_dir).resolve()

        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_html(self, template_name: str, context: dict[str, Any]) -> str:
        """Render template with context into an HTML string."""
        template = self.env.get_template(template_name)
        return template.render(**context)

    def render_pdf(
        self,
        template_name: str,
        context: dict[str, Any],
        *,
        output_path: Path | None = None,
        engine: str = "chromium",
    ) -> bytes:
        """Render template to PDF bytes with standard ISO A4 portrait geometry.

        Uses Playwright Chromium for deterministic HTML/CSS layout rendering.
        """
        html_content = self.render_html(template_name, context)
        return self.render_html_to_pdf(
            html_content,
            output_path=output_path,
            engine=engine,
        )

    def render_html_to_pdf(
        self,
        html_content: str,
        *,
        output_path: Path | None = None,
        engine: str = "chromium",
    ) -> bytes:
        """Render raw HTML content to PDF with hardened execution boundaries.

        - Disables JavaScript execution in the browser context.
        - Aborts all external subresource network requests.
        - Enforces strict ISO A4 geometry.
        """
        if engine == "weasyprint":
            from weasyprint import HTML
            # Seed documents contain only inline styles and text. Block all URL fetches.
            def reject_url(url, *args, **kwargs):
                raise ValueError("External resources are disabled for synthetic documents")
            pdf_bytes = HTML(string=html_content, url_fetcher=reject_url).write_pdf()
            if output_path is not None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(pdf_bytes)
            return pdf_bytes
        if engine != "chromium":
            raise ValueError("Unknown document rendering engine")

        # Set frozen epoch environment variable if requested
        if "SOURCE_DATE_EPOCH" not in os.environ:
            os.environ["SOURCE_DATE_EPOCH"] = "1700000000"

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(java_script_enabled=False)
            page = context.new_page()
            # Fail closed: abort all external resource fetches to prevent SSRF / data exfiltration
            page.route("**/*", lambda route: route.abort())
            page.set_content(html_content, wait_until="networkidle")
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
            )
            context.close()
            browser.close()

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)

        return pdf_bytes
