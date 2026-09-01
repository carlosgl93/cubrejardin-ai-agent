#!/bin/bash
# E2E Test Runner for CubreJardin Bot
# Usage: ./run-e2e.sh [backend|frontend|all]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="/Users/consultor/cgl/sg-cloud-workspace/cubrejardin-bot"
FRONTEND_DIR="/Users/consultor/cgl/sg-cloud-workspace/astro-sg-cloud"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Check prerequisites
check_prereqs() {
    log_info "Checking prerequisites..."

    # Check if services are running
    if curl -s http://localhost:8000/admin/health > /dev/null 2>&1; then
        log_success "Backend API is running at http://localhost:8000"
    else
        log_warn "Backend API not running. Start with: uvicorn main:app --reload --port 8000"
    fi

    if curl -s http://localhost:4321 > /dev/null 2>&1; then
        log_success "Frontend is running at http://localhost:4321"
    else
        log_warn "Frontend not running. Start with: npm run dev"
    fi
}

# Install Playwright browsers
install_browsers() {
    log_info "Installing Playwright browsers..."
    cd "$FRONTEND_DIR"
    npx playwright install --with-deps chromium
    log_success "Playwright browsers installed"
}

# Run backend E2E tests
run_backend_e2e() {
    log_info "Running Backend E2E Tests..."
    cd "$BACKEND_DIR"
    source venv/bin/activate

    # Set environment variables
    export API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
    export FRONTEND_URL="${FRONTEND_URL:-http://localhost:4321}"

    # Run E2E tests
    pytest tests/e2e/ -v --tb=short

    log_success "Backend E2E tests completed!"
}

# Run frontend E2E tests
run_frontend_e2e() {
    log_info "Running Frontend E2E Tests..."
    cd "$FRONTEND_DIR"

    # Set environment variables
    export FRONTEND_URL="${FRONTEND_URL:-http://localhost:4321}"
    export API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

    # Run Playwright tests
    npm run test:e2e -- "$@"

    log_success "Frontend E2E tests completed!"
}

# Run all E2E tests
run_all_e2e() {
    log_info "Running All E2E Tests..."

    run_backend_e2e
    run_frontend_e2e

    log_success "All E2E tests completed!"
}

# Start services for testing
start_services() {
    log_info "Starting services for E2E testing..."

    # Start backend
    cd "$BACKEND_DIR"
    source venv/bin/activate
    uvicorn main:app --reload --port 8000 &
    BACKEND_PID=$!

    # Wait for backend
    log_info "Waiting for backend to start..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/admin/health > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    # Start frontend
    cd "$FRONTEND_DIR"
    npm run dev &
    FRONTEND_PID=$!

    # Wait for frontend
    log_info "Waiting for frontend to start..."
    for i in {1..30}; do
        if curl -s http://localhost:4321 > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    log_success "Services started!"
    log_info "Backend: http://localhost:8000"
    log_info "Frontend: http://localhost:4321"
    log_info ""
    log_info "Press Ctrl+C to stop services"

    # Wait for interrupt
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
    wait
}

# Show help
show_help() {
    echo "CubreJardin Bot - E2E Test Runner"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  backend         Run backend E2E tests"
    echo "  frontend        Run frontend E2E tests"
    echo "  all             Run all E2E tests"
    echo "  install         Install Playwright browsers"
    echo "  start           Start services for E2E testing"
    echo "  check           Check if services are running"
    echo "  help            Show this help"
    echo ""
    echo "Environment Variables:"
    echo "  API_BASE_URL    Backend API URL (default: http://localhost:8000)"
    echo "  FRONTEND_URL    Frontend URL (default: http://localhost:4321)"
    echo ""
    echo "Examples:"
    echo "  $0 install       # Install Playwright browsers"
    echo "  $0 start         # Start services"
    echo "  $0 backend       # Run backend E2E tests"
    echo "  $0 frontend      # Run frontend E2E tests"
    echo "  $0 all           # Run all E2E tests"
}

# Main
case "${1:-help}" in
    backend) check_prereqs && run_backend_e2e ;;
    frontend) check_prereqs && run_frontend_e2e ;;
    all) check_prereqs && run_all_e2e ;;
    install) install_browsers ;;
    start) start_services ;;
    check) check_prereqs ;;
    help|--help|-h) show_help ;;
    *) log_error "Unknown command: $1" && show_help && exit 1 ;;
esac
