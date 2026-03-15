# Research Agent Frontend

A modern Next.js frontend for the Research Agent API, featuring a ChatGPT-like interface.

## Features

- **ChatGPT-style layout** with sidebar task list and main panel
- **Real-time log streaming** via Server-Sent Events
- **Report viewing** with markdown rendering
- **Task management** - create, view, and cancel research tasks
- **Responsive design** with Tailwind CSS

## Getting Started

### Prerequisites

- Node.js 18+
- Research Agent backend running (default: `http://localhost:8000`)

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the app.

### Environment Variables

Create a `.env.local` file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For production, set `NEXT_PUBLIC_API_URL` to your backend API URL.

## Deployment on Vercel

### Option 1: One-Click Deploy

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/your-repo/research-frontend)

### Option 2: Manual Deploy

1. Install Vercel CLI:
   ```bash
   npm i -g vercel
   ```

2. Deploy:
   ```bash
   vercel
   ```

3. Set environment variables in Vercel dashboard:
   - `NEXT_PUBLIC_API_URL`: Your backend API URL

### Backend Configuration

The backend needs to allow CORS from your Vercel domain. Update `web_server.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-app.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Project Structure

```
src/
├── app/
│   ├── globals.css      # Global styles & Tailwind
│   ├── layout.tsx       # Root layout
│   └── page.tsx         # Main page component
├── components/
│   ├── Sidebar.tsx      # Task list sidebar
│   ├── MainPanel.tsx    # Main content panel
│   ├── LogViewer.tsx    # Real-time log streaming
│   ├── ReportViewer.tsx # Markdown report display
│   ├── ResearchInput.tsx# Research submission input
│   └── TaskActions.tsx  # Task action buttons
├── lib/
│   ├── api.ts           # API client functions
│   └── utils.ts         # Utility functions
└── types/
    └── index.ts         # TypeScript types
```

## API Endpoints Used

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/research` | POST | Submit new research |
| `/research/{id}` | GET | Get task status |
| `/research/{id}` | DELETE | Cancel task |
| `/research/{id}/replay` | GET (SSE) | Stream task logs |
| `/research/{id}/report` | GET | Get/download report |
| `/research_lists_magic` | GET | List all tasks |
| `/config` | GET | Get server config |

## Tech Stack

- **Next.js 14** - React framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **Lucide React** - Icons
- **Server-Sent Events** - Real-time log streaming
