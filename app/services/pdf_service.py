import asyncio
from playwright.async_api import async_playwright


async def generate_pdf_async(html_content: str) -> bytes:
    """Convert HTML content to PDF bytes using Playwright (supports Windows)"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            
            # Set HTML content
            await page.set_content(html_content)
            
            # Generate PDF
            pdf_bytes = await page.pdf(
                format='A4',
                margin={
                    'top': '20px',
                    'right': '20px',
                    'bottom': '20px',
                    'left': '20px'
                }
            )
            
            await browser.close()
            return pdf_bytes
    except Exception as e:
        raise Exception(f"PDF generation failed: {str(e)}")


def generate_pdf(html_content: str) -> bytes:
    """Sync wrapper for PDF generation"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(generate_pdf_async(html_content))
    finally:
        loop.close()
