#!/bin/bash
# CubreJardin Bot - Quick Test Commands
# Usage: source this file or run ./test-quick.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

echo_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Setup
setup() {
    echo_info "Setting up test environment..."

    # Backend
    cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
    source venv/bin/activate

    # Frontend
    cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud

    echo_success "Setup complete!"
}

# Run all backend tests
test-backend() {
    echo_info "Running backend tests..."
    cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
    source venv/bin/activate
    pytest --ignore=tests/test_integration.py -v
    echo_success "Backend tests passed!"
}

# Run specific test file
test-file() {
    local file=$1
    if [ -z "$file" ]; then
        echo_error "Usage: test-file <test_file.py>"
        return 1
    fi
    echo_info "Running $file..."
    cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
    source venv/bin/activate
    pytest "tests/$file" -v
    echo_success "$file tests passed!"
}

# Run frontend type check
test-frontend-types() {
    echo_info "Running frontend type check..."
    cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud
    npm run astro:check
    echo_success "Frontend type check passed!"
}

# Build frontend
build-frontend() {
    echo_info "Building frontend..."
    cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud
    npm run build
    echo_success "Frontend build passed!"
}

# Full test suite
test-all() {
    echo_info "Running full test suite..."

    echo_info "Step 1: Backend tests"
    test-backend

    echo_info "Step 2: Frontend type check"
    test-frontend-types

    echo_info "Step 3: Frontend build"
    build-frontend

    echo_success "All tests passed!"
}

# Start development servers
dev-start() {
    echo_info "Starting development servers..."

    # Start backend
    cd /Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot
    source venv/bin/activate
    uvicorn main:app --reload --port 8000 &
    BACKEND_PID=$!

    # Start frontend
    cd /Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud
    npm run dev &
    FRONTEND_PID=$!

    echo_success "Servers started!"
    echo "Backend: http://localhost:8000"
    echo "Frontend: http://localhost:4321"
    echo ""
    echo "Press Ctrl+C to stop"

    # Wait for user interrupt
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
    wait
}

# Test API endpoints
test-api() {
    echo_info "Testing API endpoints..."

    local base_url="http://localhost:8000"

    echo_info "Testing /admin/queue/metrics..."
    curl -s "$base_url/admin/queue/metrics" | head -c 200
    echo ""

    echo_info "Testing /admin/learning-queue..."
    curl -s "$base_url/admin/learning-queue" | head -c 200
    echo ""

    echo_success "API tests complete!"
}

# Test WhatsApp webhook
test-webhook-whatsapp() {
    echo_info "Testing WhatsApp webhook..."

    curl -X POST http://localhost:8000/webhook/whatsapp \
        -H "Content-Type: application/json" \
        -d '{
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "+1234567890",
                            "id": "test-manual",
                            "text": {"body": "Hola"},
                            "timestamp": "1234567890",
                            "type": "text"
                        }]
                    }
                }]
            }]
        }'
    echo ""
    echo_success "Webhook test complete!"
}

# Show help
help() {
    echo "CubreJardin Bot - Quick Test Commands"
    echo ""
    echo "Usage: source test-quick.sh && <command>"
    echo ""
    echo "Commands:"
    echo "  setup              - Setup test environment"
    echo "  test-backend       - Run all backend tests"
    echo "  test-file <file>   - Run specific test file"
    echo "  test-frontend-types - Run frontend type check"
    echo "  build-frontend     - Build frontend"
    echo "  test-all           - Run full test suite"
    echo "  dev-start          - Start development servers"
    echo "  test-api           - Test API endpoints"
    echo "  test-webhook-whatsapp - Test WhatsApp webhook"
    echo "  help               - Show this help"
    echo ""
}

# Run command if provided as argument
if [ -n "$1" ]; then
    case "$1" in
        setup) setup ;;
        test-backend) test-backend ;;
        test-file) test-file "$2" ;;
        test-frontend-types) test-frontend-types ;;
        build-frontend) build-frontend ;;
        test-all) test-all ;;
        dev-start) dev-start ;;
        test-api) test-api ;;
        test-webhook-whatsapp) test-webhook-whatsapp ;;
        help) help ;;
        *) echo_error "Unknown command: $1" ;;
    esac
fi
