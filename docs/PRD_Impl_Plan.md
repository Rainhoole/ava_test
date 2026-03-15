Deep Research System – PRD and Implementation Plan
Overview and Goals
We are building an AI-powered research assistant that can perform iterative, in-depth research on user-provided topics by combining web search, web content extraction, and large language model (LLM) analysis
mcp.so
. The system will take a query from the user, conduct multi-step research (refining queries and digging deeper as needed), and produce a comprehensive Markdown report of findings with references. The final research report will be stored in a Notion database for record-keeping and later review. Key goals include:
Iterative Deep Research: Automatically perform multiple rounds of searching and reading, guided by an LLM, to gather relevant information
mcp.so
.
LLM-Driven Analysis: Use an LLM (e.g. Gemini or GPT-4) to generate smart search queries, extract “learnings” from content, propose follow-up questions, and summarize findings
mcp.so
.
Asynchronous Architecture: Cleanly separate the front-end interface (JS) from the back-end research engine, so the UI remains responsive while heavy research tasks run asynchronously.
Notion Integration: Save the final research results to a Notion database (without altering its existing schema) as a persistent record (analogous to how a prior implementation used a SQL database
mcp.so
).
Extendability: Design the system with future enhancements in mind – e.g. Human feedback, Telegram bot interface, and Long-term memory (knowledge base) – with minimal refactoring needed when those are added. These features are out of scope for the initial implementation but placeholders or integration points should be considered.
Out of Scope (for now): Direct human feedback loops, Telegram integration, and long-term memory storage (beyond Notion persistence) will not be implemented in this phase. The focus is on the core autonomous research workflow and Notion logging.

Architecture
The system will be organized into distinct front-end and back-end components, with a modular design that reflects the eventual final architecture. The diagram below illustrates the major components and data flow (also image is included in arch.png)
mermaid

flowchart LR
    subgraph Frontend_UI
        UI[Web/JS Front-End\nQuery Input & Result Display]
    end
    subgraph Backend_Research_Server
        API[(Research API Endpoint)]
        Agent[Research Agent\nAsync Orchestrator]
        Search[Web Search Module]
        Scraper[Content Extraction Module]
        LLM[LLM Analysis Module]
        NotionDB[(Notion Database)]
    end
    User(("User")) --> UI
    UI -->|Submit query| API
    API -->|Enqueue task| Agent
    Agent -->|Search queries| Search
    Search -->|Top results| Agent
    Agent -->|Fetch pages| Scraper
    Scraper -->|Page text| Agent
    Agent -->|Ask & refine| LLM
    LLM -->|Insights & follow-ups| Agent
    Agent --> Agent
    Agent -->|Final report| NotionDB
    API -->|Return result or link| UI

    %% Future integrations (dashed)
    subgraph Future_Enhancements
        FB[Human Feedback Module]
        Telegram[Telegram Bot Interface]
        Memory[Long-Term Memory Store]
    end
    UI -.->|feedback| FB
    Telegram -.-> API
    Agent -.-> Memory

Component Breakdown:
User & Front-End (JS UI): A web-based interface where the user enters their research query (and optional parameters like depth/breadth). This could be a simple React/Next.js app or even a minimal HTML/JS page. It sends the query to the back-end and later displays the results (or a link to the Notion page). The front-end will remain responsive, as the heavy work is done asynchronously by the back-end.
Back-End API: A lightweight HTTP API (e.g. a Node/Express or FastAPI endpoint within the research server) that the front-end calls to initiate a research task. When a request comes in, the API enqueues or triggers an asynchronous research job in the Research Agent module. The API immediately responds to the front-end (so the UI isn’t blocked). The response could contain a task ID for the front-end to poll for completion or a confirmation that the task started. (In the initial implementation, we might simplify by having the API wait for completion and return the result directly, but the internal structure will allow easy switching to a queued async model.)
Research Agent (Async Orchestrator): This is the core engine that carries out the multi-step research process. It runs asynchronously (e.g. in a background worker thread or process) so as not to block the API server. The agent takes the user’s query and orchestrates the following workflow:
Query Generation: Use the LLM to refine the initial query or generate multiple related queries if a breadth parameter > 1 (for example, for broader coverage). If breadth >1, the agent will generate or use multiple search queries in parallel.
mcp.so
Web Search: For each query, call the Search module to retrieve top search results (e.g. top N URLs) relevant to the query.
Content Extraction: For each result URL, use the Scraper module to fetch the page content (HTML and/or text). This can be done via an external service like Firecrawl or a custom scraper. We will leverage Firecrawl (if available) for efficient web data extraction and parsing, using its API with the provided FIRECRAWL_KEY (or a self-hosted instance)
github.com
. If Firecrawl is not available, a fallback could be implemented using an HTTP library and basic HTML parsing.
LLM Analysis: Pass the extracted content (or summaries of it) to the LLM module. The LLM (Gemini or GPT) will analyze the information to extract key findings (“learnings”) and suggest new follow-up questions or directions
github.com
github.com
. The agent compiles these insights and new questions.
Iterative Loop: If a depth parameter > 0, the agent will iteratively continue the research using the new questions as queries for further rounds
github.com
github.com
. After each iteration, the depth counter is decremented. The loop continues until the specified depth is reached (no further follow-up) or no new relevant questions emerge. This iterative approach lets the agent refine its research direction over time
mcp.so
, mimicking an expert researcher diving deeper.
Result Synthesis: After completing all iterations, the agent uses the LLM to compile a comprehensive Markdown report of the findings
mcp.so
. This report will include an organized summary of insights gathered, answers to the original query, and references (links to source materials). The report format can be similar to the assistant’s answers here: paragraphs of findings with inline citations of sources.
Notion Logging: The final step of the agent is to save the report to the connected Notion database via the Notion API.
Notion Database: Acts as a persistence layer for completed research reports (analogous to how a SQL/Postgres DB was used in another implementation
mcp.so
). We will use the Notion SDK to create a new page in a designated Notion Database for each completed research task. The Notion database schema will not be altered in this implementation; instead, we ensure our data fits into its existing structure. For example, if an existing Notion database (from the Twitter VC Analyzer project) is repurposed for research reports, it likely has properties we can use:
Title property – will store the research topic or question.
Content or Notes property – to store the main findings or a summary. If no suitable text field exists, we may need to introduce a new “Report” rich-text property to hold the Markdown content (or as much of it as feasible).
References/Links property – if the current DB has a place for source URLs or attachments, we can use it to store key references. If not, references might simply remain embedded in the Markdown report text.
Status/Date properties – if present, can be updated (e.g., mark the report as completed, set a completion timestamp).
Note: We assume we have the Notion Database ID and integration token configured. If the existing database’s schema lacks any field we require (e.g. a large text field for the report), that may need to be added manually in Notion (we won’t modify the schema via code). In the PRD we flag that a “Report Content” field might be needed. The implementation will accommodate whatever fields are available by either using an existing multi-line text property or splitting content among existing fields (for example, “Summary” vs “Details”). This will be clearly documented so it can be adjusted on the Notion side.
External APIs & Services:
Search Module: This will likely call an external Search API. If using Firecrawl, it might provide a search endpoint; otherwise we can use an API like Bing Web Search or Google Custom Search (with appropriate API keys) to get result URLs and snippets. This module is abstracted so it can be replaced or tuned (for example, switching to a different search provider).
Content Scraper: As noted, Firecrawl is preferred for robust content scraping (including dynamic content if needed). The system will be designed to easily swap in another scraper or even a simple HTTP fetch if necessary.
LLM Module: Uses an LLM API. By default, we will integrate Gemini LLM (if available via GEMINI_API_KEY) for query generation and analysis
github.com
. If Gemini is not accessible, the code could fall back to OpenAI’s API (with an OPENAI_API_KEY) with a suitable model (e.g. GPT-4) – but this fallback is optional. The design allows plugging in different LLM backends via a unified interface (to accommodate future models or self-hosted ones).
Future Enhancement Hooks: While not implemented now, the architecture accounts for:
Human Feedback Module: In future, a human-in-the-loop interface could be added. For instance, after the agent produces an intermediate result or final report, a human could review and provide corrections or additional questions. The design will allow insertion of a feedback step (perhaps between iterations or before finalizing the report). For now, we might simply log a placeholder or allow the user to edit the Notion page manually as a form of feedback.
Telegram Bot Interface: A separate interface where users can submit queries and receive results via Telegram. The back-end API can be reused for this – we would just add a Telegram bot that forwards messages to the API and returns the Notion link or summary back to chat. Our current API design (stateless request/response with task IDs) will make this integration straightforward later.
Long-Term Memory Store: In future, we may integrate a database or vector store to accumulate knowledge from past research (to avoid repeating work and to let the agent recall previous findings). For now, the Notion database itself can serve as a rudimentary memory (as the agent could search it for related topics if implemented). We will not implement vector search or cross-session memory now, but the code will be written in a way that adding a memory lookup before web search (and updating memory after research) is possible without major changes. For example, we might structure the agent’s workflow so that there’s an abstract KnowledgeBase interface – currently backed by Notion (with simple search or none), which can later be backed by a more sophisticated store.
Implementation Plan
Below is a step-by-step plan for implementing the system on top of the existing mcptools codebase. Each step corresponds to concrete development tasks, including updating code and writing tests. We assume mcptools already contains some base structure (possibly similar to the open deep-research agent); we will extend it as needed:
Project Setup & Configuration:
Ensure the mcptools repository is set up locally and examine its structure. Identify where the main application logic resides (e.g., an entry point script or server setup). We will integrate our components into this existing structure.
Add any required configuration settings for API keys and IDs:
Notion API Token and Database ID (e.g., via environment variables NOTION_TOKEN and NOTION_DB_ID).
LLM API keys: GEMINI_API_KEY (and optionally OPENAI_API_KEY as fallback).
Firecrawl API Key: FIRECRAWL_KEY (and an optional base URL if using self-hosted).
If not already present, introduce a configuration module or use environment variables directly in code for these settings. Make sure to securely load these keys (e.g., using dotenv if Node, or similar for Python). No secrets are hard-coded.
Separate Front-End UI (JS) from Back-End Logic:
Create a distinct front-end component. If mcptools already includes a UI (or is only back-end), set up a new directory (e.g., webapp/ or frontend/) for the front-end code. This can be a simple static site served by the back-end or a separate development (e.g., a React app).
Implement a basic web page with:
An input form for the research query (and possibly numeric fields for Depth and Breadth parameters, with sensible defaults like depth=1, breadth=3).
A submit button that calls the back-end API (using fetch/AJAX). On submission, it should disable input and show a loading indicator.
An area to display results: initially this can just show a message like “Research in progress, please wait…” and then either display the final Markdown report or a link to the Notion page once ready.
If using a framework (React/Next.js), create a simple component for this form and results. If keeping it ultra-simple, an HTML + vanilla JS will do.
Do not embed the research logic in the front-end – the front-end only handles user interaction and displaying results, calling the back-end via HTTP.
Back-End API Endpoint:
In the back-end (within mcptools server code), add an API route (e.g., POST /research or similar) that the front-end will call to start a research task.
When this endpoint is hit with a JSON body containing the query (and params), it will invoke the Research Agent. Implementation detail:
If an async task queue or worker system is available (e.g., using Node’s worker threads, or a library like bull for job queues), enqueue the job and immediately return a task ID.
Otherwise, for initial simplicity, spawn a new thread/process or use an asynchronous call that performs the research without blocking the main event loop. For example, in Node we might use a child process running the agent logic, or simply fire off an async function (since our code will await at points of I/O, it might not block much).
If immediate response is needed, the API can choose to wait for the result (but this could risk timeout if research takes long). A compromise is to send periodic keep-alive pings or simply document that deep research may take a while.
Decide on the response format:
Option A: Return a task ID and have the front-end poll another endpoint (e.g., GET /research/{id}/status) to retrieve the result or status. Implement a simple in-memory storage or map in the server to store results by ID once done.
Option B: Perform the research synchronously (just for now) and return the result payload directly when done. (This is simpler to implement and test initially. Given our focus on testing actual external calls, a single end-to-end request might be acceptable if it’s within a couple of minutes; we need to be mindful of any request timeouts).
We lean towards Option A for a scalable approach. So implement: generate a unique task_id (could be a UUID or incremental), store a status object (with states like "pending", "completed", or "error"), then start the research agent in the background. Immediately respond with { task_id: ... }.
If Option A: also implement GET /research/{task_id}:
This returns the status and result if available. E.g., { status: "pending" } or { status: "completed", result: {...} }.
The result can include the final Markdown content or (to avoid huge payload) perhaps just a link or an identifier of the Notion page. We might include both a short summary and the Notion page URL for convenience.
Ensure proper error handling in the API: if a bad request comes (missing query) respond with 400; if something fails in the agent, catch it and mark status "error" with an error message.
Research Agent Logic Implementation:
Create a module (e.g., research_agent.js or agent.py depending on language) that encapsulates the deep research workflow. If mcptools already has similar logic, refactor it into this module so it can be called independently (and possibly concurrently).
The agent function should roughly do:
pseudo
Copy
Edit
function runDeepResearch(query, depth, breadth) -> ReportData:
    // initialize collections for overall learnings and references
    all_learnings = []
    references = []
    questions = [query]  // initial question list
    for d in range(depth+1):  // 0 to depth inclusive (depth=0 means one iteration)
        new_questions = []
        for each q in questions (up to breadth limit):
            results = performSearch(q)
            pageContents = fetchAndParse(results.topN URLs)
            // Analyze results with LLM:
            (learnings, followUps) = LLMAnalyze(q, results, pageContents)
            add learnings to all_learnings
            add any references (URLs) from results to references
            add followUps to new_questions
        // if more depth to go, prepare next iteration
        questions = (breadth limit) most relevant followUps from new_questions (LLM or simple filter)
    // After loop, synthesize final report
    reportMarkdown = LLMGenerateReport(query, all_learnings, references)
    return { reportMarkdown, references, query }
Search (performSearch): Implement using the Search module:
Possibly use an existing function or tool in mcptools if available. If not, create a new function to call an external API. For example, call Bing Web Search API (using an AZURE_API_KEY if available) or Google Custom Search (with an API key & CX). Another approach: if a SerpAPI key is available, use that to get Google results in JSON. The output should be a list of result items (URL, title, snippet).
If using Firecrawl’s API and it supports search, we could send the query to Firecrawl to get results directly (Firecrawl is primarily for scraping, but it might have some search capability via an index or it might rely on a separate tool).
For now, assume we have to handle search ourselves: integrate one reliable search API. (We will document which API and require its key if needed. If none is available, a last resort is using an unofficial HTML scrape of Google via Firecrawl or similar, but that’s brittle for testing.)
Respect rate limits of chosen API and maybe limit to top 5 results per query.
Content Extraction (fetchAndParse): Implement using Scraper module:
Use Firecrawl: They have an API endpoint where you provide a URL and it returns extracted text or structured content. Utilize FIRECRAWL_KEY. If Firecrawl requires running a local server, document steps to run it (the Docker in mcptools might already handle this).
Alternatively, implement a simple fetch using Node’s axios/got or Python requests and parse the HTML (perhaps using a library like Cheerio for Node or BeautifulSoup for Python) to get readable text. For initial implementation and testing, focusing on Firecrawl (which is tested and high-quality) is preferred.
This function should return either the full text or a trimmed summary of each page. We might limit how much text we feed to the LLM to keep within token limits (the LLM analysis prompt should not exceed model limits). Possibly, we only feed the snippet or first part of each page unless the LLM specifically needs more.
LLM Analysis (LLMAnalyze):
Construct a prompt for the LLM that includes the current research question, the search results (titles/snippets or extracted content), and asks for:
Key findings relevant to the question (learnings).
Any new questions or directions to explore (follow-up questions).
Use the Gemini API via GEMINI_API_KEY to get a completion. (If there is a specific endpoint and model name, use those as per Gemini’s documentation; the code from api_test_gemini_native.py can guide how to call Gemini’s API).
Parse the LLM’s response. We expect it to provide something like a list of bullet points of learnings and possibly questions. We can prompt it to format output in a machine-readable way (e.g., JSON with {"learnings": [...], "followUps": [...]}) to simplify parsing. If that’s not possible, we might parse bullet points heuristically.
Add the returned learnings to all_learnings. For references, the LLM might not give them explicitly; we should gather references directly from the search results (URLs we retrieved) and perhaps any specific sources mentioned in LLM’s text. We will maintain the references list from the URLs we actually fetched and possibly any additional ones the LLM cites.
Concurrent processing: To speed up, if breadth is more than 1 (meaning we handle multiple queries per depth level), we can run searches and fetches in parallel (e.g., using Promise.all in Node or asyncio.gather in Python). Also fetching multiple pages can be concurrent. Implement appropriate concurrency control to avoid overwhelming external APIs (maybe limit to 3-5 concurrent fetches).
Ensure each iteration’s operations (search -> fetch -> LLM) are robust: wrap calls in try/except or promise catch to handle failures. If one page fails to fetch, log it and continue with others.
Follow-up question selection: After getting followUps from LLM, we may get many questions. Decide on how to select for the next iteration:
If the breadth parameter is N, we can take the top N follow-up questions. If the LLM output is unranked, we might just take the first N or all if not too many. We assume the LLM outputs them in order of importance or we could ask it to prioritize.
Alternatively, feed the follow-ups back into a ranking step (optional, maybe skip for now).
Also, avoid repeating questions that were already asked in previous iterations (keep a set of asked queries and filter out duplicates).
Loop continues until depth runs out. The combination of breadth and depth defines how exhaustive the research is. For example, depth=1, breadth=3 means one round of up to 3 searches and done. Depth=2 means do initial round, then second round with follow-ups.
Generate Final Report (LLMGenerateReport):
Prepare a prompt for the LLM to produce a final report. Input to the prompt could include:
A summary of the user’s original query and the goal.
A compiled list of all key learnings gathered (this could be a long list).
The list of reference URLs and their titles (to encourage the LLM to cite them or at least be aware of sources).
Instructions to produce a markdown formatted report that is well-structured (with headings, bullet points, etc.), and to include references (maybe as a list at the end or inline citations).
Call the LLM API one more time with this prompt. Alternatively, we could attempt to have the agent itself compile the report from the data without another LLM call, but leveraging the LLM will likely produce a more coherent and nicely worded report.
Receive the markdown content from the LLM. Post-process if needed: e.g., ensure links are properly formatted. Possibly append the references list (if not already included by the LLM).
The output is our final reportMarkdown. Also package metadata like title = query, maybe a brief summary (first few lines) if needed for Notion.
Integrate with Notion Saving: Once the report is ready, the agent should call the Notion integration (next step) to create a page. This could be done here in the agent, or the agent could return the report data to the API and the API does the Notion saving. However, doing it inside the agent ensures it's part of the job transaction. We will likely have the agent itself perform the Notion API call (so that by the time the API or polling endpoint sees the task complete, the data is already in Notion).
Throughout the agent, use logging to track progress (useful for debugging long tasks). For example: “Started search round 1”, “Fetched 5 results for query X”, “LLM extracted 3 learnings”, etc. These logs could be also sent to the front-end if a real-time status update feature is wanted later (out of scope now, but good to have logging anyway).
Notion Integration Module:
Implement a module (e.g., notion_client.js) to handle creating and updating pages in Notion. Leverage the official Notion SDK for Node (@notionhq/client) or Python (notion-client).
Initialize a Notion client with the token from config.
Write a function saveResearchToNotion(report) that takes the final report data (including at least the title, the markdown text, and the list of references or source links) and performs the following:
Use the Notion create page API to insert a new page into the configured database (NOTION_DB_ID).
Map our data to the Notion database properties:
Set the Title property = research topic (the original query, or a cleaned-up version as title-case).
Set any Summary/Content property = either the full markdown (if the property type supports a lot of text) or a truncated summary. If the report is very large, Notion’s property text might hit limits (Notion rich text property supports up to 2000 characters per text object; we might split into multiple blocks if needed).
Alternatively, we can create the page with just title and maybe a short summary property, and then use the append block children API to add the full report as content blocks to the page. This would preserve formatting nicely (we’d have to parse our markdown into Notion blocks). For now, to keep things simpler, we could add one big code block or quote block containing the markdown text – but that’s not ideal for readability. Trade-off decision: We will first try to add the content in a semi-structured way:
For example, split the markdown by lines and create a series of Notion paragraph blocks, bold text for headings, etc. (Implement a basic markdown-to-Notion converter for headings, bullet points, and links).
If time is short, as a fallback simply attach the markdown as plain text in a Notion rich text property or in a Code block.
Add a property for references if the Notion DB has a field for it. This could be a multi-url property or just append URLs to the content. If no dedicated field, we can include a "References" section in the markdown itself (which the user can see on the page).
Set any other relevant metadata (e.g., a “Status” property to "Completed", and a “Date” property to now, if those exist).
Return the Notion page URL or ID. The Notion API returns the new page’s ID; we can construct a URL or query the title to get the URL (Notion URLs are of the form https://www.notion.so/<workspace>/<PageTitle>-<PageID>). The simplest way: if the user’s Notion workspace is known or if the API client provides a URL, use that.
Do not alter database schema in code: If we find that a property we expect (e.g., “Report Content”) is missing, we will document that it needs to be added in Notion. The code will attempt to use it and will log an error if Notion API complains about an unknown property. (This will signal that manual update is needed, which the user will handle as stated.)
Test the Notion function standalone (using a small dummy call) to verify credentials and that pages can be created as expected.
Integrate Notion Module with Research Agent:
After generating the final report, call saveResearchToNotion(report) from the agent. Handle exceptions (e.g., network issues or incorrect DB ID) by catching and marking the task as "error" if it fails. If successful, get the page URL.
Decide on what to return to the API layer or front-end:
Likely, the agent can return a structure like { success: true, notion_page_id: X, notion_url: Y } along with maybe the content. The API (if polling model) will store this as the task result.
If the API is synchronous (Option B earlier), then simply respond to the original request with the notion URL and maybe content snippet.
Finalize Front-End Display of Results:
Update the front-end logic to handle the response from the API:
If using task polling: after getting a task ID, start a timer to poll the status endpoint every few seconds. Once it indicates completion, retrieve the result (which might include the Notion URL and maybe the content).
Display to the user: possibly show a link: “Research complete. View full report on Notion” as a clickable link (using the notion_url). Also, if we have the content available, we can display the summary or first part directly.
For a slicker UI, we could render the markdown directly on the page so the user can see results immediately. This can be done by using a Markdown renderer library on the front-end to convert the text to HTML. However, given the report may be long and the Notion page is anyway saved, an initial implementation might just provide the link. We leave it to future improvement to embed the result in the UI nicely. (This also aligns with the idea that Notion is the primary viewing/editing interface for the report.)
Possibly also show a message like “The report has been saved to your Notion database.” to reinforce persistence.
If the front-end is separate (e.g., a React app), ensure CORS is handled on the back-end API or serve the front-end from the same origin.
Testing Plan:
We will create comprehensive tests to ensure each component works and that the integration of all parts produces the expected outcomes. Because our system interacts with live external services (Notion API, web search, etc.), the tests will use real endpoints (not mocks) as requested. This requires that test environment is configured with valid API keys and that calling these services is feasible during testing.
Unit Tests:
Test the Search module with a sample query. This will call the real search API (or Firecrawl) and we assert that we get a non-empty list of results with valid URLs. For example, search for “OpenAI ChatGPT” should return results including “openai.com”. We won’t check exact titles (which can change) but we can check that at least 1 result is returned and contains expected fields.
Test the Scraper module with a known URL. E.g., take a known simple webpage (perhaps a Wikipedia page or a static site) and fetch it. Verify that the returned content contains an expected phrase from that page. This tests that Firecrawl (or our fallback) is working and parsing text. (The test should be robust to minor content changes, maybe just check that some heading or the title is present in the text.)
Test the LLM module in isolation might be tricky as it depends on external LLM API. We could do a small sanity test if the API usage is not too costly: e.g., prompt the LLM with a very simple input (“Summarize: The sky is blue because...”) and assert the output contains the word “blue” or something. However, LLM output can vary. It might be sufficient to test that the call to the LLM API returns some response and does not error out given a valid prompt. We’ll also handle the case of missing API key (test that it raises a clear error).
Test the Notion integration on its own: using a test Notion database (could be the real one or a separate test DB). The test will call saveResearchToNotion with a dummy short report (e.g., title “Test Entry”, content “This is a test”). After running, use the Notion API (or the response from our function) to verify that a page was created:
We can query the Notion database for an entry with that title, or use the returned page ID to retrieve it.
Assert that the page’s Title property matches “Test Entry” and that the content or summary property contains “This is a test”.
Clean up: It’s good practice to delete the test page after verification, to not clutter the DB. The Notion API allows deleting (archiving) pages; we can do that in the test teardown.
Test Research Agent logic in a controlled way:
We might simulate a scenario by stubbing the external calls in a unit test (to isolate logic). For example, stub Search to return a fixed small set of results (pointing to a local file or a known text), stub Scraper to return predetermined content, and stub LLM to return a fixed analysis (we could even create a dummy LLM class that reads from a file of prepared responses).
However, since the requirement is to hit live endpoints, our integration tests will cover the full pipeline. Still, having a semi-unit test with stubs could be useful to test iterative logic (like that depth loop correctly stops and collects info). We will implement such tests but mark them as separate from the pure integration tests.
Integration Test (End-to-End):
We will create an end-to-end test that runs a full research cycle with a real external call, but for feasibility, we’ll use a small query and restrict depth/breadth to minimize time and external load. For example:
Query: “MCP research tool” with depth=0, breadth=1 (just one search).
The test calls the live API endpoint (spinning up the server in test mode).
It waits (polling if asynchronous) for the result.
Verifies that the response indicates success and contains a Notion page link or ID.
Then, uses Notion API to check that page’s content or at least that it exists. For example, confirm the title property is “MCP research tool” (or contains it).
Also check that the page has some content (not necessarily exact match, but not empty). We might check that at least one of the reference URLs we expect (like “mcp.so” or something related) appears in the stored text, to ensure references were included.
This end-to-end test will effectively exercise: search API returns something, LLM processes (Gemini might not return consistent output, but at least it should return some text), Notion saving works. We will log the output for manual inspection as well.
Because this test depends on external APIs and network, it could be flaky (for example, if the LLM API rate-limits or the search returns nothing). To mitigate, we choose a query likely to have results, and we set generous timeouts for the test. We also ensure that even if the content varies, our assertions are general (e.g., check that the Notion page contains at least 100 characters of text, etc., rather than specific phrases).
Performance: Though not a strict requirement in tests, we will observe the time taken for the end-to-end test. If a single iteration takes too long (say >30 seconds), consider adjusting parameters or making the test query simpler to keep it reasonably fast.
Additional Test Cases:
Error handling: simulate a scenario where the Notion integration fails (e.g., use an invalid Notion token in a test config) to ensure the system logs an error and the API returns a failure status gracefully. We expect the agent to catch exceptions and mark the task as error, and the API to relay that to the user (e.g., via the status endpoint or HTTP response). The test would assert that an appropriate error message or status is received, rather than a hang or crash.
Concurrent requests: if feasible, write a test that launches two research tasks in parallel (perhaps with very shallow depth to keep it quick) and ensure that both complete and are saved correctly, and that no data from one leaks into the other. This will test our task isolation and any concurrency controls.
All tests will be included in a /tests directory (or integrated in whatever testing framework mcptools uses, e.g., Jest for Node or PyTest for Python). We will provide documentation on how to run the tests, including the need to set environment variables for external service keys in the test environment.
Documentation and Final Touches:
Update the README or relevant documentation in mcptools to explain the new Deep Research feature. Include:
How to configure the Notion integration (what values to put for NOTION_TOKEN and NOTION_DB_ID, and note about ensuring the database has the needed fields).
How to run the research: e.g., via the web UI (URL or localhost port) or via a CLI if we provide one. Possibly provide an example cURL command for the /research API.
Describe the expected output (a Notion page link) and where to find the results.
Mention the future extension points (feedback, etc.) to inform other developers.
Ensure linting, formatting is done (especially if this is a JS/TS project, run Prettier or similar).
Do a final manual integration test: run the server, execute a query through the front-end, and verify the end-to-end flow one more time in a real scenario. Check the Notion page for formatting issues and adjust if needed (for example, if markdown didn’t render well, maybe tweak the conversion).
After everything is verified, commit the changes to the repository.
By following this plan, we will have a fully functional Deep Research tool integrated into mcptools that meets the current requirements and is tested against live services. The architecture is aligned with the final vision, making future enhancements (like human-in-the-loop revisions, Telegram bot access, and richer long-term memory) much easier to add when needed. Sources:
Deep Research MCP concept and features
mcp.so
mcp.so
mcp.so
, which guided our design for iterative LLM-driven research and persistent storage. (Our implementation uses Notion for persistence instead of SQL.)