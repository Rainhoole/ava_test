#!/usr/bin/env python3
"""
Twitter MCP Server for Claude Agent SDK.

Provides Twitter data retrieval tools via Model Context Protocol.

Usage:
    # As MCP server (called by Claude Agent SDK)
    python twitter_mcp.py

    # Test mode
    python twitter_mcp.py --test @username
"""

import os
import sys
import json
import asyncio
import argparse
import requests
from typing import Any

from dotenv import load_dotenv
load_dotenv()

# Try to import mcp, provide helpful error if not installed
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)


class TwitterAPI:
    """Twitter API client using RapidAPI."""

    def __init__(self):
        self.api_key = os.getenv('RAPID_API_KEY')
        if not self.api_key:
            raise ValueError("RAPID_API_KEY environment variable not set")

    def get_profile(self, username: str) -> dict:
        """Get Twitter profile by username."""
        clean_username = username.replace('@', '')

        url = "https://twitter283.p.rapidapi.com/UserResultByScreenName"
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "twitter283.p.rapidapi.com",
        }
        params = {"username": clean_username}

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Extract user data
        user_results = data.get("data", {}).get("user_results", {})
        result = user_results.get("result", {})

        if not result:
            return {"error": f"Profile not found for @{clean_username}"}

        core = result.get("core", {})
        profile_bio = result.get("profile_bio", {})
        relationship_counts = result.get("relationship_counts", {})
        tweet_counts = result.get("tweet_counts", {})

        # Extract website URL from entities
        website_url = None
        entities = profile_bio.get("entities", {})
        urls = entities.get("urls", [])
        if urls:
            website_url = urls[0].get("expanded_url") or urls[0].get("url")

        return {
            "username": core.get("screen_name", clean_username),
            "name": core.get("name", "Unknown"),
            "bio": profile_bio.get("description", ""),
            "website_url": website_url,
            "followers_count": relationship_counts.get("followers", 0),
            "following_count": relationship_counts.get("following", 0),
            "tweets_count": tweet_counts.get("tweets", 0),
            "user_id": result.get("rest_id", ""),
            "created_at": core.get("created_at", ""),
            "verified": core.get("verified", False),
            "profile_image_url": core.get("profile_image_url_https", ""),
        }

    def get_tweets(self, username: str, limit: int = 20) -> dict:
        """Get recent tweets from a user."""
        # First get user ID
        profile = self.get_profile(username)
        if "error" in profile:
            return profile

        user_id = profile.get("user_id")
        if not user_id:
            return {"error": "Could not get user ID"}

        url = "https://twitter283.p.rapidapi.com/UserTweets"
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "twitter283.p.rapidapi.com",
        }
        params = {"user_id": user_id}

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Extract tweets
        tweets = []
        self._extract_tweets(data, tweets, limit)

        return {
            "username": username.replace('@', ''),
            "user_id": user_id,
            "total_tweets": len(tweets),
            "tweets": tweets[:limit]
        }

    def _extract_tweets(self, data: Any, results: list, limit: int):
        """Recursively extract tweets from API response."""
        if len(results) >= limit:
            return

        if isinstance(data, dict):
            # Check for full_text (tweet content)
            if "full_text" in data and isinstance(data["full_text"], str):
                # Extract URLs from entities
                urls = []
                entities = data.get("entities", {})
                for url_obj in entities.get("urls", []):
                    expanded = url_obj.get("expanded_url") or url_obj.get("url")
                    if expanded:
                        urls.append(expanded)

                tweet = {
                    "id": data.get("id_str", ""),
                    "text": data["full_text"],
                    "created_at": data.get("created_at", ""),
                    "retweet_count": data.get("retweet_count", 0),
                    "favorite_count": data.get("favorite_count", 0),
                    "urls": urls,
                }
                results.append(tweet)

            # Recurse into nested objects
            for value in data.values():
                self._extract_tweets(value, results, limit)

        elif isinstance(data, list):
            for item in data:
                self._extract_tweets(item, results, limit)

    def get_following(self, username: str, limit: int = 50, oldest_first: bool = False) -> dict:
        """Get accounts a user follows."""
        clean_username = username.replace('@', '')

        url = "https://twitter283.p.rapidapi.com/FollowingLight"
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "twitter283.p.rapidapi.com",
        }
        params = {"username": clean_username, "count": str(min(limit, 200))}

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("error") == "Not authorized.":
            return {"error": "Profile is private"}

        users = data.get("users", [])

        profiles = []
        for user in users:
            profiles.append({
                "username": user.get("screen_name", ""),
                "name": user.get("name", ""),
                "bio": user.get("description", ""),
                "followers": user.get("followers_count", 0),
                "verified": user.get("verified", False),
            })

        # Optionally reverse to get oldest follows first (useful for finding founders)
        if oldest_first:
            profiles = profiles[::-1]

        return {
            "username": clean_username,
            "total_following": len(profiles),
            "oldest_first": oldest_first,
            "profiles": profiles[:limit]
        }


# Create MCP server
server = Server("twitter-research")

# Initialize Twitter API (lazy loading)
_twitter_api = None


def get_twitter_api() -> TwitterAPI:
    global _twitter_api
    if _twitter_api is None:
        _twitter_api = TwitterAPI()
    return _twitter_api


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Twitter tools."""
    return [
        Tool(
            name="get_twitter_profile",
            description="""Get Twitter profile information including bio, follower counts, website URL, and account details.

Use this FIRST to:
- Check Early Exit conditions (foundation, regional, inactive, later stage)
- Get the website URL for scraping
- Understand the account's reach and activity level""",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Twitter username (with or without @)"
                    }
                },
                "required": ["username"]
            }
        ),
        Tool(
            name="get_twitter_tweets",
            description="""Get recent tweets from a Twitter user.

Use this to:
- Find URLs shared in tweets (for scraping)
- Assess technical depth and communication style
- Identify announcements, partnerships, product launches
- Check activity patterns and engagement levels""",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Twitter username (with or without @)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tweets to retrieve (default: 20)",
                        "default": 20
                    }
                },
                "required": ["username"]
            }
        ),
        Tool(
            name="get_twitter_following",
            description="""Get accounts a Twitter user follows.

Use with oldest_first=true to:
- Discover early team members and founders
- Find investors and advisors
- Identify strategic partners

The oldest follows often reveal the founding team and early supporters.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Twitter username (with or without @)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of profiles to retrieve (default: 50)",
                        "default": 50
                    },
                    "oldest_first": {
                        "type": "boolean",
                        "description": "If true, return oldest follows first (useful for finding founders)",
                        "default": False
                    }
                },
                "required": ["username"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a Twitter tool."""
    try:
        twitter = get_twitter_api()

        if name == "get_twitter_profile":
            result = twitter.get_profile(arguments.get("username", ""))

        elif name == "get_twitter_tweets":
            result = twitter.get_tweets(
                arguments.get("username", ""),
                arguments.get("limit", 20)
            )

        elif name == "get_twitter_following":
            result = twitter.get_following(
                arguments.get("username", ""),
                arguments.get("limit", 50),
                arguments.get("oldest_first", False)
            )

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def run_server():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def test_mode(username: str):
    """Test Twitter API directly."""
    print(f"Testing Twitter API for @{username}")
    print("=" * 50)

    try:
        twitter = get_twitter_api()

        print("\n1. Getting profile...")
        profile = twitter.get_profile(username)
        print(json.dumps(profile, indent=2))

        if "error" not in profile:
            print("\n2. Getting tweets...")
            tweets = twitter.get_tweets(username, limit=5)
            print(json.dumps(tweets, indent=2))

            print("\n3. Getting following (oldest first)...")
            following = twitter.get_following(username, limit=10, oldest_first=True)
            print(json.dumps(following, indent=2))

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twitter MCP Server")
    parser.add_argument("--test", type=str, help="Test mode: provide Twitter username")
    args = parser.parse_args()

    if args.test:
        test_mode(args.test)
    else:
        # Run as MCP server
        asyncio.run(run_server())
