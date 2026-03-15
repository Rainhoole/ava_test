"""
GPT-based summarizer for generating compelling deal summaries.
Uses OpenAI to create investment-focused summaries explaining why deals are interesting.
"""

import os
import logging
from typing import Dict, Optional, List
import warnings

# Suppress Pydantic serialization warnings
warnings.filterwarnings("ignore", category=UserWarning, message=".*Pydantic.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*serializ.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*unexpected.*")

# Load environment variables first
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Clear proxy settings that can interfere with API calls
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''

from openai import OpenAI

# Silence httpx logger
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class DealSummarizer:
    def __init__(self):
        """Initialize OpenAI client."""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        model = os.getenv('OPENAI_MODEL')
        if not model:
            raise ValueError("OPENAI_MODEL not found in environment variables")
        
        # Create OpenAI client - let it use default settings
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info("Initialized GPT summarizer")
    
    def summarize_deal(self, deal_title: str, deal_content: str) -> Dict[str, str]:
        """
        Generate a compelling summary of a deal for investors.
        
        Args:
            deal_title: The title/name of the deal
            deal_content: Full content from the Notion page
            
        Returns:
            Dictionary with 'description', 'why_interesting', and 'highlights'
        """
        prompt = f"""You are an investment analyst at a leading crypto/web3 venture fund. Analyze this deal report and provide:

1. A concise high-level description (2-3 sentences) of what the company does
2. Why this deal is particularly interesting for crypto/web3 investors (2-3 bullet points) - focus on the scoring criteria and evaluation provided at the end of the report
3. Key investment highlights that make this a priority opportunity

Focus on:
- Unique value proposition in the crypto/web3 space
- Market opportunity and timing (from the scoring)
- Team/technology advantages (from the evaluation)
- Potential returns or strategic value
- Why this scored as a HIGH priority deal
- Reference specific scores or criteria that made this exceptional

Keep the tone professional but enthusiastic, suitable for sophisticated investors.

Deal Title: {deal_title}

Deal Report:
{deal_content}

Format your response as:
HOOK:
[One eye-catching sentence that would make investors immediately interested - focus on metrics, growth, market size, or unique value prop]

DESCRIPTION:
[Your 2-3 sentence description]

WHY IT'S INTERESTING:
• [Bullet point 1]
• [Bullet point 2]
• [Bullet point 3]

KEY HIGHLIGHTS:
[1-2 sentences on the most compelling investment highlights]"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a sophisticated crypto/web3 investment analyst who identifies exceptional opportunities. Focus on what makes each deal unique and compelling for venture investors."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_completion_tokens=500
            )
            
            # Parse the response
            summary_text = response.choices[0].message.content.strip()
            
            # Log the raw response for debugging
            logger.debug(f"Raw GPT response for {deal_title}:\n{summary_text}")
            
            # Extract sections
            sections = self._parse_summary_sections(summary_text)
            
            logger.info(f"Generated summary for deal: {deal_title}")
            logger.debug(f"Parsed sections: hook={bool(sections.get('hook'))}, desc={bool(sections.get('description'))}")
            return sections
            
        except Exception as e:
            logger.error(f"Error generating summary for {deal_title}: {str(e)}")
            # Return a fallback summary
            return {
                "hook": f"{deal_title} emerges as a game-changing crypto opportunity with exponential growth potential.",
                "description": f"{deal_title} is an innovative crypto/web3 project with significant potential in the current market.",
                "why_interesting": "• Strong founding team with proven track record\n• Addresses a clear market need in the crypto space\n• Well-positioned for the current market cycle",
                "highlights": "This opportunity represents a compelling investment in the evolving crypto ecosystem."
            }
    
    def _parse_summary_sections(self, summary_text: str) -> Dict[str, str]:
        """Parse the GPT response into structured sections."""
        sections = {
            "hook": "",
            "description": "",
            "why_interesting": "",
            "highlights": ""
        }
        
        try:
            # Split by section headers
            parts = summary_text.split('\n\n')
            
            current_section = None
            for part in parts:
                part = part.strip()
                
                # Remove any markdown formatting and check for section headers
                clean_part = part.replace("**", "").strip()
                
                if clean_part.startswith("HOOK:"):
                    current_section = "hook"
                    sections[current_section] = clean_part.replace("HOOK:", "").strip()
                
                elif clean_part.startswith("DESCRIPTION:"):
                    current_section = "description"
                    sections[current_section] = clean_part.replace("DESCRIPTION:", "").strip()
                
                elif clean_part.startswith("WHY IT'S INTERESTING:") or clean_part.startswith("WHY IT'S INTERESTING:"):
                    current_section = "why_interesting"
                    sections[current_section] = clean_part.replace("WHY IT'S INTERESTING:", "").replace("WHY IT'S INTERESTING:", "").strip()
                
                elif clean_part.startswith("KEY HIGHLIGHTS:"):
                    current_section = "highlights"
                    sections[current_section] = clean_part.replace("KEY HIGHLIGHTS:", "").strip()
                
                elif current_section:
                    # Continuation of previous section
                    # Clean up markdown formatting in bullet points
                    clean_continuation = part.replace("- *", "• ").replace("*:", ":").replace("*", "")
                    sections[current_section] += "\n" + clean_continuation
            
        except Exception as e:
            logger.error(f"Error parsing summary sections: {str(e)}")
            # Return the full text in description as fallback
            sections["description"] = summary_text
        
        return sections
    
    def generate_email_subject(self, deal_hooks: List[str]) -> str:
        """
        Generate a compelling email subject line from deal hooks.
        
        Args:
            deal_hooks: List of hook sentences from each deal
            
        Returns:
            Eye-catching subject line combining the hooks
        """
        if not deal_hooks:
            return "Breakthrough crypto opportunities with explosive growth potential"
        
        if len(deal_hooks) == 1:
            # Single deal - use its hook directly
            return deal_hooks[0]
        
        # Multiple deals - create a combined hook
        try:
            # Create a prompt to combine multiple hooks into one compelling sentence
            hooks_text = "\n".join([f"- {hook}" for hook in deal_hooks])
            
            prompt = f"""Combine these investment opportunity hooks into ONE compelling sentence that captures the essence of all deals:

{hooks_text}

Create a single eye-catching sentence that would make investors immediately want to read more. Focus on the most impressive metrics, growth rates, or market opportunities. Keep it under 100 characters if possible.

Output ONLY the combined sentence, nothing else."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a master copywriter who creates irresistible email subject lines for crypto/web3 investment opportunities."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_completion_tokens=100
            )
            
            combined_hook = response.choices[0].message.content.strip()
            # Remove quotes if GPT added them
            combined_hook = combined_hook.strip('"\'')
            
            logger.info(f"Generated combined email hook: {combined_hook}")
            return combined_hook
            
        except Exception as e:
            logger.error(f"Error generating combined subject: {str(e)}")
            # Fallback to a generic but compelling subject
            return f"{len(deal_hooks)} explosive crypto opportunities with {deal_hooks[0].split()[0]} potential"


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    summarizer = DealSummarizer()
    
    # Test with sample content
    test_deal = {
        "title": "Example DeFi Protocol",
        "content": """
        Example DeFi Protocol is building a revolutionary automated market maker (AMM) 
        with advanced features for liquidity providers. The team consists of former 
        engineers from Uniswap and Aave, with over $50M in TVL already committed 
        from early partners. Their unique approach to impermanent loss protection 
        and cross-chain liquidity aggregation positions them as a potential leader 
        in the next generation of DeFi infrastructure.
        """
    }
    
    summary = summarizer.summarize_deal(test_deal["title"], test_deal["content"])
    
    print("\nGenerated Summary:")
    print(f"\nDescription:\n{summary['description']}")
    print(f"\nWhy It's Interesting:\n{summary['why_interesting']}")
    print(f"\nKey Highlights:\n{summary['highlights']}")
