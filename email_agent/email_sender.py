"""
Email sender module for sending deal notifications via Gmail.
Converted from JavaScript email_notify.js to Python.
"""

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
from datetime import datetime
import pytz
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self):
        """Initialize email sender with Gmail credentials."""
        self.gmail_user = os.getenv('GMAIL_USER')
        self.gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        
        if not self.gmail_user or not self.gmail_password:
            logger.warning("Gmail credentials not configured in .env file")
            logger.warning(f"GMAIL_USER: {'Set' if self.gmail_user else 'Not set'}")
            logger.warning(f"GMAIL_APP_PASSWORD: {'Set' if self.gmail_password else 'Not set'}")
            raise ValueError("Missing Gmail credentials")
        
        # Clean password (remove spaces that Gmail shows for readability)
        self.gmail_password = self.gmail_password.replace(' ', '')
        
        logger.info(f"Initialized Gmail sender for: {self.gmail_user}")
        logger.info(f"Password length: {len(self.gmail_password)} characters")
    
    def load_recipients(self) -> List[str]:
        """
        Load email recipients from email_recipients.txt file.
        
        Returns:
            List of valid email addresses
        """
        recipients_file = os.path.join(os.path.dirname(__file__), 'email_recipients.txt')
        
        try:
            with open(recipients_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            emails = [
                email.strip() 
                for email in content.split('\n') 
                if email.strip() and '@' in email.strip()
            ]
            
            logger.info(f"📧 Loaded {len(emails)} email recipients")
            return emails
            
        except Exception as e:
            logger.error(f"⚠️ Could not load email recipients: {str(e)}")
            return []
    
    def send_deals_email(self, deals: List[Dict], stats: Optional[Dict] = None, subject_hook: Optional[str] = None) -> bool:
        """
        Send email with exceptional deals to all recipients.
        
        Args:
            deals: List of deal dictionaries with summaries
            stats: Optional statistics about the processing
            subject_hook: Optional custom subject line hook
            
        Returns:
            True if at least one email was sent successfully
        """
        try:
            logger.info("📧 Starting email notification process...")
            
            # Load recipients
            recipients = self.load_recipients()
            if not recipients:
                logger.warning("⚠️ No email recipients configured, skipping email notification")
                return False
            
            # Generate email content
            subject, html_content = self._generate_email_content(deals, stats, subject_hook)
            
            # Send to each recipient
            success_count = 0
            for recipient in recipients:
                if self._send_single_email(recipient, subject, html_content):
                    success_count += 1
            
            logger.info(f"📧 Email notification complete: {success_count}/{len(recipients)} sent successfully")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"⚠️ Email notification system error: {str(e)}")
            return False
    
    def _send_single_email(self, recipient: str, subject: str, html_content: str) -> bool:
        """
        Send email to a single recipient using Gmail SMTP.
        
        Args:
            recipient: Email address to send to
            subject: Email subject
            html_content: HTML email body
            
        Returns:
            True if email was sent successfully
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"Ava - Reforge <{self.gmail_user}>"
            msg['To'] = recipient
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send via Gmail SMTP
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
            
            logger.info(f"📧 Email sent successfully to: {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"⚠️ Failed to send email to {recipient}: {str(e)}")
            return False
    
    def _generate_email_content(self, deals: List[Dict], stats: Optional[Dict] = None, subject_hook: Optional[str] = None) -> tuple[str, str]:
        """
        Generate email subject and HTML content for deals notification.
        
        Args:
            deals: List of deal dictionaries with summaries
            stats: Optional statistics
            subject_hook: Optional custom subject line hook
            
        Returns:
            Tuple of (subject, html_content)
        """
        # Get current timestamp in Eastern Time
        eastern = pytz.timezone('America/New_York')
        timestamp = datetime.now(eastern).strftime('%B %d, %Y at %I:%M %p ET')
        
        # Subject line - use dynamic hook if provided
        if subject_hook:
            subject = f"Ava's Deal Insights: {subject_hook}"
        else:
            # Fallback subject
            subject = f"Ava's Deal Insights: {len(deals)} exceptional crypto opportunities with explosive growth potential"
        
        # HTML content
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; color: #333;">
            <div style="background: linear-gradient(135deg, #0066cc 0%, #004499 100%); padding: 30px; border-radius: 8px 8px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 28px;">🚀 Exceptional Investment Opportunities</h1>
                <p style="color: #e6f2ff; margin: 10px 0 0 0; font-size: 16px;">Ava's Priority HIGH Deals - Crypto/Web3 Focus</p>
            </div>
            
            <div style="background: #f8f9fa; padding: 20px; border-left: 4px solid #0066cc;">
                <p style="margin: 0; font-size: 16px; line-height: 1.6;">
                    I've identified {len(deals)} exceptional opportunities in the crypto/web3 space that meet our high-priority investment criteria. 
                    These deals represent compelling opportunities with strong fundamentals, innovative technology, and significant market potential.
                </p>
            </div>
            
            <div style="padding: 20px;">
        """
        
        # Add each deal
        for i, deal in enumerate(deals, 1):
            summary = deal.get('summary', {})
            
            html += f"""
                <div style="background: white; border: 1px solid #e1e8ed; border-radius: 8px; padding: 25px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <div style="border-bottom: 2px solid #0066cc; padding-bottom: 15px; margin-bottom: 20px;">
                        <h2 style="margin: 0; color: #0066cc; font-size: 24px;">
                            {i}. {deal['title']}
                        </h2>
                        <p style="margin: 8px 0 0 0; color: #657786; font-size: 14px;">
                            Created: {self._format_date(deal.get('created_time', ''))}
                        </p>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; margin: 0 0 10px 0; font-size: 18px;">📋 Overview</h3>
                        <p style="margin: 0; line-height: 1.6; color: #333;">
                            {summary.get('description', 'No description available')}
                        </p>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; margin: 0 0 10px 0; font-size: 18px;">🎯 Why This Deal Is Exceptional</h3>
                        <div style="color: #333; line-height: 1.8;">
                            {self._format_bullet_points(summary.get('why_interesting', ''))}
                        </div>
                    </div>
                    
                    <div style="background: #f0f8ff; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                        <h3 style="color: #0066cc; margin: 0 0 8px 0; font-size: 16px;">💡 Key Investment Highlights</h3>
                        <p style="margin: 0; color: #333; line-height: 1.6;">
                            {summary.get('highlights', 'Strong investment potential identified.')}
                        </p>
                    </div>
                    
                    <div style="text-align: center; margin-top: 20px;">
                        <a href="{deal.get('external_url', '#')}" 
                           style="background: #0066cc; color: white; padding: 12px 30px; text-decoration: none; 
                                  border-radius: 6px; font-weight: bold; display: inline-block; 
                                  box-shadow: 0 2px 4px rgba(0,102,204,0.3);">
                           📊 View Full Analysis
                        </a>
                    </div>
                </div>
            """
        
        # Add footer
        html += f"""
            </div>
            
            <div style="background: #f8f9fa; padding: 30px; border-top: 1px solid #e1e8ed; text-align: center;">
                <p style="margin: 0 0 10px 0; color: #657786; font-size: 14px;">
                    This analysis was generated by Ava's AI-powered research system
                </p>
                <p style="margin: 0; color: #657786; font-size: 12px;">
                    {timestamp}
                </p>
            </div>
            
            <div style="padding: 20px; text-align: center; color: #657786; font-size: 12px;">
                <p style="margin: 10px 0;"><strong>Ava</strong><br>
                Autonomous Investment Partner at Reforge</p>
                <p style="margin: 10px 0;">
                    This email contains confidential investment analysis. 
                    Please do not forward without permission.
                </p>
            </div>
        </div>
        """
        
        return subject, html
    
    def _format_date(self, iso_date: str) -> str:
        """Format ISO date string to readable format."""
        try:
            dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
            return dt.strftime('%B %d, %Y')
        except:
            return "Recently"
    
    def _format_bullet_points(self, text: str) -> str:
        """Convert bullet points to HTML format."""
        if not text:
            return "<p>• Strong investment opportunity identified</p>"
        
        lines = text.strip().split('\n')
        formatted = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith('•') or line.startswith('-') or line.startswith('*'):
                # Remove bullet and add as formatted HTML
                content = line.lstrip('•-* ').strip()
                formatted += f'<p style="margin: 5px 0; padding-left: 20px;">• {content}</p>'
            elif line:
                # Add non-bullet lines as regular paragraphs
                formatted += f'<p style="margin: 5px 0; padding-left: 20px;">• {line}</p>'
        
        return formatted


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test email sender
    sender = EmailSender()
    
    # Test with sample deal
    test_deals = [{
        "title": "Example DeFi Protocol",
        "created_time": "2024-01-15T10:30:00Z",
        "external_url": "https://notion.so/example",
        "summary": {
            "description": "Example DeFi Protocol is revolutionizing automated market making with advanced liquidity features. The team brings deep expertise from leading DeFi protocols.",
            "why_interesting": "• Former Uniswap and Aave engineers with proven track record\n• $50M+ TVL committed from tier-1 partners\n• Novel approach to impermanent loss protection",
            "highlights": "Positioned to capture significant market share in the next generation of DeFi infrastructure with unique cross-chain capabilities."
        }
    }]
    
    # Send test email
    success = sender.send_deals_email(test_deals, {"total_analyzed": 50})
    print(f"\nEmail sent: {success}")