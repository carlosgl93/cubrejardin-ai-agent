# CubreJardin Bot - Testing Guide

This document provides comprehensive instructions for testing the CubreJardin Bot application.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Backend Testing](#backend-testing)
4. [Frontend Testing](#frontend-testing)
5. [Integration Testing](#integration-testing)
6. [Manual Testing](#manual-testing)
7. [CI/CD Testing](#cicd-testing)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 15+ (with pgvector extension)
- Redis 7+
- Docker (optional, for containerized testing)

---

## Environment Setup

### 1. Backend Environment

```bash
cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Required Environment Variables

Create a `.env.test` file in the project root:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/cubrejardin_test
REDIS_URL=redis://localhost:6379/0

# Supabase
SUPABASE_URL=https://test.supabase.co
SUPABASE_ANON_KEY=test-key
SUPABASE_SERVICE_KEY=test-service-key

# WhatsApp (use test credentials)
WHATSAPP_PHONE_NUMBER_ID=1234567890
WHATSAPP_WEBHOOK_VERIFY_TOKEN=test-verify-token
WHATSAPP_ACCESS_TOKEN=test-access-token

# Telegram (for testing)
TELEGRAM_BOT_TOKEN=test-telegram-token

# MercadoFiel (for testing)
MERCADO_FIEL_API_KEY=test-api-key

# OpenAI (required for some tests)
OPENAI_API_KEY=sk-test-key
```

### 3. Database Setup

```bash
# Start PostgreSQL (Docker)
docker run -d \
  --name cubrejardin-test-db \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=cubrejardin_test \
  -p 5433:5432 \
  -v pgdata_test:/var/lib/postgresql/data \
  postgres:15-alpine

# Enable pgvector
docker exec -it cubrejardin-test-db psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Start Redis
docker run -d --name Redis \
  -p 6380:6379 \
  redis:7-alpine
```

---

## Backend Testing

### Running All Tests

```bash
cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
source venv/bin/activate

# Run all unit tests (recommended)
pytest --ignore=tests/test_integration.py -v

# Run specific test file
pytest tests/test_learning_service.py -v

# Run with coverage
pytest --cov=services --cov=agents --cov=api -v
```

### Test Categories

#### 1. Service Tests
```bash
# Test message queue service
pytest tests/test_message_queue.py -v

# Test learning service
pytest tests/test_learning_service.py -v

# Test interactive service
pytest tests/test_interactive_service.py -v
```

#### 2. Agent Tests
```bash
# Test FAQ agent
pytest tests/test_faq_agent.py -v

# Test guardian
pytest tests/test_guardian.py -v

# Test RAG agent
pytest tests/test_rag_agent.py -v
```

#### 3. Adapter Tests
```bash
# Test WhatsApp adapter
pytest tests/test_whatsapp_adapter.py -v

# Test Instagram adapter
pytest tests/test_instagram_adapter.py -v
```

#### 4. API Tests
```bash
# Test webhook validation
pytest tests/test_webhook.py -v

# Test Instagram webhook
pytest tests/test_webhook_ig.py -v

# Test conversations
pytest tests/test_conversations_filter.py -v
```

### Running Tests with Specific Markers

```bash
# Run only async tests
pytest -m asyncio -v

# Run integration tests (requires full setup)
pytest tests/test_integration.py -v

# Skip slow tests
pytest -m "not slow" -v
```

---

## Frontend Testing

### 1. TypeScript Type Checking

```bash
cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud

# Check TypeScript types
npm run astro:check

# Or using astro directly
npx astro check --no-watch
```

### 2. Build Testing

```bash
cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud

# Build the frontend
npm run build

# Preview the build
npm run preview
```

### 3. Component Testing

The frontend uses Preact. Test components by:

1. **Visual Testing**: Run the dev server and check components
```bash
cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud
npm run dev
```

2. **Widget Testing**: The new QueueMetrics and TelemetryDashboard widgets:
   - Navigate to Dashboard
   - Scroll to "Métricas del Sistema" section
   - Verify both widgets render
   - Check API endpoint returns data

---

## Integration Testing

### Full Stack Integration

1. **Start the backend**:
```bash
cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
source venv/bin/activate

# Start the API server
uvicorn main:app --reload --port 8000
```

2. **Start the frontend**:
```bash
cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud
npm run dev
```

3. **Run integration tests**:
```bash
cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
source venv/bin/activate

# The integration test requires a real database
pytest tests/test_integration.py -v -s
```

### Manual Integration Tests

#### Test 1: WhatsApp Webhook
```bash
# Simulate incoming WhatsApp message
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "+1234567890",
            "id": "test-id",
            "text": {"body": "Hola, necesito ayuda"},
            "timestamp": "1234567890",
            "type": "text"
          }]
        }
      }]
    }]
  }'
```

#### Test 2: Message Queue Metrics
```bash
# Get queue metrics
curl http://localhost:8000/admin/queue/metrics

# Response should include:
# {
#   "messages_sent": 0,
#   "messages_failed": 0,
#   "queue_high": 0,
#   "queue_normal": 0,
#   "queue_low": 0,
#   "dead_letter_count": 0
# }
```

#### Test 3: Learning Queue
```bash
# List learning queue entries
curl http://localhost:8000/admin/learning-queue

# Validate a learning entry
curl -X POST http://localhost:8000/admin/learning/1/validate
```

#### Test 4: Interactive Buttons (WhatsApp)
```bash
# Test button callback handling
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "+1234567890",
            "id": "test-btn-callback",
            "text": {"body": "FAQ"},
            "timestamp": "1234567890",
            "type": "text"
          }]
        }
      }]
    }]
  }'
```

---

## Manual Testing

### 1. Dashboard Widgets Testing

#### QueueMetrics Widget
1. Open the frontend dashboard
2. Scroll to "Métricas del Sistema" section
3. Verify QueueMetrics widget displays:
   - Title: "Cola de Mensajes"
   - Priority queue counts (high/normal/low)
   - Dead letter count
   - Messages sent/failed
4. Click refresh button - counts should update
5. Check that progress bar shows queue distribution

#### TelemetryDashboard Widget
1. Verify TelemetryDashboard widget displays:
   - Title: "Métricas de Telemetry"
   - Messages received/sent
   - Average latency
   - Confidence gauge
   - Error rate
2. Check auto-refresh (updates every 60 seconds)

### 2. WhatsApp Interactive Buttons Testing

1. **Test FAQ Category Buttons**:
   - Send "ayuda" or "menú" via WhatsApp
   - Should receive buttons with FAQ categories
   - Click a button to get category-specific suggestions

2. **Test RAG Suggestion Buttons**:
   - After asking a question, receive suggestion buttons
   - Click "Ver más" to get related documents
   - Click "Preguntar otra cosa" to reset conversation

### 3. Stock Management Testing

```bash
# Test natural language stock parsing
curl -X POST http://localhost:8000/api/stock/parse \
  -H "Content-Type: application/json" \
  -d '{"query": "agregar 5 unidades al producto X"}'
```

### 4. Learning Flow Testing

1. User sends message → Bot doesn't know answer → Handoff to human
2. Human provides answer via Telegram
3. Answer saved to learning queue
4. Admin validates entry at `/admin/learning-queue`
5. Entry ingested into vector database

---

## CI/CD Testing

### GitHub Actions (if configured)

The repository should have a workflow file at `.github/workflows/test.yml`:

```yaml
name: Test

on: [push, pull_request]

jobs:
  backend-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pytest --ignore=tests/test_integration.py -v

  frontend-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      - run: npm ci
      - run: npm run astro:check
```

### Local CI Simulation

```bash
# Run full CI pipeline locally
#!/bin/bash
set -e

echo "=== Running Backend Tests ==="
cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
source venv/bin/activate
pytest --ignore=tests/test_integration.py -v

echo "=== Running Frontend Check ==="
cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud
npm run astro:check

echo "=== Building Frontend ==="
npm run build

echo "=== All Tests Passed ==="
```

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Error
```
Error: could not connect to database
```
**Solution**: Ensure PostgreSQL is running and DATABASE_URL is correct.

#### 2. Redis Connection Error
```
Error: Connection refused to Redis
```
**Solution**: Start Redis or check REDIS_URL environment variable.

#### 3. Import Errors
```
ModuleNotFoundError: No module named 'services'
```
**Solution**: Run from project root directory.

#### 4. Test Timeout
```
pytest: timeout exceeded
```
**Solution**: Increase timeout in pytest.ini or skip slow tests.

#### 5. Frontend Build Error
```
Cannot find module './widgets/QueueMetrics'
```
**Solution**: Verify the component file exists at the correct path.

### Debug Mode

```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG

# Run single test with full output
pytest tests/test_learning_service.py -v -s

# Run with profiling
pytest --profile -v
```

---

## Test Coverage

### Current Coverage Summary

| Component | Files | Coverage |
|-----------|-------|----------|
| Services | message_queue, learning, interactive | 85%+ |
| Agents | handoff, faq, rag, guardian | 80%+ |
| Adapters | whatsapp, instagram | 90%+ |
| API | admin, webhooks, templates | 75%+ |

### Generate Coverage Report

```bash
cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
source venv/bin/activate

# Generate HTML coverage report
pytest --cov=services --cov=agents --cov=api --cov-report=html

# View report
open htmlcov/index.html
```

---

## Performance Testing

### Load Testing with Locust

```python
# tests/load_test.py
from locust import HttpUser, task, between

class WhatsAppBotUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def send_message(self):
        self.client.post("/webhook/whatsapp", json={
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "+1234567890",
                            "id": "test",
                            "text": {"body": "Hola"},
                            "timestamp": "1234567890",
                            "type": "text"
                        }]
                    }
                }]
            }]
        })

    @task(1)
    def check_metrics(self):
        self.client.get("/admin/queue/metrics")
```

Run with:
```bash
locust -f tests/load_test.py --host=http://localhost:8000
```

---

## Additional Resources

- [pytest Documentation](https://docs.pystasy.pytest.org/)
- [Preact Testing](https://preactjs.com/guide/v10/testing)
- [Astro Testing](https://docs.astro.build/en/guides/testing/)


---

## E2E Testing

The project includes End-to-End (E2E) tests for both backend API and frontend UI.

### E2E Test Structure

```
cubrejardin-bot/
├── tests/
│   └── e2e/
│       ├── conftest.py         # Pytest fixtures
│       ├── test_api.py         # Backend API E2E tests
│       └── test_whatsapp.py    # WhatsApp flow E2E tests
└── run-e2e.sh                  # E2E test runner script

astro-sg-cloud/
├── tests/
│   └── e2e/
│       ├── dashboard.spec.ts   # Dashboard E2E tests
│       └── auth.spec.ts        # Auth E2E tests
├── playwright.config.ts        # Playwright configuration
└── package.json               # npm scripts for E2E
```

### Prerequisites for E2E Testing

1. **Services must be running:**
   ```bash
   # Terminal 1: Start backend
   cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
   source venv/bin/activate
   uvicorn main:app --reload --port 8000

   # Terminal 2: Start frontend
   cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud
   npm run dev
   ```

2. **Install Playwright browsers:**
   ```bash
   cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud
   npx playwright install --with-deps chromium
   ```

### Running E2E Tests

#### Using the E2E Runner Script

```bash
# Check if services are running
./run-e2e.sh check

# Install Playwright browsers
./run-e2e.sh install

# Run backend E2E tests only
./run-e2e.sh backend

# Run frontend E2E tests only
./run-e2e.sh frontend

# Run all E2E tests
./run-e2e.sh all
```

#### Using npm scripts (Frontend)

```bash
cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud

# Run E2E tests
npm run test:e2e

# Run E2E tests with UI
npm run test:e2e:ui

# Run E2E tests in headed mode (see browser)
npm run test:e2e:headed

# Debug E2E tests
npm run test:e2e:debug

# View test report
npm run test:e2e:report
```

#### Using pytest (Backend)

```bash
cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
source venv/bin/activate

# Run all backend E2E tests
pytest tests/e2e/ -v

# Run specific E2E test file
pytest tests/e2e/test_api.py -v
pytest tests/e2e/test_whatsapp.py -v

# Run with verbose output
pytest tests/e2e/ -v -s
```

### Backend E2E Tests

#### API Endpoint Tests (`tests/e2e/test_api.py`)

| Test | Description |
|------|-------------|
| `test_health_check` | Verify `/admin/health` returns OK |
| `test_queue_metrics_endpoint` | Verify `/admin/queue/metrics` returns valid data |
| `test_list_learning_queue` | Verify `/admin/learning-queue` returns list |
| `test_whatsapp_webhook_verify` | Verify webhook verification works |
| `test_whatsapp_webhook_message` | Verify webhook accepts messages |
| `test_list_templates` | Verify `/api/templates` returns list |
| `test_list_conversations` | Verify `/api/conversations` returns list |

#### WhatsApp Flow Tests (`tests/e2e/test_whatsapp.py`)

| Test | Description |
|------|-------------|
| `test_user_greeting_flow` | User sends "Hola", bot responds |
| `test_user_asks_question` | User asks question, bot routes to RAG |
| `test_user_requests_human` | User requests human, triggers handoff |
| `test_faq_button_callback` | FAQ button click triggers suggestions |
| `test_voice_message` | Voice message handling |

### Frontend E2E Tests

#### Dashboard Tests (`tests/e2e/dashboard.spec.ts`)

| Test | Description |
|------|-------------|
| `should load dashboard page` | Dashboard loads with title |
| `should display metrics section` | "Métricas del Sistema" section visible |
| `should display QueueMetrics widget` | QueueMetrics widget renders |
| `should display TelemetryDashboard widget` | TelemetryDashboard renders |
| `should have refresh button on metrics widgets` | Refresh buttons work |
| `should load queue metrics from API` | Metrics fetched from API |
| `should show progress bar when queue has messages` | Progress bar renders |

#### Auth Tests (`tests/e2e/auth.spec.ts`)

| Test | Description |
|------|-------------|
| `should redirect to login when not authenticated` | Auth guard works |
| `should show login page` | Login page renders |
| `should require admin privileges` | Admin access control |

#### Navigation Tests

| Test | Description |
|------|-------------|
| `should navigate to WhatsApp Templates` | Templates link works |
| `should navigate to Documents` | Documents link works |
| `should navigate to Conversations` | Conversations link works |

### Environment Variables for E2E

```bash
# Backend API URL
export API_BASE_URL=http://localhost:8000

# Frontend URL
export FRONTEND_URL=http://localhost:4321

# Test tenant ID
export TEST_TENANT_ID=e2e-test-tenant

# Test phone number
export TEST_USER_PHONE=+1234567890
```

### Troubleshooting E2E Tests

#### Services Not Running
```
Error: Connection refused
```
**Solution**: Start services with `./run-e2e.sh start` or manually start backend and frontend.

#### Playwright Browser Not Installed
```
Error: Executable doesn't exist
```
**Solution**: Run `./run-e2e.sh install` or `npx playwright install`.

#### Tests Timing Out
```
Error: Timeout exceeded
```
**Solution**: Increase timeout in `playwright.config.ts` or `conftest.py`.

#### Auth Tests Failing
```
Error: Authentication required
```
**Solution**: E2E tests may need valid Supabase credentials. Check environment variables.

### CI/CD E2E Testing

Add to your CI workflow:

```yaml
e2e-test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    # Start services
    - name: Start services
      run: |
        docker-compose up -d db redis
        sleep 5

    # Start backend
    - name: Start backend
      run: |
        cd backend && pip install -r requirements.txt
        uvicorn main:app --port 8000 &

    # Start frontend  
    - name: Start frontend
      run: |
        cd frontend && npm install && npm run dev &

    # Run E2E tests
    - name: Run Backend E2E
      run: pytest tests/e2e/ -v

    - name: Run Frontend E2E
      run: |
        cd frontend
        npx playwright install --with-deps
        npm run test:e2e
```

