"""
===================================================================================
Python Tool Implementations
===================================================================================

Python versions of all tools from tools.js:
- Twitter API tools (via RapidAPI)
- Web scraping (via Firecrawl)
- Web search (via Firecrawl)

===================================================================================
"""

import os
import io
import json
import re
import time
import logging
import requests
from typing import Dict, List, Optional, Any, Set
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class Tools:
    def __init__(self):
        """Initialize with API keys from environment variables."""
        self.rapid_api_key = os.getenv('RAPID_API_KEY')
        self.firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY')
        self.rapid_api_host = 'twitter135.p.rapidapi.com'
        
        # Initialize Firecrawl
        if self.firecrawl_api_key:
            self.firecrawl_app = FirecrawlApp(api_key=self.firecrawl_api_key)
        else:
            self.firecrawl_app = None

        # Validate required API keys
        if not self.rapid_api_key:
            print("Warning: RAPID_API_KEY not found in environment variables")
        if not self.firecrawl_api_key:
            print("Warning: FIRECRAWL_API_KEY not found in environment variables")

    # -----------------------------
    # URL entity parsing + text replacement (no network expansion)
    # -----------------------------
    def _collect_entity_url_pairs(self, source: Dict) -> List[Dict[str, str]]:
        """Collect (tco, expanded) URL pairs from common entity locations.
        - entities.urls
        - entities.media
        - extended_entities.media
        - note_tweet entity_set.urls (when source is a note result)
        Returns list of dicts: {"tco": <short>, "expanded": <expanded>}
        """
        pairs: List[Dict[str, str]] = []

        def add_pairs(url_objs: Optional[List[Dict]]):
            if not url_objs:
                return
            for u in url_objs:
                if not isinstance(u, dict):
                    continue
                tco = u.get('url')
                expanded = (
                    u.get('expanded_url')
                    or u.get('unwound_url')
                    or u.get('media_url_https')
                    or u.get('media_url')
                )
                if tco and expanded and 't.co/' in tco:
                    pairs.append({"tco": tco, "expanded": expanded})

        # legacy-like structure
        entities = source.get('entities', {}) if isinstance(source, dict) else {}
        add_pairs(entities.get('urls'))
        add_pairs(entities.get('media'))

        extended = source.get('extended_entities', {}) if isinstance(source, dict) else {}
        add_pairs(extended.get('media'))

        # note result structure
        entity_set = source.get('entity_set', {}) if isinstance(source, dict) else {}
        add_pairs(entity_set.get('urls'))

        return pairs

    def _replace_tco_in_text(self, text: str, pairs: List[Dict[str, str]]) -> str:
        if not text:
            return text
        replaced = text
        for p in pairs:
            tco = p.get('tco')
            expanded = p.get('expanded')
            if tco and expanded:
                try:
                    replaced = replaced.replace(tco, expanded)
                except Exception:
                    pass
        return replaced

    def get_twitter_profile(self, username: str, **kwargs) -> Dict[str, Any]:
        """
        Get detailed profile information for a Twitter user by their username.
        
        Args:
            username: The Twitter username to look up (with or without @)
            
        Returns:
            Dictionary containing profile information or error
        """
        if kwargs:
            print(f"get_twitter_profile ignoring extra params: {kwargs}")
        try:
            clean_username = username.replace('@', '')

            data = self._fetch_twitter283_user_result_by_screen_name(clean_username)
            user_results = data.get("data", {}).get("user_results", {}) if isinstance(data, dict) else {}
            result = user_results.get("result", {}) if isinstance(user_results, dict) else {}

            if not isinstance(result, dict) or not result:
                return {"error": f"Profile not found for @{clean_username}"}

            core = result.get("core", {}) if isinstance(result.get("core"), dict) else {}
            profile_bio = result.get("profile_bio", {}) if isinstance(result.get("profile_bio"), dict) else {}
            relationship_counts = result.get("relationship_counts", {}) if isinstance(result.get("relationship_counts"), dict) else {}
            tweet_counts = result.get("tweet_counts", {}) if isinstance(result.get("tweet_counts"), dict) else {}
            avatar = result.get("avatar", {}) if isinstance(result.get("avatar"), dict) else {}
            banner = result.get("banner", {}) if isinstance(result.get("banner"), dict) else {}
            location_obj = result.get("location", {}) if isinstance(result.get("location"), dict) else {}
            verification = result.get("verification", {}) if isinstance(result.get("verification"), dict) else {}

            profile = {
                "username": core.get("screen_name", clean_username),
                "name": core.get("name", "Unknown"),
                "bio": profile_bio.get("description", ""),
                "followers_count": relationship_counts.get("followers", 0),
                "following_count": relationship_counts.get("following", 0),
                "tweets_count": tweet_counts.get("tweets", 0),
                "website": self._extract_website_url_from_twitter283_user(result),
                "user_id": result.get("rest_id") or user_results.get("rest_id") or "",
                # Keep legacy-compatible semantics (twitter135's legacy.verified appears to be False in practice)
                "verified": False,
                "blue_verified": verification.get("is_blue_verified", False),
                "created_at": core.get("created_at", ""),
                "location": location_obj.get("location", ""),
                "profile_image_url": avatar.get("image_url", ""),
                "profile_banner_url": banner.get("image_url", ""),
            }

            return profile
            
        except requests.exceptions.RequestException as e:
            return {"error": f"API request failed for @{username}: {str(e)}"}
        except Exception as e:
            return {"error": f"Failed to get profile for @{username}: {str(e)}"}

    def _fetch_twitter283_user_result_by_screen_name(self, username: str) -> Dict[str, Any]:
        url = "https://twitter283.p.rapidapi.com/UserResultByScreenName"
        headers = {
            "x-rapidapi-key": self.rapid_api_key,
            "x-rapidapi-host": "twitter283.p.rapidapi.com",
        }
        params = {"username": username}
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _extract_website_url_from_twitter283_user(self, user_result: Dict[str, Any]) -> str:
        """Extract website URL from twitter283 user result, filtering t.co links."""
        try:
            profile_bio = user_result.get("profile_bio", {}) if isinstance(user_result, dict) else {}
            entities = profile_bio.get("entities", {}) if isinstance(profile_bio, dict) else {}
            url_data = entities.get("url", {}) if isinstance(entities, dict) else {}
            urls = url_data.get("urls", []) if isinstance(url_data, dict) else []

            url_to_check = ""
            if urls and isinstance(urls, list):
                first = urls[0] if urls else {}
                if isinstance(first, dict):
                    url_to_check = first.get("expanded_url", "") or first.get("url", "")

            if not url_to_check:
                website = user_result.get("website", {}) if isinstance(user_result, dict) else {}
                if isinstance(website, dict):
                    url_to_check = website.get("url", "")

            return "" if isinstance(url_to_check, str) and "t.co/" in url_to_check else (url_to_check or "")
        except Exception:
            return ""

    def get_twitter_following(self, username: str, oldest_first: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Fetch profiles of accounts that the target user is following.
        Returns in chronological order (oldest first) to prioritize founders/early team members.
        
        Args:
            username: The Twitter username to get followings for
            oldest_first: If True, only returns the oldest 50 followings
            
        Returns:
            Dictionary containing following profiles or error
        """
        if kwargs:
            print(f"get_twitter_following ignoring extra params: {kwargs}")
        try:
            clean_username = username.replace('@', '')
            
            # First, get the user's profile to check total following count
            profile = self.get_twitter_profile(clean_username)
            if "error" in profile:
                return profile
                
            total_following = profile.get('following_count', 0)
            print(f"@{clean_username} follows {total_following} accounts")
            
            # If following more than 1500, skip but don't fail
            if total_following > 1500:
                print(f"Skipping following collection for @{clean_username} (follows {total_following} > 5000 accounts)")
                return {
                    "skipped": True,
                    "reason": "too_many_followings",
                    "total_following": total_following,
                    "message": "User follows too many accounts (>5000). Skipping following analysis but continuing research."
                }
            
            # Collect all followings using pagination
            all_followings = []
            cursor = None
            page_count = 0
            max_pages = 20  # Safety limit
            
            print(f"Collecting all {total_following} followings for @{clean_username}...")
            
            while page_count < max_pages:
                page_count += 1
                print(f"Fetching page {page_count}...")
                
                rapid_following_host = "twitter283.p.rapidapi.com"
                url = "https://twitter283.p.rapidapi.com/FollowingLight"
                headers = {
                    "x-rapidapi-key": self.rapid_api_key,
                    "x-rapidapi-host": rapid_following_host
                }
                params = {
                    "username": clean_username,
                    "count": "200"  # Maximum per page
                }
                
                if cursor:
                    params["cursor"] = cursor
                
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("error") == "Not authorized.":
                    return {"error": "Profile is private"}
                
                if not data.get("users"):
                    break  # No more data
                
                page_followings = data["users"]
                all_followings.extend(page_followings)
                
                print(f"Page {page_count}: Got {len(page_followings)} followings (total: {len(all_followings)})")
                
                # Check for next cursor
                cursor = data.get("next_cursor_str")
                if not cursor or cursor == "0" or len(all_followings) >= total_following:
                    break  # No more pages
                
                # Small delay between requests
                time.sleep(0.1)
            
            print(f"Collected {len(all_followings)} total followings for @{clean_username}")
            
            # If oldest_first is True, take the last 50 from API response (oldest followings)
            if oldest_first:
                all_followings = all_followings[-50:]  # Take last 50 (oldest from API)
                print(f"Returning oldest 50 followings (potential founders) for @{clean_username}")
            # Otherwise, keep the reverse chronological order (newest first) as returned by API
            
            # Simplify the data structure
            basic_profiles = []
            for user in all_followings:
                profile = {
                    "username": user.get("screen_name", ""),
                    "name": user.get("name", ""),
                    "bio": user.get("description", ""),
                    "followers": user.get("followers_count", 0),
                    "website": self._extract_website_url_from_user(user),
                    "verified": user.get("verified", False),
                    "created_at": user.get("created_at", "")
                }
                basic_profiles.append(profile)
            
            return {
                "total_collected": len(basic_profiles),
                "total_following": total_following,
                "chronological_order": oldest_first,  # True only if oldest_first=True
                "note": "Results are in reverse chronological order (newest first) by default, or oldest first if oldest_first=True",
                "profiles": basic_profiles
            }
            
        except requests.exceptions.RequestException as e:
            return {"error": f"API request failed for @{username}: {str(e)}"}
        except Exception as e:
            return {"error": f"Failed to get following list for @{username}: {str(e)}"}
    #20 max, dont change it back to 50
    def get_twitter_tweets(self, username: str, limit: int = 20, **kwargs) -> Dict[str, Any]:
        """
        Fetch recent tweets posted by a Twitter user.
        
        Args:
            username: The Twitter username
            limit: Number of tweets to fetch (default 20)
            
        Returns:
            Dictionary containing tweets or error
        """
        if kwargs:
            print(f"get_twitter_tweets ignoring extra params: {kwargs}")
        try:
            clean_username = username.replace('@', '')
            
            # First, get the user's profile to obtain their User ID
            profile = self.get_twitter_profile(clean_username)
            if "error" in profile:
                return {"error": f"Failed to get user ID for @{clean_username}: {profile['error']}"}
            
            user_id = profile.get('user_id', '')
            if not user_id:
                return {"error": f"Could not find user ID for @{clean_username}"}

            processed_tweets: List[Dict[str, Any]] = []

            cursor: Optional[str] = None
            page_count = 0
            max_pages = 10  # Safety limit for cursor pagination
            page_size = 20
            pages_needed = max(1, (limit + page_size - 1) // page_size)

            while page_count < max_pages and page_count < pages_needed and len(processed_tweets) < limit:
                page_count += 1
                data = self._fetch_twitter283_user_tweets(user_id, cursor=cursor)
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")

                page_tweets: List[Dict[str, Any]] = []
                try:
                    transformed = self._transform_twitter283_user_tweets_response(data)
                    self._find_full_text_recursively(transformed, page_tweets)
                except Exception as e:
                    print(f"Error parsing Twitter response: {e}")
                    return {
                        "username": clean_username,
                        "user_id": user_id,
                        "tweets": [],
                        "error": f"Error parsing response: {str(e)}",
                    }

                for t in page_tweets:
                    if not isinstance(t, dict):
                        continue
                    processed_tweets.append(self._normalize_tweet_entry(t))
                    if len(processed_tweets) >= limit:
                        break

                cursor = self._extract_bottom_cursor(data)
                if not cursor:
                    break

                time.sleep(0.1)

            if not processed_tweets:
                return {
                    "username": clean_username,
                    "user_id": user_id,
                    "entries": [],
                    "message": "No tweets found for this user."
                }
            
            return {
                "username": clean_username,
                "user_id": user_id,
                "total_entries": len(processed_tweets),
                "entries": processed_tweets  # Complete tweet objects with URLs
            }
            
        except requests.exceptions.RequestException as e:
            return {"error": f"API request failed for @{username}: {str(e)}"}
        except Exception as e:
            return {"error": f"Failed to fetch tweets for @{username}: {str(e)}"}

    def _fetch_twitter283_user_tweets(self, user_id: str, cursor: Optional[str] = None) -> Dict[str, Any]:
        url = "https://twitter283.p.rapidapi.com/UserTweets"
        headers = {
            "x-rapidapi-key": self.rapid_api_key,
            "x-rapidapi-host": "twitter283.p.rapidapi.com",
        }
        params: Dict[str, str] = {"user_id": user_id}
        if cursor:
            params["cursor"] = cursor

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _extract_bottom_cursor(self, data: Any) -> Optional[str]:
        """Extract the Bottom cursor value from a twitter283 UserTweets response."""
        if not data:
            return None

        if isinstance(data, list):
            for item in data:
                cursor = self._extract_bottom_cursor(item)
                if cursor:
                    return cursor
            return None

        if not isinstance(data, dict):
            return None

        if data.get("__typename") == "TimelineTimelineCursor" and data.get("cursor_type") == "Bottom":
            value = data.get("value")
            return value if isinstance(value, str) and value else None

        if data.get("cursor_type") == "Bottom":
            value = data.get("value")
            return value if isinstance(value, str) and value else None

        for value in data.values():
            cursor = self._extract_bottom_cursor(value)
            if cursor:
                return cursor

        return None

    def _transform_twitter283_user_tweets_response(self, data: Any) -> Any:
        """Transform twitter283 UserTweets response into a shape compatible with `_find_full_text_recursively`."""
        if isinstance(data, list):
            return [self._transform_twitter283_user_tweets_response(x) for x in data]
        if not isinstance(data, dict):
            return data

        entry_id = data.get("entry_id")
        if isinstance(entry_id, str) and entry_id.startswith("promoted-tweet-"):
            return {"entry_id": entry_id}

        transformed: Dict[str, Any] = {k: self._transform_twitter283_user_tweets_response(v) for k, v in data.items()}

        rest_id = transformed.get("rest_id")
        legacy = transformed.get("legacy")
        if (
            isinstance(rest_id, str)
            and rest_id.isdigit()
            and isinstance(legacy, dict)
            and isinstance(legacy.get("full_text"), str)
            and "id_str" not in legacy
        ):
            legacy["id_str"] = rest_id

        if "legacy" in transformed and "quoted_tweet_results" in transformed:
            reordered: Dict[str, Any] = {}
            for k in transformed.keys():
                if k in ("legacy", "quoted_tweet_results"):
                    continue
                reordered[k] = transformed[k]
            reordered["quoted_tweet_results"] = transformed["quoted_tweet_results"]
            reordered["legacy"] = transformed["legacy"]
            return reordered

        return transformed

    def _normalize_tweet_entry(self, tweet: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize tweet dict fields to match legacy output."""
        if not isinstance(tweet, dict):
            return tweet

        text = tweet.get("text")
        if isinstance(text, str) and "twitter.com/" in text:
            tweet["text"] = text.replace("https://twitter.com/", "https://x.com/").replace("http://twitter.com/", "https://x.com/")

        urls = tweet.get("urls")
        if isinstance(urls, list):
            normalized_urls: List[str] = []
            seen: Set[str] = set()
            for u in urls:
                if not isinstance(u, str) or not u:
                    continue
                u2 = u.replace("https://twitter.com/", "https://x.com/").replace("http://twitter.com/", "https://x.com/")
                if "/i/web/status/" in u2:
                    continue
                if u2 in seen:
                    continue
                seen.add(u2)
                normalized_urls.append(u2)
            tweet["urls"] = normalized_urls

        return tweet

    def _is_docsend_url(self, url: str) -> bool:
        """Check if URL is a DocSend document link."""
        return bool(re.match(r'https?://(www\.)?docsend\.com/view/', url))

    def _fetch_docsend_content(self, url: str) -> Optional[str]:
        """Download DocSend document and extract text.

        Uses docsend_extract module (DeckToPDF API primary, docsend2pdf.com fallback).
        """
        try:
            # Import from research_agent_cowork's docsend_extract
            import sys
            cowork_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'research_agent_cowork')
            if cowork_dir not in sys.path:
                sys.path.insert(0, cowork_dir)
            from docsend_extract import download_docsend_pdf

            pdf_path = download_docsend_pdf(url=url)
            if not pdf_path:
                return None

            try:
                import pdfplumber
                pages_text = []
                with pdfplumber.open(pdf_path) as pdf:
                    page_count = len(pdf.pages)
                    for i, page in enumerate(pdf.pages):
                        text = page.extract_text() or ""
                        if text.strip():
                            pages_text.append(f"--- Page {i + 1} ---\n{text}")

                header = f"# DocSend Document\n\nSource: {url}\nPages: {page_count}\n\n"
                if pages_text:
                    return header + "\n\n".join(pages_text)
                return header + "[DocSend document contains image-based slides with no extractable text.]"

            except ImportError:
                return f"# DocSend Document\n\nSource: {url}\n\n[PDF text extraction unavailable — pdfplumber not installed]"

        except Exception as e:
            logger.error(f"DocSend fetch failed for {url}: {e}")
            return None

    def scrape_website(self, url: str, **kwargs) -> str:
        """
        Scrape a single URL and return its text content.

        Args:
            url: The URL to scrape

        Returns:
            String containing the scraped content or error message
        """
        if kwargs:
            print(f"scrape_website ignoring extra params: {kwargs}")

        # DocSend URLs need special handling
        if self._is_docsend_url(url):
            print(f"\n📄 DocSend detected: {url}")
            content = self._fetch_docsend_content(url)
            if content:
                return content[:125000]
            print(f"⚠️ DocSend extraction failed, falling back to Firecrawl")

        try:
            if not self.firecrawl_app:
                return json.dumps({"error": "FIRECRAWL_API_KEY not configured"})
            
            print(f"\n🔎 Scraping: {url}")
            
            # Use Firecrawl to scrape the URL with correct parameters
            # Add timeout to prevent hanging (50 seconds, less than OpenAI's 60s limit)
            if hasattr(self.firecrawl_app, "scrape"):
                scrape_result = self.firecrawl_app.scrape(
                    url,
                    formats=['markdown'],
                    only_main_content=True,
                    timeout=50000  # 50 seconds in milliseconds
                )
            else:
                # Backward compatibility for older SDKs
                scrape_result = self.firecrawl_app.scrape_url(
                    url,
                    formats=['markdown'],
                    onlyMainContent=True,
                    maxAge=86400000,  # 1 day cache
                    timeout=50000  # 50 seconds in milliseconds
                )
            
            # The SDK returns a ScrapeResponse object
            if not scrape_result:
                raise Exception("No content returned from Firecrawl")
            
            # Debug the response structure
            print(f"✅ Firecrawl returned response of type: {type(scrape_result)}")
            
            # Try different ways to extract content
            page_content = None
            
            # Method 1: Direct attributes
            if hasattr(scrape_result, 'markdown') and scrape_result.markdown:
                page_content = scrape_result.markdown
                print("   Found content in .markdown attribute")
            elif hasattr(scrape_result, 'html') and scrape_result.html:
                page_content = scrape_result.html
                print("   Found content in .html attribute")
            # Method 2: Dictionary-style access
            elif hasattr(scrape_result, '__getitem__'):
                try:
                    page_content = scrape_result.get('markdown') or scrape_result.get('html') or scrape_result.get('content')
                    if page_content:
                        print("   Found content via dictionary access")
                except:
                    pass
            # Method 3: Check for data attribute
            elif hasattr(scrape_result, 'data'):
                if isinstance(scrape_result.data, dict):
                    page_content = scrape_result.data.get('markdown') or scrape_result.data.get('html') or scrape_result.data.get('content')
                    if page_content:
                        print("   Found content in .data attribute")
                elif isinstance(scrape_result.data, str):
                    page_content = scrape_result.data
                    print("   Found content as string in .data")
            
            if not page_content:
                print(f"❌ Could not extract content from response")
                print(f"   Response type: {type(scrape_result)}")
                print(f"   Available attributes: {[attr for attr in dir(scrape_result) if not attr.startswith('_')]}")
                if hasattr(scrape_result, '__dict__'):
                    print(f"   Response dict: {scrape_result.__dict__}")
                raise Exception("No content extracted from Firecrawl response")
            
            # Clean up the content
            import re
            # Remove base64 images
            page_content = re.sub(r'!\[.*?\]\(data:image\/.*?\)', '[IMAGE REMOVED]', page_content)
            page_content = re.sub(r'data:image\/[^;]+;base64,[a-zA-Z0-9+/=]+', '', page_content)
            
            # Limit content size (125KB for large context windows)
            return page_content[:125000]
            
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors specifically (502, 503, etc.)
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                if status_code == 502:
                    error_msg = "Firecrawl service temporarily unavailable (502 Bad Gateway)"
                elif status_code == 503:
                    error_msg = "Firecrawl service overloaded (503 Service Unavailable)"
                elif status_code == 504:
                    error_msg = "Firecrawl request timed out (504 Gateway Timeout)"
                else:
                    error_msg = f"Firecrawl HTTP error {status_code}"
            
            error_details = {
                "error": error_msg,
                "url": url,
                "content": f"Failed to scrape {url}: {error_msg}. The website may be temporarily unavailable or blocking scrapers."
            }
            print(f"❌ Scrape failed: {error_msg}")
            return json.dumps(error_details)
            
        except Exception as e:
            import traceback
            error_details = {
                "error": f"Failed to scrape \"{url}\": {str(e)}",
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
            print(f"❌ Scrape failed with {type(e).__name__}: {str(e)}")
            print(f"   Full traceback: {traceback.format_exc()}")
            return json.dumps(error_details)

    def search_web(self, query: str, limit: int = 5, **kwargs) -> Dict[str, Any]:
        """
        Search the web for information using Firecrawl's search API.
        Always includes scraped content from search results.
        
        Args:
            query: The search query
            limit: Number of search results to return (default 5, max 10)
            
        Returns:
            Dictionary containing search results with scraped content or error
        """
        if kwargs:
            print(f"search_web ignoring extra params: {kwargs}")
        try:
            if not self.firecrawl_app:
                return {"error": "FIRECRAWL_API_KEY not configured"}
            
            print(f"\n🔎 Searching web for: {query} (limit: {limit})")
            
            # Search with content scraping - always include content
            from firecrawl import ScrapeOptions
            scrape_options = ScrapeOptions(
                formats=['markdown', 'links'],
                onlyMainContent=True,
                timeout=50000  # 50 seconds in milliseconds
            )
            search_result = self.firecrawl_app.search(
                query,
                limit=min(limit, 5),  # Cap at 5 results
                scrape_options=scrape_options
            )
            
            # The SDK returns a SearchResponse object
            if not search_result:
                return {
                    "query": query,
                    "results": [],
                    "message": "No search results found."
                }
            
            # Extract data from the SearchResponse object - results are dictionaries
            search_results = search_result.data or []
            
            if not search_results:
                return {
                    "query": query,
                    "results": [],
                    "message": "No search results found."
                }
            
            # Process and format results - results are dictionaries as per Firecrawl docs
            formatted_results = []
            for index, result in enumerate(search_results):
                formatted_result = {
                    "rank": index + 1,
                    "title": result.get('title', 'No title'),
                    "url": result.get('url', ''),
                    "description": result.get('description', ''),
                    "content": result.get('markdown', result.get('html', '')),
                    "links": result.get('links', []),
                    "metadata": result.get('metadata', {})
                }
                formatted_results.append(formatted_result)
            
            # Combine all content
            combined_content = '\n\n---\n\n'.join([
                f"## {r['title']}\nURL: {r['url']}\n{r['content']}"
                for r in formatted_results
            ])
            
            return {
                "query": query,
                "total_results": len(formatted_results),
                "combined_content": combined_content[:125000],  # Limit size
                "individual_results": formatted_results,
                "search_metadata": {
                    "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "content_included": True,
                    "sdk_used": True
                }
            }
                
        except Exception as e:
            print(f"Search error: {str(e)}")
            return {
                "error": f"Failed to search for \"{query}\": {str(e)}",
                "query": query,
                "results": []
            }

    def bulk_get_twitter_profiles(self, identifiers: List[str], **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch profiles for up to 20 Twitter users by username.

        This function now only accepts usernames (with or without '@') and
        simply calls `get_twitter_profile` for each one.
        
        Args:
            identifiers: List of Twitter usernames (max 20)
            
        Returns:
            List of profile dicts as returned by `get_twitter_profile`
        """
        if kwargs:
            print(f"bulk_get_twitter_profiles ignoring extra params: {kwargs}")
        try:
            if len(identifiers) > 20:
                identifiers = identifiers[:20]
            
            profiles: List[Dict[str, Any]] = []
            for identifier in identifiers:
                profile = self.get_twitter_profile(identifier)
                profiles.append(profile)
            
            return profiles
            
        except Exception as e:
            return [{"error": f"Failed bulk profile fetch: {str(e)}"}]

    def _extract_website_url(self, legacy_data: Dict) -> str:
        """Extract website URL from Twitter legacy data, filtering t.co links."""
        try:
            entities = legacy_data.get('entities', {})
            url_data = entities.get('url', {})
            urls = url_data.get('urls', [])
            url_to_check = ""
            if urls and len(urls) > 0:
                url_to_check = urls[0].get('expanded_url', '')
            
            if not url_to_check:
                 url_to_check = legacy_data.get('url', '')
            
            # Never return a t.co link, as it's un-scrapable
            return "" if 't.co/' in url_to_check else url_to_check
        except:
            return ''

    def _extract_website_url_from_user(self, user_data: Dict) -> str:
        """Extract website URL from Twitter user data, filtering t.co links."""
        try:
            entities = user_data.get('entities', {})
            url_data = entities.get('url', {})
            urls = url_data.get('urls', [])
            url_to_check = ""
            if urls and len(urls) > 0:
                url_to_check = urls[0].get('expanded_url', '')

            if not url_to_check:
                url_to_check = user_data.get('url', '')
            
            # Never return a t.co link, as it's un-scrapable
            return "" if 't.co/' in url_to_check else url_to_check
        except:
            return ''

    def _extract_urls_from_tweet(self, tweet_data: Dict) -> List[str]:
        """Extract expanded URLs from all known tweet entity locations."""
        collected: Set[str] = set()

        def normalize_url(candidate: Optional[str]) -> Optional[str]:
            if not candidate or not isinstance(candidate, str):
                return None
            if 't.co/' in candidate.lower():
                return None
            return candidate

        def add_from_obj(url_obj: Any) -> None:
            if not isinstance(url_obj, dict):
                return

            candidates = [
                url_obj.get('expanded_url'),
                url_obj.get('unwound_url'),
                url_obj.get('media_url_https'),
                url_obj.get('media_url'),
                url_obj.get('url'),
            ]

            for candidate in candidates:
                normalized = normalize_url(candidate)
                if normalized:
                    collected.add(normalized)
                    break  # Prefer the first non t.co option

        def add_from_iter(items: Any) -> None:
            if not items:
                return
            for item in items:
                add_from_obj(item)

        try:
            entities = tweet_data.get('entities', {})
            add_from_iter(entities.get('urls'))
            add_from_iter(entities.get('media'))

            extended_entities = tweet_data.get('extended_entities', {})
            add_from_iter(extended_entities.get('media'))

            entity_set = tweet_data.get('entity_set')
            if isinstance(entity_set, dict):
                add_from_iter(entity_set.get('urls'))
                add_from_iter(entity_set.get('media'))

            attachments = tweet_data.get('attachments', {})
            if isinstance(attachments, dict):
                add_from_iter(attachments.get('media_keys'))

            card = tweet_data.get('card', {})
            if isinstance(card, dict):
                legacy_card = card.get('legacy', {})
                add_from_iter(legacy_card.get('binding_values'))

        except Exception as exc:
            print(f"Error extracting URLs from tweet: {exc}")

        return sorted(collected)

    def _find_full_text_recursively(self, data: Any, results: List[Dict]) -> None:
        """
        Recursive helper to find objects with 'full_text' property and 'note_tweet_results'.
        Prioritizes note_tweet_results for longer tweets and properly flattens the data.
        Based on the JavaScript implementation for robust tweet extraction.
        """
        if not data:
            return

        if isinstance(data, list):
            # If it's a list, recurse into each element
            for item in data:
                self._find_full_text_recursively(item, results)
        elif isinstance(data, dict):
            # First, check if this object has note_tweet_results (for longer tweets)
            if 'note_tweet' in data and isinstance(data['note_tweet'], dict):
                note_tweet = data['note_tweet']
                if ('note_tweet_results' in note_tweet and 
                    isinstance(note_tweet['note_tweet_results'], dict) and
                    'result' in note_tweet['note_tweet_results']):
                    
                    note_result = note_tweet['note_tweet_results']['result']
                    note_text = note_result.get('text', '')
                    
                    if note_text and note_text.strip():
                        # For note tweets, collect URLs from entity sets and legacy media
                        url_pairs = []
                        url_pairs.extend(self._collect_entity_url_pairs(note_result))
                        # Merge in legacy payload URLs (media photo/video links)
                        legacy_payload = data.get('legacy', {}) if isinstance(data, dict) else {}
                        url_pairs.extend(self._collect_entity_url_pairs(legacy_payload))
                        # Build final URL list from expanded values only (no t.co)
                        urls = []
                        seen: Set[str] = set()
                        for p in url_pairs:
                            expanded = p.get('expanded')
                            if expanded and expanded not in seen:
                                seen.add(expanded)
                                urls.append(expanded)
                        # Replace t.co links in the visible text
                        note_text = self._replace_tco_in_text(note_text, url_pairs)

                        # Flatten the note tweet data - simplified for research
                        tweet = {
                            "id": data.get('id_str') or data.get('rest_id') or '',
                            "text": note_text,
                            "created_at": data.get('created_at') or '',
                            "retweet_count": data.get('retweet_count', 0),
                            "favorite_count": data.get('favorite_count', 0),
                            "reply_count": data.get('reply_count', 0),
                            "quote_count": data.get('quote_count', 0),
                            "urls": urls
                        }
                        results.append(tweet)
                        # Avoid recursing further into this specific tweet object
                        return
            
            # If no note_tweet, check if it contains 'full_text'
            if (isinstance(data.get('full_text'), str) and 
                data['full_text'].strip() != ''):
                
                # Collect URLs from legacy entities and media
                url_pairs = self._collect_entity_url_pairs(data)
                urls = []
                seen: Set[str] = set()
                for p in url_pairs:
                    expanded = p.get('expanded')
                    if expanded and expanded not in seen:
                        seen.add(expanded)
                        urls.append(expanded)
                # Replace t.co links in text
                full_text = self._replace_tco_in_text(data['full_text'], url_pairs)
                
                tweet = {
                    "id": data.get('id_str') or data.get('rest_id') or '',
                    "text": full_text,
                    "created_at": data.get('created_at') or '',
                    "retweet_count": data.get('retweet_count', 0),
                    "favorite_count": data.get('favorite_count', 0),
                    "reply_count": data.get('reply_count', 0),
                    "quote_count": data.get('quote_count', 0),
                    "urls": urls
                }
                results.append(tweet)
                # Avoid recursing further into this specific tweet object
                # (though it might contain nested quotes, we simplify for now)
                return

            # If no 'full_text' here, recurse into its properties
            for key, value in data.items():
                self._find_full_text_recursively(value, results)

# Example usage and testing
if __name__ == "__main__":
    # Initialize tools
    tools = Tools()
    
    # Test Twitter profile lookup
    print("Testing Twitter profile lookup...")
    profile = tools.get_twitter_profile("elonmusk")
    print(json.dumps(profile, indent=2)) 
