# Email Agent Implementation Plan

## Overview
The Email Agent automates sending exceptional crypto/web3 investment deals to a list of recipients. It reads from Notion database, filters for high-priority deals, generates summaries using GPT, and sends emails via Gmail.

## Key Features
1. **Notion Integration**: Read deals from internal database, filter by "Ava's Priority HIGH"
2. **Email Status Tracking**: Skip deals already marked as "emailed"
3. **Date Filtering**: Only process deals from the last 2 months
4. **GPT Summarization**: Generate compelling summaries explaining why each deal is interesting
5. **Batch Limiting**: Send maximum 5 deals per run
6. **External Links**: Use external database links for recipient viewing
7. **Status Updates**: Mark deals as "emailed" after sending

## Implementation Steps

### 1. Setup and Configuration
- [x] Create `impl.md` documentation
- [x] Create main script `email_agent.py`
- [x] Set up dependencies in `requirements.txt`
- [x] Configure environment variables

### 2. Notion Integration Module
- [x] Create `notion_client.py` for database operations
- [x] Implement filtering logic:
  - Priority = "Ava's Priority HIGH" (corrected to "High")
  - Email Status != "emailed"
  - Created date within last 2 months
- [x] Fetch page content for selected deals
- [x] Update Email Status field after sending

### 3. Email Module
- [x] Convert `email_notify.js` logic to Python
- [x] Create `email_sender.py` with Gmail integration
- [x] Load recipients from `email_recipients.txt`
- [x] Format HTML emails with deal summaries

### 4. GPT Integration
- [x] Create prompt for deal summarization
- [x] Implement OpenAI API integration
- [x] Generate high-level descriptions and "why it's interesting" insights

### 5. Main Orchestration
- [x] Combine all modules in `email_agent.py`
- [x] Implement batch processing (max 5 deals)
- [x] Add error handling and logging
- [x] Create external Notion links using NOTION_DATABASE_ID_EXT

## File Structure
```
email_agent/
├── impl.md                 # This file
├── email_agent.py         # Main orchestration script
├── notion_deals_client.py # Notion database operations
├── email_sender.py        # Gmail integration (converted from JS)
├── gpt_summarizer.py      # OpenAI integration for summaries
├── requirements.txt       # Python dependencies
├── email_recipients.txt   # List of email recipients (existing)
└── logs/                  # Logging directory
```

## GPT Prompt for Deal Summarization
```
You are an investment analyst at a crypto/web3 venture fund. Analyze this deal report and provide:

1. A concise high-level description (2-3 sentences) of what the company does
2. Why this deal is particularly interesting for crypto/web3 investors (2-3 bullet points) based on the scoring towards the end of deal report 
3. Key investment highlights that make this a priority opportunity

Focus on:
- Unique value proposition in the crypto/web3 space
- Market opportunity and timing
- Team/technology advantages
- Potential returns or strategic value

Deal Report:
{page_content}
```

## Technical Requirements
- Python 3.8+
- notion-client
- openai
- google-auth
- google-auth-oauthlib
- google-auth-httplib2
- email/smtplib (built-in)
- python-dotenv

## Environment Variables Needed
- NOTION_API_KEY (existing)
- NOTION_DATABASE_ID (internal database)
- NOTION_DATABASE_ID_EXT (external database for links)
- OPENAI_API_KEY (existing)
- GMAIL_USER (from JS file)
- GMAIL_APP_PASSWORD (from JS file)

## Usage Instructions

### Installation
```bash
cd email_agent
pip install -r requirements.txt
```

### Running the Email Agent

1. **Full run (send emails and update Notion):**
```bash
python email_agent.py
```

2. **Dry run (test without sending emails):**
```bash
python email_agent.py --dry-run
```

3. **Specify maximum deals to process:**
```bash
python email_agent.py --max-deals 3
```

4. **Combine options:**
```bash
python email_agent.py --max-deals 2 --dry-run
```

### Testing Individual Components

1. **Test Notion client:**
```bash
python notion_deals_client.py
```

2. **Test GPT summarizer:**
```bash
python gpt_summarizer.py
```

3. **Test email sender:**
```bash
python email_sender.py
```

### Logs
- All execution logs are saved in `email_agent/logs/`
- Log files are timestamped: `email_agent_YYYYMMDD_HHMMSS.log`

### Email Recipients
- Edit `email_recipients.txt` to add/remove recipients
- One email address per line
- Currently configured: c@reforge.vc

### Troubleshooting

1. **No deals found:**
   - Check that there are deals with "Ava's Priority" = "High" in Notion
   - Ensure deals have no "Email Status" or status is not "emailed"
   - Verify deals were created within the last 2 months

2. **Email sending fails:**
   - Verify GMAIL_USER and GMAIL_APP_PASSWORD in .env
   - Ensure Gmail app password is correct (no spaces)
   - Check that "Less secure app access" or app passwords are enabled

3. **GPT summarization errors:**
   - Verify OPENAI_API_KEY is set in .env
   - Check API quota/limits

4. **Notion access errors:**
   - Verify NOTION_API_KEY is correct
   - Check NOTION_DATABASE_ID and NOTION_DATABASE_ID_EXT are set
   - Ensure the Notion integration has access to the database