"""
Notion client for interacting with the deals database.
Handles filtering, fetching, and updating deal records.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from notion_client import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger(__name__)


class NotionDealsClient:
    def __init__(self):
        """Initialize Notion client with API key from environment."""
        self.notion_api_key = os.getenv('NOTION_API_KEY')
        self.internal_db_id = os.getenv('NOTION_DATABASE_ID')
        self.external_db_id = os.getenv('NOTION_DATABASE_ID_EXT')
        
        if not all([self.notion_api_key, self.internal_db_id, self.external_db_id]):
            raise ValueError("Missing required Notion environment variables")
        
        self.client = Client(auth=self.notion_api_key)
        logger.info("Initialized Notion client")
    
    def get_high_priority_deals(self, max_deals: int = 5, min_score: int = 84) -> List[Dict]:
        """
        Fetch high-scoring deals that haven't been emailed yet.
        
        Args:
            max_deals: Maximum number of deals to return (default: 5)
            min_score: Minimum Ava's Score threshold (default: 84)
            
        Returns:
            List of deal dictionaries with page content and metadata
        """
        # Calculate date 2 months ago
        two_months_ago = datetime.now(timezone.utc) - timedelta(days=60)
        
        try:
            # Query the database with filters
            # Build filter
            filter_query = {
                "and": [
                    {
                        "property": "Ava's Score",
                        "number": {
                            "greater_than_or_equal_to": min_score
                        }
                    },
                    {
                        "or": [
                            {
                                "property": "Email Status",
                                "select": {
                                    "does_not_equal": "Emailed"
                                }
                            },
                            {
                                "property": "Email Status",
                                "select": {
                                    "is_empty": True
                                }
                            }
                        ]
                    },
                    {
                        "timestamp": "created_time",
                        "created_time": {
                            "after": two_months_ago.isoformat()
                        }
                    }
                ]
            }
            
            logger.debug(f"Querying database with filter: {filter_query}")
            
            response = self.client.databases.query(
                database_id=self.internal_db_id,
                filter=filter_query,
                sorts=[
                    {
                        "timestamp": "created_time",
                        "direction": "descending"
                    }
                ],
                page_size=max_deals
            )
            
            deals = []
            skipped_page_ids = []  # Track pages to mark as emailed due to missing external entry
            
            for page in response['results'][:max_deals]:
                try:
                    # Check current email status for debugging
                    email_status = None
                    if 'Email Status' in page['properties']:
                        email_status_prop = page['properties']['Email Status']
                        if email_status_prop.get('select'):
                            email_status = email_status_prop['select'].get('name')
                    
                    logger.debug(f"Page {page['id']} - Email Status: {email_status}")
                    
                    # Get page content
                    page_content = self._get_page_content(page['id'])
                    
                    # Extract deal info
                    title = self._get_page_title(page)
                    
                    # Find the corresponding page in external database by title
                    external_url = self._find_page_in_external_database(title)
                    
                    # Skip this deal if not found in external database
                    if not external_url:
                        logger.warning(f"Skipping deal '{title}' - not found in external database")
                        skipped_page_ids.append(page['id'])
                        continue
                    
                    deal = {
                        'id': page['id'],
                        'title': title,
                        'created_time': page['created_time'],
                        'content': page_content,
                        'properties': page['properties'],
                        'external_url': external_url
                    }
                    deals.append(deal)
                    # Get Ava's Score for logging
                    avas_score = None
                    if 'Ava\'s Score' in page['properties']:
                        score_prop = page['properties']['Ava\'s Score']
                        if score_prop.get('formula') and score_prop['formula'].get('number') is not None:
                            avas_score = score_prop['formula']['number']
                    
                    logger.info(f"Fetched deal: {deal['title']} (Score: {avas_score}, Email Status: {email_status})")
                    
                except Exception as e:
                    logger.error(f"Error processing page {page['id']}: {str(e)}")
                    continue
            
            # Mark skipped deals as emailed to prevent repeated processing
            if skipped_page_ids:
                logger.info(f"Marking {len(skipped_page_ids)} deals as 'emailed' due to missing external database entries")
                self.mark_as_emailed(skipped_page_ids)
            
            logger.info(f"Found {len(deals)} deals with score >= {min_score} to process")
            return deals
            
        except Exception as e:
            logger.error(f"Error querying Notion database: {str(e)}")
            return []
    
    def _get_page_content(self, page_id: str) -> str:
        """
        Fetch the full content of a Notion page.
        
        Args:
            page_id: The ID of the page to fetch
            
        Returns:
            String containing the page content
        """
        try:
            # Get all blocks from the page
            blocks = self.client.blocks.children.list(block_id=page_id)
            
            content_parts = []
            for block in blocks['results']:
                block_text = self._extract_text_from_block(block)
                if block_text:
                    content_parts.append(block_text)
            
            return '\n\n'.join(content_parts)
            
        except Exception as e:
            logger.error(f"Error fetching page content for {page_id}: {str(e)}")
            return ""
    
    def _extract_text_from_block(self, block: Dict) -> Optional[str]:
        """Extract text content from a Notion block."""
        block_type = block['type']
        
        if block_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item']:
            rich_text = block.get(block_type, {}).get('rich_text', [])
            return ''.join([text['plain_text'] for text in rich_text])
        
        elif block_type == 'toggle':
            # Get toggle title and children
            toggle_text = ''.join([text['plain_text'] for text in block['toggle'].get('rich_text', [])])
            return toggle_text
        
        return None
    
    def _get_page_title(self, page: Dict) -> str:
        """Extract the title from a Notion page."""
        try:
            # Try to get Name property first
            if 'Name' in page['properties']:
                name_prop = page['properties']['Name']
                if name_prop['type'] == 'title' and name_prop['title']:
                    return name_prop['title'][0]['plain_text']
            
            # Fallback to any title property
            for prop_name, prop_value in page['properties'].items():
                if prop_value['type'] == 'title' and prop_value['title']:
                    return prop_value['title'][0]['plain_text']
            
            return "Untitled"
            
        except Exception as e:
            logger.error(f"Error extracting title: {str(e)}")
            return "Untitled"
    
    def _generate_external_url(self, page_id: str) -> str:
        """
        Generate external Notion URL for a page.
        This is a fallback method if we can't find the page in external database.
        
        Args:
            page_id: The ID of the page (with or without hyphens)
            
        Returns:
            External URL for the page
        """
        # Remove hyphens from page ID
        clean_id = page_id.replace('-', '')
        
        # Generate external database view URL with the page
        return f"https://www.notion.so/{self.external_db_id}?p={clean_id}"
    
    def _find_page_in_external_database(self, title: str) -> Optional[str]:
        """
        Search for a page by title in the external database.
        
        Args:
            title: The title of the page to search for
            
        Returns:
            The external URL if found, None otherwise
        """
        try:
            logger.debug(f"Searching external database for title: '{title}'")
            
            # First try exact match
            response = self.client.databases.query(
                database_id=self.external_db_id,
                filter={
                    "property": "Name",
                    "title": {
                        "equals": title
                    }
                }
            )
            
            if response['results']:
                # Get the first matching page
                external_page = response['results'][0]
                external_page_id = external_page['id'].replace('-', '')
                
                # Generate the proper external URL
                external_url = f"https://www.notion.so/{self.external_db_id}?p={external_page_id}"
                logger.info(f"Found external page for '{title}': {external_url}")
                return external_url
            else:
                logger.warning(f"No external page found for title: {title}")
                return None
                
        except Exception as e:
            logger.error(f"Error searching external database for '{title}': {str(e)}")
            return None
    
    def mark_as_emailed(self, page_ids: List[str]) -> bool:
        """
        Update the Email Status property to 'emailed' for the given pages.
        
        Args:
            page_ids: List of page IDs to update
            
        Returns:
            True if all updates succeeded, False otherwise
        """
        success_count = 0
        
        for page_id in page_ids:
            try:
                self.client.pages.update(
                    page_id=page_id,
                    properties={
                        "Email Status": {
                            "select": {
                                "name": "Emailed"
                            }
                        }
                    }
                )
                success_count += 1
                logger.info(f"Marked page {page_id} as emailed")
                
            except Exception as e:
                logger.error(f"Error updating page {page_id}: {str(e)}")
        
        return success_count == len(page_ids)


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    client = NotionDealsClient()
    deals = client.get_high_priority_deals(max_deals=1, min_score=84)
    
    if deals:
        print(f"\nFound {len(deals)} deals:")
        for deal in deals:
            print(f"\nTitle: {deal['title']}")
            print(f"External URL: {deal['external_url']}")
            print(f"Content preview: {deal['content'][:200]}...")
    else:
        print("No deals found")