# MCP Server Production Setup Guide

This guide provides step-by-step instructions to set up the MCP server as a production system service with proper logging, monitoring, and auto-restart capabilities.

## Prerequisites

- Server is already running manually
- All dependencies are installed
- nginx is configured (see DEPLOYMENT.md)

## Step-by-Step Setup

### Step 1: Stop the Current Manual Process

First, stop the currently running server:

```bash
# Find the process
ps aux | grep "python main.py" | grep -v grep

# Kill the process (replace PID with actual process ID)
kill <PID>
```

### Step 2: Install the Systemd Service

```bash
# Copy the service file to systemd directory
sudo cp /tmp/mcp-server.service /etc/systemd/system/

# Reload systemd to recognize the new service
sudo systemctl daemon-reload
```

### Step 3: Set Up Log Rotation

```bash
# Install logrotate configuration
sudo cp /tmp/mcp-server-logrotate /etc/logrotate.d/mcp-server

# Test logrotate configuration
sudo logrotate -d /etc/logrotate.d/mcp-server
```

### Step 4: Start and Enable the Service

```bash
# Start the service
sudo systemctl start mcp-server

# Enable it to start on boot
sudo systemctl enable mcp-server

# Check status
sudo systemctl status mcp-server
```

### Step 5: Verify the Service is Running

```bash
# Check service status
sudo systemctl status mcp-server

# Check if it's listening on port 8000
sudo netstat -tlnp | grep 8000

# Test the health check
/home/ubuntu/mcp_server/openai_mcp/mcp_server/health_check.sh

# Test via curl
curl -i https://ava.reforge.vc/sse/ -H "Accept: text/event-stream" --max-time 2
```

### Step 6: Monitor Logs

```bash
# View systemd logs
sudo journalctl -u mcp-server -f

# View application logs
tail -f /home/ubuntu/mcp_server/openai_mcp/mcp_server/logs/mcp_server.log

# View stdout/stderr logs
tail -f /var/log/mcp-server/stdout.log
tail -f /var/log/mcp-server/stderr.log
```

## Service Management Commands

### Start/Stop/Restart
```bash
sudo systemctl start mcp-server
sudo systemctl stop mcp-server
sudo systemctl restart mcp-server
```

### Check Status
```bash
sudo systemctl status mcp-server
```

### View Logs
```bash
# Last 100 lines
sudo journalctl -u mcp-server -n 100

# Follow logs
sudo journalctl -u mcp-server -f

# Logs from today
sudo journalctl -u mcp-server --since today
```

### Disable/Enable Auto-start
```bash
# Disable auto-start on boot
sudo systemctl disable mcp-server

# Re-enable auto-start
sudo systemctl enable mcp-server
```

## Monitoring and Health Checks

### Manual Health Check
```bash
/home/ubuntu/mcp_server/openai_mcp/mcp_server/health_check.sh
```

### Set Up Automated Monitoring (Optional)
Add to crontab for regular health checks:

```bash
# Edit crontab
crontab -e

# Add this line to check every 5 minutes
*/5 * * * * /home/ubuntu/mcp_server/openai_mcp/mcp_server/health_check.sh || systemctl restart mcp-server
```

## Troubleshooting

### Service Won't Start
1. Check logs: `sudo journalctl -u mcp-server -n 50`
2. Verify permissions: `ls -la /home/ubuntu/mcp_server/openai_mcp/mcp_server/`
3. Check if port 8000 is in use: `sudo lsof -i :8000`

### Environment Variables Not Loading
1. Check .env file exists: `ls -la /home/ubuntu/mcp_server/openai_mcp/.env`
2. Verify startup script: `cat /home/ubuntu/mcp_server/openai_mcp/mcp_server/start_production.sh`

### Service Exit Code 203/EXEC
This usually means the script cannot be executed. Common causes:
1. **Windows line endings (CRLF)** - Most common when files are created on Windows
   ```bash
   # Check file format
   file /home/ubuntu/mcp_server/openai_mcp/mcp_server/start_production.sh
   
   # If it shows "CRLF line terminators", fix with:
   sed -i 's/\r$//' /home/ubuntu/mcp_server/openai_mcp/mcp_server/start_production.sh
   sed -i 's/\r$//' /home/ubuntu/mcp_server/openai_mcp/mcp_server/health_check.sh
   ```
2. Missing execute permissions: `chmod +x /home/ubuntu/mcp_server/openai_mcp/mcp_server/start_production.sh`

### High Memory/CPU Usage
1. Check process: `htop` or `ps aux | grep mcp-server`
2. Review logs for errors causing loops
3. Restart service: `sudo systemctl restart mcp-server`

## Log Files

- **Application logs**: `/home/ubuntu/mcp_server/openai_mcp/mcp_server/logs/mcp_server.log`
- **Systemd stdout**: `/var/log/mcp-server/stdout.log`
- **Systemd stderr**: `/var/log/mcp-server/stderr.log`
- **Systemd journal**: `sudo journalctl -u mcp-server`

## Security Considerations

The service runs with:
- User: `ubuntu` (non-root)
- Private tmp directory
- No new privileges
- Resource limits applied
- Automatic restart on failure

## Backup and Recovery

### Backup Configuration
```bash
# Backup service files
sudo cp /etc/systemd/system/mcp-server.service ~/backup/
cp /home/ubuntu/mcp_server/openai_mcp/.env ~/backup/
```

### Recovery
```bash
# Restore from backup
sudo cp ~/backup/mcp-server.service /etc/systemd/system/
cp ~/backup/.env /home/ubuntu/mcp_server/openai_mcp/
sudo systemctl daemon-reload
sudo systemctl restart mcp-server
```

## Performance Tuning

The service is configured with:
- File descriptor limit: 65536
- Process limit: 4096
- Automatic restart with 10-second delay
- Log rotation to prevent disk fill

## Integration with Claude Desktop

After setting up the service, Claude Desktop should continue to work with:
```json
{
  "mcpServers": {
    "openai-mcp": {
      "transport": "sse",
      "url": "https://ava.reforge.vc/sse/"
    }
  }
}
```

The systemd service ensures the MCP server is always available for Claude Desktop connections.