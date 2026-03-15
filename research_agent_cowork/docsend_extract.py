"""
DocSend PDF Extraction Module.

Downloads DocSend documents as PDF files using two services with retry fallback:
  1. Primary: DeckToPDF API (AWS Lambda endpoint)
  2. Fallback: docsend2pdf.com (web scraping with CSRF tokens)

Supports:
  - Single documents (/view/ URLs)
  - Datarooms (/s/ URLs with multiple documents)
  - Email + passcode authentication

Adapted from standalone docsend_extract.py for use in the research agent.

Usage:
    # Async — full extraction with auth and dataroom support
    text, pdf_paths = await extract_docsend_content(url, email="user@example.com")

    # Sync — simple download, returns file path or None
    pdf_path = download_docsend_pdf(url, output_dir="outputs/uploads")
"""

import requests
from requests.exceptions import HTTPError
from bs4 import BeautifulSoup
import logging
import os
import re
import json
import html
from functools import wraps
from pathlib import Path
from typing import Optional, Tuple, List
import asyncio

logger = logging.getLogger(__name__)

# Default email for DocSend authentication (many links require email entry)
DOCSEND_EMAIL = os.getenv('DOCSEND_EMAIL_ACCOUNT', 'research@fluxa.com')


def _sanitize_filename(filename: str) -> str:
    """Remove or replace characters unsafe for filenames."""
    sanitized = re.sub(r'[\\/*?:"<>|]', '_', filename)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = sanitized.strip('._')
    return sanitized[:200] or 'document'


def error_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Error in {func.__name__}")
            return f"Error in {func.__name__}: {e}"
    return wrapper


# ---------------------------------------------------------------------------
# Sync helper — simple interface for web_server.py and firecrawl_mcp.py
# ---------------------------------------------------------------------------

def download_docsend_pdf(
    url: str,
    output_dir: str = "outputs/uploads",
    email: Optional[str] = None,
    passcode: str = "",
    doc_name: Optional[str] = None,
) -> Optional[str]:
    """Download a DocSend document as PDF. Returns file path or None.

    Tries DeckToPDF API first, then docsend2pdf.com as fallback.
    This is a synchronous convenience wrapper.
    """
    email = email or DOCSEND_EMAIL
    os.makedirs(output_dir, exist_ok=True)

    # Generate filename
    if not doc_name:
        match = re.search(r'/view/([^/?]+)', url)
        doc_id = match.group(1) if match else "docsend"
        doc_name = f"docsend_{doc_id[:12]}"

    safe_name = _sanitize_filename(f"{doc_name}.pdf")
    output_path = os.path.join(output_dir, safe_name)

    # Try DeckToPDF API first, then docsend2pdf.com
    pdf_data = None
    try:
        logger.info(f"[DocSend] Trying DeckToPDF API for: {url}")
        pdf_data = translate_via_decktopdf_api(url, email, passcode)
    except Exception as e:
        logger.warning(f"[DocSend] DeckToPDF API failed: {e}")

    if not pdf_data or not isinstance(pdf_data, dict) or 'content' not in pdf_data:
        try:
            logger.info(f"[DocSend] Trying docsend2pdf.com for: {url}")
            pdf_data = generate_pdf_from_docsend_url(url, email, passcode)
        except Exception as e:
            logger.warning(f"[DocSend] docsend2pdf.com failed: {e}")

    if not pdf_data or not isinstance(pdf_data, dict) or 'content' not in pdf_data:
        logger.error(f"[DocSend] All services failed for: {url}")
        return None

    # Write PDF
    content = pdf_data['content']
    if len(content) < 100:
        logger.error(f"[DocSend] PDF content too small ({len(content)} bytes)")
        return None

    with open(output_path, 'wb') as f:
        f.write(content)

    logger.info(f"[DocSend] PDF saved: {output_path} ({len(content)} bytes)")
    return output_path


# ---------------------------------------------------------------------------
# Async full extraction (with auth, datarooms, etc.)
# ---------------------------------------------------------------------------

@error_handler
async def extract_docsend_content(
    url: str,
    email: Optional[str] = None,
    passcode: str = "",
    doc_name: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """Extract DocSend content. Returns (extracted_text, list_of_pdf_paths)."""
    email = email or DOCSEND_EMAIL
    logger.info(f"Starting DocSend content extraction for URL: {url}")
    session = create_session()
    combined_text = ""
    pdf_paths = []

    try:
        response = session.get(url, allow_redirects=True)
        response.raise_for_status()
        final_url = response.url

        soup = BeautifulSoup(response.text, 'html.parser')

        # Check if authentication is required
        if 'input' in response.text and 'authenticity_token' in response.text:
            logger.info("Authentication required. Attempting authentication...")
            soup = authenticate(session, final_url, email, passcode, soup)
            if not isinstance(soup, BeautifulSoup):
                logger.error("Authentication failed or returned unexpected type.")
                return "", []

        # Differentiate dataroom vs single document
        if '/s/' in final_url:
            logger.info("Detected dataroom URL. Handling as dataroom...")
            combined_text, temp_pdf_paths = await handle_dataroom(session, soup, email, passcode)
            pdf_paths.extend(temp_pdf_paths)
        else:
            # Resolve potential /v/ link
            if '/v/' in final_url:
                r = requests.get(url, allow_redirects=False)
                if r.status_code == 302 and 'Location' in r.headers:
                    final_url = r.headers['Location']

            extracted_text, temp_pdf_path = await handle_single_document(final_url, email, passcode, doc_name)
            if temp_pdf_path:
                combined_text = extracted_text
                pdf_paths.append(temp_pdf_path)
            else:
                logger.error(f"handle_single_document failed for URL: {final_url}")
                return "", []

        logger.info(f"DocSend extraction finished. {len(pdf_paths)} PDF path(s).")
        return combined_text, pdf_paths

    except HTTPError as http_err:
        logger.exception(f"HTTP error accessing {url}: {http_err}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during DocSend extraction for {url}")
        raise


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def create_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'DNT': '1',
    })
    return session


# ---------------------------------------------------------------------------
# DocSend authentication
# ---------------------------------------------------------------------------

def authenticate(session, url, email, passcode, soup):
    """Submit DocSend email/passcode auth form."""
    logger.info(f"Attempting authentication for URL: {url} with email: {email}")
    try:
        csrf_token_tag = soup.find('meta', {'name': 'csrf-token'})
        if not csrf_token_tag or not csrf_token_tag.get('content'):
            logger.error("CSRF token meta tag not found or missing content.")
            raise ValueError("CSRF token not found")
        csrf_token = csrf_token_tag['content']

        auth_data = {
            'utf8': '\u2713', '_method': 'patch', 'authenticity_token': csrf_token,
            'link_auth_form[email]': email, 'link_auth_form[passcode]': passcode,
            'commit': 'Continue'
        }

        auth_response = session.post(url, data=auth_data)

        if auth_response.status_code >= 400:
            logger.error(f"Authentication failed with status code: {auth_response.status_code}")

        auth_response.raise_for_status()
        logger.info(f"Authentication successful for {url}")
        return BeautifulSoup(auth_response.text, 'html.parser')

    except HTTPError as e:
        response_text = e.response.text if e.response else "N/A"
        if "Please verify that you own the entered email address" in response_text:
            raise ValueError(f"Email verification required for {email}.")
        elif "Incorrect email address or password" in response_text or e.response.status_code == 401:
            raise ValueError(f"Authentication failed: Invalid email or password.")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during authentication for {url}")
        raise


# ---------------------------------------------------------------------------
# Dataroom handling (multi-document)
# ---------------------------------------------------------------------------

async def process_docsend_document(session, url, email, passcode, safe_doc_name):
    """Process a single document within a dataroom."""
    logger.info(f"Processing dataroom document: {url}")
    try:
        if not safe_doc_name:
            url_parts = url.split('/')
            url_id = url_parts[-1].split('?')[0] if len(url_parts) >= 5 else "doc"
            safe_doc_name = f"docsend_{url_id[:8]}"

        session.get(url, allow_redirects=True)
    except Exception as e:
        logger.error(f"Failed to process document at {url}: {e}")
        return "", None

    document_text, temp_pdf_path = await handle_single_document(url, email, passcode, safe_doc_name)
    return document_text, temp_pdf_path


async def handle_dataroom(session, soup, email, passcode):
    """Handle DocSend dataroom (/s/ URL) with multiple documents."""
    doc_links = extract_document_links(soup)
    logger.info(f"Found {len(doc_links)} links in the dataroom.")

    tasks = []
    for link in doc_links:
        if 'href' in link.attrs:
            doc_url = link['href']
            doc_name_tag = link.find('div', class_='bundle-document_name')
            doc_name = doc_name_tag.text.strip() if doc_name_tag else "unknown_document"
            safe_doc_name = re.sub(r'[^\w\-_\.]', '_', doc_name).replace(' ', '_')
            if is_valid_docsend_document(session, doc_url):
                tasks.append(asyncio.create_task(
                    process_docsend_document(session, doc_url, email, passcode, safe_doc_name)
                ))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    combined_text = ""
    temp_pdf_paths = []
    for result in results:
        if isinstance(result, tuple):
            document_text, temp_pdf_path = result
            combined_text += document_text
            if temp_pdf_path:
                temp_pdf_paths.append(temp_pdf_path)
        else:
            logger.error(f"Error in processing dataroom document: {result}")

    return combined_text, temp_pdf_paths


# ---------------------------------------------------------------------------
# Single document handling
# ---------------------------------------------------------------------------

@error_handler
async def handle_single_document(url, email, passcode, doc_name=None):
    """Process a single DocSend URL, generate PDF, return (text, pdf_path)."""
    logger.info(f"Handling single document: {url} (Name: {doc_name})")
    temp_pdf_dir = str(Path(__file__).parent / "outputs" / "uploads")
    os.makedirs(temp_pdf_dir, exist_ok=True)

    if not doc_name:
        url_parts = url.split('/')
        if len(url_parts) >= 5:
            url_id = url_parts[-1].split('?')[0]
            doc_name = f"docsend_doc_{url_id[:8]}"
        else:
            doc_name = "docsend_document"

    safe_filename = _sanitize_filename(f"{doc_name}.pdf")
    temp_pdf_path = os.path.join(temp_pdf_dir, safe_filename)

    pdf_content_kwargs = await generate_pdf_with_retry(url, email, passcode)

    if pdf_content_kwargs is None or not isinstance(pdf_content_kwargs, dict) or 'content' not in pdf_content_kwargs:
        logger.error(f"Failed to generate PDF content for {url} after retries.")
        return "", None

    try:
        with open(temp_pdf_path, 'wb') as f:
            f.write(pdf_content_kwargs['content'])

        if not os.path.exists(temp_pdf_path):
            logger.error(f"Failed to write PDF file to {temp_pdf_path}.")
            return "", None

        file_size = os.path.getsize(temp_pdf_path)
        logger.info(f"PDF written: {temp_pdf_path} ({file_size} bytes)")
        return "", temp_pdf_path

    except Exception as e:
        logger.exception(f"Error during PDF file handling for URL {url}")
        if os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
            except OSError:
                pass
        return "", None


# ---------------------------------------------------------------------------
# PDF generation with dual-service retry
# ---------------------------------------------------------------------------

async def generate_pdf_with_retry(url, email, passcode, max_retries=2, delay=3):
    """Try DeckToPDF API first, then docsend2pdf.com as fallback."""
    logger.info(f"Generating PDF for: {url} (Primary: DeckToPDF API)")

    # Attempt 1: DeckToPDF API
    last_primary_error = None
    try:
        primary_kwargs = translate_via_decktopdf_api(url, email, passcode)
        if isinstance(primary_kwargs, dict) and 'content' in primary_kwargs:
            logger.info(f"DeckToPDF API successful for {url}.")
            return primary_kwargs
    except Exception as primary_error:
        last_primary_error = primary_error
        logger.warning(f"DeckToPDF API failed: {primary_error}")

    # Attempt 2: docsend2pdf.com with retries
    logger.warning(f"Attempting fallback docsend2pdf.com for: {url}")
    retries = 0
    last_fallback_error = None
    while retries < max_retries:
        try:
            fallback_kwargs = generate_pdf_from_docsend_url(url, email, passcode)
            if isinstance(fallback_kwargs, dict) and 'content' in fallback_kwargs:
                logger.info(f"docsend2pdf.com successful for {url}.")
                return fallback_kwargs
        except HTTPError as e:
            last_fallback_error = e
            status_code = e.response.status_code if e.response else None
            if status_code == 404:
                break
            if status_code == 504 and retries < max_retries - 1:
                retries += 1
                logger.warning(f"Retry {retries}/{max_retries} after 504. Waiting {delay}s...")
                await asyncio.sleep(delay)
            else:
                break
        except Exception as e:
            last_fallback_error = e
            logger.warning(f"docsend2pdf.com error: {e}")
            break

    logger.error(f"All services failed for {url}. Primary: {last_primary_error}, Fallback: {last_fallback_error}")
    return None


# ---------------------------------------------------------------------------
# Service 1: DeckToPDF API (AWS Lambda)
# ---------------------------------------------------------------------------

@error_handler
def translate_via_decktopdf_api(url, email, passcode):
    """Generate PDF using the DeckToPDF AWS API endpoint."""
    api_endpoint = 'https://xywyfi41dl.execute-api.us-east-1.amazonaws.com/fetch'
    logger.info(f"DeckToPDF API: {url}")

    payload = {
        'docsend_id': url,
        'docsend_email': email,
        'docsend_passcode': passcode
    }

    response = requests.post(
        api_endpoint,
        headers={'Content-Type': 'application/json'},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()

    try:
        api_response_data = response.json()
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON response from DeckToPDF API")

    if 'error' in api_response_data:
        raise ValueError(f"DeckToPDF API error: {api_response_data['error']}")

    if 'url' not in api_response_data or not api_response_data['url']:
        raise ValueError("Missing PDF URL in DeckToPDF API response")

    pdf_download_url = api_response_data['url']
    logger.info(f"DeckToPDF returned PDF URL: {pdf_download_url}")

    pdf_response = requests.get(pdf_download_url, timeout=90)
    pdf_response.raise_for_status()

    return {
        'content': pdf_response.content,
        'headers': {
            'Content-Type': pdf_response.headers.get('Content-Type', ''),
            'Content-Disposition': pdf_response.headers.get('Content-Disposition', '')
        }
    }


# ---------------------------------------------------------------------------
# Service 2: docsend2pdf.com (web scraping)
# ---------------------------------------------------------------------------

def generate_pdf_from_docsend_url(url, email, passcode='', searchable=True):
    """Generate PDF via docsend2pdf.com website."""
    credentials = docsend2pdf_credentials()
    if isinstance(credentials, str) and credentials.startswith("Error"):
        raise RuntimeError(credentials)
    kwargs = dict(email=email, passcode=passcode, searchable=searchable, **credentials)
    result = docsend2pdf_translate(url, **kwargs)
    if isinstance(result, str) and result.startswith("Error"):
        raise RuntimeError(result)
    return result


@error_handler
def docsend2pdf_credentials():
    """Fetch CSRF tokens from docsend2pdf.com."""
    with requests.Session() as session:
        target_url = 'https://docsend2pdf.com'
        response = session.get(target_url)
        response.raise_for_status()
        cookies = session.cookies.get_dict()
        soup = BeautifulSoup(response.text, 'html.parser')
        csrfmiddlewaretoken_tag = soup.find('input', {'name': 'csrfmiddlewaretoken'})

        if not csrfmiddlewaretoken_tag or 'value' not in csrfmiddlewaretoken_tag.attrs:
            raise ValueError("csrfmiddlewaretoken not found on docsend2pdf.com")

        return {
            'csrfmiddlewaretoken': csrfmiddlewaretoken_tag['value'],
            'csrftoken': cookies.get('csrftoken', '')
        }


@error_handler
def docsend2pdf_translate(url, csrfmiddlewaretoken, csrftoken, email, passcode='', searchable=False):
    """Submit URL to docsend2pdf.com and get PDF bytes back."""
    target_url = 'https://docsend2pdf.com'
    with requests.Session() as session:
        session.cookies.set('csrftoken', csrftoken)
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': target_url,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        data = {
            'csrfmiddlewaretoken': csrfmiddlewaretoken,
            'url': url,
            'email': email,
            'passcode': passcode,
        }
        if searchable:
            data['searchable'] = 'on'

        response = session.post(target_url, headers=headers, data=data, allow_redirects=True, timeout=60)

        if not response.ok:
            response.raise_for_status()

        return {
            'content': response.content,
            'headers': {
                'Content-Type': response.headers.get('Content-Type', 'application/octet-stream'),
                'Content-Disposition': response.headers.get('Content-Disposition', '')
            }
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@error_handler
def extract_document_links(soup):
    """Extract document links from a DocSend dataroom page."""
    data = json.loads(soup.text)
    unescaped_html = html.unescape(data['viewer_html'])
    soup = BeautifulSoup(unescaped_html, 'html.parser')
    container = soup.find('div', class_='bundle-viewer')
    return container.find_all('a', href=True)


def is_valid_docsend_document(session, url):
    """Check if a URL is a valid DocSend document (not a YouTube redirect, etc.)."""
    if 'docsend.com' not in url or '/view/' not in url:
        return False
    try:
        response = session.get(url, allow_redirects=False)
        if response.status_code == 302:
            location = response.headers.get('Location', '')
            if 'youtube.com' in location or 'youtu.be' in location:
                logger.info(f"URL {url} redirects to YouTube. Skipping.")
                return False
        return True
    except Exception as e:
        logger.error(f"Error checking URL {url}: {e}")
        return False
