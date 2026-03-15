#!/usr/bin/env python3
"""
Email Agent - Sends exceptional crypto/web3 deals to recipients
Reads high-priority deals from Notion, generates summaries, and emails them
"""

import os
import sys
import logging
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notion_deals_client import NotionDealsClient
from gpt_summarizer import DealSummarizer
from email_sender import EmailSender

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Setup logging
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f'email_agent_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class EmailAgent:
    def __init__(self):
        """Initialize the Email Agent with all required components."""
        logger.info("=" * 60)
        logger.info("Email Agent Starting")
        logger.info("=" * 60)
        
        try:
            self.notion_client = NotionDealsClient()
            self.summarizer = DealSummarizer()
            self.email_sender = EmailSender()
            logger.info("All components initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize components: {str(e)}")
            raise
    
    def run(self, max_deals: int = 5, min_score: int = 84, dry_run: bool = False) -> Dict:
        """
        Main execution method for the Email Agent.
        
        Args:
            max_deals: Maximum number of deals to process (default: 5)
            min_score: Minimum Ava's Score threshold (default: 84)
            dry_run: If True, don't send emails or update Notion (default: False)
            
        Returns:
            Dictionary with execution statistics
        """
        stats = {
            "deals_found": 0,
            "deals_processed": 0,
            "deals_emailed": 0,
            "errors": []
        }
        
        try:
            # Step 1: Fetch high-scoring deals from Notion
            logger.info(f"Fetching deals with score >= {min_score} (max: {max_deals})...")
            deals = self.notion_client.get_high_priority_deals(max_deals=max_deals, min_score=min_score)
            stats["deals_found"] = len(deals)
            
            if not deals:
                logger.info(f"No deals found with score >= {min_score}")
                return stats
            
            logger.info(f"Found {len(deals)} deals with score >= {min_score} to process")
            
            # Step 2: Generate summaries for each deal
            processed_deals = []
            hooks = []  # Collect hooks for subject line
            
            for deal in deals:
                try:
                    logger.info(f"\nProcessing deal: {deal['title']}")
                    
                    # Generate summary using GPT
                    summary = self.summarizer.summarize_deal(
                        deal_title=deal['title'],
                        deal_content=deal['content']
                    )
                    
                    # Add summary to deal
                    deal['summary'] = summary
                    processed_deals.append(deal)
                    stats["deals_processed"] += 1
                    
                    # Collect hook for subject line
                    if summary.get('hook'):
                        hooks.append(summary['hook'])
                    
                    logger.info(f"✓ Successfully generated summary for: {deal['title']}")
                    
                except Exception as e:
                    logger.error(f"✗ Error processing deal {deal['title']}: {str(e)}")
                    stats["errors"].append({
                        "deal": deal['title'],
                        "error": str(e)
                    })
            
            if not processed_deals:
                logger.warning("No deals were successfully processed")
                return stats
            
            # Step 3: Generate dynamic subject line from hooks
            subject_hook = None
            if hooks:
                logger.info(f"\nGenerating dynamic subject line from {len(hooks)} hooks...")
                subject_hook = self.summarizer.generate_email_subject(hooks)
                logger.info(f"Generated subject hook: {subject_hook}")
            
            # Step 4: Send email with all processed deals
            if not dry_run:
                logger.info(f"\nSending email with {len(processed_deals)} deals...")
                email_sent = self.email_sender.send_deals_email(
                    deals=processed_deals,
                    stats={
                        "total_analyzed": stats["deals_found"],
                        "total_processed": stats["deals_processed"]
                    },
                    subject_hook=subject_hook
                )
                
                if email_sent:
                    stats["deals_emailed"] = len(processed_deals)
                    logger.info(f"✓ Email sent successfully with {len(processed_deals)} deals")
                    
                    # Step 5: Mark deals as emailed in Notion
                    logger.info("\nUpdating Notion database...")
                    page_ids = [deal['id'] for deal in processed_deals]
                    
                    if self.notion_client.mark_as_emailed(page_ids):
                        logger.info("✓ All deals marked as 'emailed' in Notion")
                    else:
                        logger.warning("⚠ Some deals may not have been marked as 'emailed'")
                else:
                    logger.error("✗ Failed to send email")
            else:
                logger.info("\n[DRY RUN] Would have sent email with the following:")
                logger.info(f"Subject: Ava's Deal Insights: {subject_hook or 'Exceptional crypto opportunities'}")
                logger.info("\nDeals included:")
                for i, deal in enumerate(processed_deals, 1):
                    logger.info(f"  {i}. {deal['title']}")
                    logger.info(f"     - Hook: {deal['summary'].get('hook', 'N/A')}")
                    logger.info(f"     - Description: {deal['summary']['description'][:100]}...")
                    logger.info(f"     - External URL: {deal['external_url']}")
                logger.info("\n[DRY RUN] Would have marked these deals as 'emailed' in Notion")
            
            # Final summary
            logger.info("\n" + "=" * 60)
            logger.info("Email Agent Execution Summary")
            logger.info("=" * 60)
            logger.info(f"Deals found: {stats['deals_found']}")
            logger.info(f"Deals processed: {stats['deals_processed']}")
            logger.info(f"Deals emailed: {stats['deals_emailed']}")
            if stats['errors']:
                logger.info(f"Errors encountered: {len(stats['errors'])}")
                for error in stats['errors']:
                    logger.info(f"  - {error['deal']}: {error['error']}")
            logger.info("=" * 60)
            
            return stats
            
        except Exception as e:
            logger.error(f"Fatal error in Email Agent: {str(e)}")
            stats["errors"].append({
                "deal": "SYSTEM",
                "error": str(e)
            })
            return stats


def main():
    """Main entry point for the Email Agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Email Agent - Send exceptional deals to recipients')
    parser.add_argument('--max-deals', type=int, default=5, help='Maximum number of deals to process (default: 5)')
    parser.add_argument('--min-score', type=int, default=84, help='Minimum Ava\'s Score threshold (default: 84)')
    parser.add_argument('--dry-run', action='store_true', help='Run without sending emails or updating Notion')
    
    args = parser.parse_args()
    
    try:
        agent = EmailAgent()
        stats = agent.run(max_deals=args.max_deals, min_score=args.min_score, dry_run=args.dry_run)
        
        # Exit with error code if there were errors
        if stats['errors']:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Failed to run Email Agent: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()