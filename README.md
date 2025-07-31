# pyairtable-api-gateway

Simple API gateway for routing requests to PyAirtable microservices

## Overview

This is a lightweight API gateway that provides a single entry point for the PyAirTableMCP microservices ecosystem. It handles:
- Request routing to appropriate microservices
- Health check aggregation
- Basic authentication and CORS
- Load balancing (future)

## Services Routing

- `/api/chat` → `llm-orchestrator-py:8003`
- `/api/airtable/*` → `airtable-gateway-py:8002`
- `/api/tools/*` → `mcp-server-py:8001`
- `/api/health` → Health check aggregation

## Quick Start

```bash
# Clone the repository
git clone https://github.com/Reg-Kris/pyairtable-api-gateway.git
cd pyairtable-api-gateway

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with service URLs

# Run the gateway
uvicorn src.main:app --reload --port 8000
```

## Environment Variables

```
# Service URLs
AIRTABLE_GATEWAY_URL=http://localhost:8002
MCP_SERVER_URL=http://localhost:8001
LLM_ORCHESTRATOR_URL=http://localhost:8003

# Gateway Configuration
API_KEY=simple-api-key
PORT=8000
LOG_LEVEL=INFO
```

## Usage

```bash
# Chat with LLM
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "List all tables in my base",
    "session_id": "user123",
    "base_id": "appXXXXXXXXXXXXXX"
  }'

# Check system health
curl http://localhost:8000/api/health

# List available tools
curl http://localhost:8000/api/tools
```

## Docker

```bash
# Build image
docker build -t pyairtable-api-gateway .

# Run container
docker run -p 8000:8000 --env-file .env pyairtable-api-gateway
```