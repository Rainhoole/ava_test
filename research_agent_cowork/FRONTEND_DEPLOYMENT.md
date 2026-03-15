# Frontend Deployment Guide

This guide documents the deployment of the Research Agent frontend (Next.js) to Vercel, including configuration for connecting to the backend API.

## Overview

The frontend is a Next.js 14 application that communicates with the FastAPI backend via REST API and Server-Sent Events (SSE) for real-time log streaming.

## Prerequisites

- Node.js 18+
- Vercel account (free tier works)
- Backend API deployed and accessible (see [../DEPLOYMENT.md](../DEPLOYMENT.md))

## Deployment Options

### Option 1: Vercel (Recommended)

#### One-Click Deploy

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/your-repo/research-frontend)

#### Manual Deploy via CLI

1. Install Vercel CLI:
   ```bash
   npm i -g vercel
   ```

2. Navigate to frontend directory:
   ```bash
   cd research-frontend
   ```

3. Deploy:
   ```bash
   vercel
   ```

4. Set environment variables in Vercel dashboard:
   - `NEXT_PUBLIC_API_URL`: Your backend API URL (e.g., `https://api.example.com`)

#### Deploy via Vercel Dashboard

1. Go to [vercel.com](https://vercel.com) and sign in
2. Click "Add New" → "Project"
3. Import your Git repository
4. Set root directory to `research_agent_cowork/research-frontend`
5. Configure environment variables:
   - `NEXT_PUBLIC_API_URL`: Your backend API URL
6. Click "Deploy"

### Option 2: Self-Hosted (Node.js)

1. Build the application:
   ```bash
   cd research-frontend
   npm install
   npm run build
   ```

2. Start production server:
   ```bash
   npm start
   ```

3. Use PM2 for process management:
   ```bash
   npm i -g pm2
   pm2 start npm --name "research-frontend" -- start
   pm2 save
   ```

### Option 3: Docker

Create a `Dockerfile` in the frontend directory:

```dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:18-alpine AS runner
WORKDIR /app
ENV NODE_ENV production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
```

Build and run:
```bash
docker build -t research-frontend .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=https://api.example.com research-frontend
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `https://api.example.com` |

**Note**: Variables prefixed with `NEXT_PUBLIC_` are exposed to the browser.

## Backend CORS Configuration

The backend must allow CORS requests from your frontend domain. Update `web_server.py` if needed:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-app.vercel.app",
        "https://your-custom-domain.com",
        "http://localhost:3000",  # For local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Nginx Configuration (Self-Hosted)

If self-hosting behind nginx:

```nginx
server {
    server_name app.example.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # SSL configuration (use certbot)
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;
}

server {
    if ($host = app.example.com) {
        return 301 https://$host$request_uri;
    }
    listen 80;
    server_name app.example.com;
    return 404;
}
```

## Vercel Configuration

The `vercel.json` file configures rewrites for API proxying (optional):

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://api.example.com/:path*"
    }
  ]
}
```

## Testing the Deployment

### 1. Verify Frontend Loads

```bash
curl -I https://your-app.vercel.app
```

Expected: `HTTP/2 200`

### 2. Verify API Connection

Open browser console and check for CORS errors. If you see CORS errors:
1. Verify backend CORS configuration includes your frontend domain
2. Check that `NEXT_PUBLIC_API_URL` is correctly set

### 3. Test SSE Streaming

1. Create a new research task
2. Verify real-time logs appear in the LogViewer component
3. Check browser Network tab for EventStream connections

## Troubleshooting

### "CORS error" in browser console

1. Verify backend allows your frontend origin in CORS settings
2. Check that the API URL doesn't have a trailing slash
3. Ensure `allow_credentials=True` in backend CORS config

### SSE streaming not working

1. Check that backend SSE endpoints are accessible
2. Verify no proxy is buffering SSE responses
3. Test SSE endpoint directly:
   ```bash
   curl https://api.example.com/tasks/{id}/stream -H "Accept: text/event-stream"
   ```

### Environment variable not working

1. Variables must be prefixed with `NEXT_PUBLIC_` to be available in browser
2. Rebuild the app after changing environment variables
3. In Vercel, redeploy after changing environment variables

### Build errors

```bash
# Clear cache and rebuild
rm -rf .next node_modules
npm install
npm run build
```

## Production Checklist

- [ ] Backend API deployed and accessible
- [ ] CORS configured to allow frontend domain
- [ ] `NEXT_PUBLIC_API_URL` environment variable set
- [ ] SSL/HTTPS enabled for both frontend and backend
- [ ] SSE streaming tested and working
- [ ] Error monitoring set up (optional: Sentry, LogRocket)

## Architecture Overview

```
┌─────────────────┐     HTTPS      ┌─────────────────┐
│                 │ ◄────────────► │                 │
│  Vercel/Nginx   │                │  Backend API    │
│  (Frontend)     │                │  (FastAPI)      │
│                 │     SSE        │                 │
│  Next.js App    │ ◄──────────── │  web_server.py  │
│                 │                │                 │
└─────────────────┘                └─────────────────┘
     Port 443                           Port 8000
```

## Updating the Deployment

### Vercel (Automatic)

Push to the connected Git branch - Vercel will automatically rebuild and deploy.

### Self-Hosted

```bash
cd research-frontend
git pull
npm install
npm run build
pm2 restart research-frontend
```
