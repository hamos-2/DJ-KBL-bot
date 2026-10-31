"""Unit tests for SEO landing page, robots.txt, and sitemap.xml endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_root_returns_html_landing_page():
    """Browser request with text/html should receive the SEO landing page."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "KBL봇" in response.text
        assert "https://pf.kakao.com/_pxgeWX" in response.text
        assert "SoftwareApplication" in response.text


@pytest.mark.asyncio
async def test_root_returns_json_for_api_clients():
    """API client with application/json accept header should receive JSON."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/", headers={"Accept": "application/json"})
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/json"
        data = response.json()
        assert data.get("service") == "KBL Bot API"


@pytest.mark.asyncio
async def test_robots_txt_endpoint():
    """robots.txt should be served with text/plain content type."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/robots.txt")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        assert "User-agent" in response.text
        assert "Allow: /" in response.text


@pytest.mark.asyncio
async def test_sitemap_xml_endpoint():
    """sitemap.xml should be served with application/xml content type."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sitemap.xml")
        assert response.status_code == 200
        assert "xml" in response.headers.get("content-type", "")
        assert "<urlset" in response.text
        assert "https://hamos-2.github.io/DJ-KBL-bot/" in response.text
