#!/bin/bash

# Professional Crawler Dataset Creator - Startup Script
# This script provides easy commands to manage the crawler dataset system

set -e

COMPOSE_FILE="docker-compose.yml"
PROJECT_NAME="crawler-dataset"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
}

# Function to check if Docker Compose is available
check_docker_compose() {
    if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
        print_error "Docker Compose is not installed."
        exit 1
    fi
}

# Function to start all services
start_services() {
    print_info "Starting all services..."
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME up -d
    print_success "Services started successfully!"

    print_info "Waiting for services to be ready..."
    sleep 10

    print_info "Service URLs:"
    echo "  Web UI:     http://localhost:3000"
    echo "  API:        http://localhost:8000"
    echo "  MinIO:      http://localhost:9001 (admin/admin)"
    echo "  Grafana:    http://localhost:3001 (admin/admin)"
    echo "  Prometheus: http://localhost:9090"
}

# Function to stop all services
stop_services() {
    print_info "Stopping all services..."
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME down
    print_success "Services stopped successfully!"
}

# Function to restart services
restart_services() {
    print_info "Restarting all services..."
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME restart
    print_success "Services restarted successfully!"
}

# Function to view logs
view_logs() {
    service=${1:-""}
    if [ -z "$service" ]; then
        print_info "Viewing logs for all services (Ctrl+C to exit)..."
        docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f
    else
        print_info "Viewing logs for $service (Ctrl+C to exit)..."
        docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f $service
    fi
}

# Function to check service status
check_status() {
    print_info "Checking service status..."
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME ps
}

# Function to run a crawl
run_crawl() {
    url=${1:-""}
    depth=${2:-3}

    if [ -z "$url" ]; then
        print_error "Usage: $0 crawl <url> [depth]"
        exit 1
    fi

    print_info "Starting crawl of $url with depth $depth..."

    # Use API to start crawl
    response=$(curl -s -X POST http://localhost:8000/crawl \
        -H "Content-Type: application/json" \
        -d "{\"start_url\": \"$url\", \"max_depth\": $depth}")

    if [ $? -eq 0 ]; then
        job_id=$(echo $response | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)
        print_success "Crawl started with job ID: $job_id"
        print_info "Monitor progress at: http://localhost:3000"
    else
        print_error "Failed to start crawl"
    fi
}

# Function to process data
run_process() {
    print_info "Starting data processing..."

    response=$(curl -s -X POST http://localhost:8000/process \
        -H "Content-Type: application/json" \
        -d '{"raw_dir": "dataset/raw", "output_dir": "dataset"}')

    if [ $? -eq 0 ]; then
        job_id=$(echo $response | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)
        print_success "Processing started with job ID: $job_id"
        print_info "Monitor progress at: http://localhost:3000"
    else
        print_error "Failed to start processing"
    fi
}

# Function to tokenize data
run_tokenize() {
    print_info "Starting tokenization and sharding..."

    response=$(curl -s -X POST http://localhost:8000/tokenize \
        -H "Content-Type: application/json" \
        -d '{
            "cleaned_dir": "dataset/cleaned",
            "shards_dir": "dataset/shards",
            "model_name": "microsoft/DialoGPT-medium",
            "max_length": 2048,
            "val_split": 0.05
        }')

    if [ $? -eq 0 ]; then
        job_id=$(echo $response | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)
        print_success "Tokenization started with job ID: $job_id"
        print_info "Monitor progress at: http://localhost:3000"
    else
        print_error "Failed to start tokenization"
    fi
}

# Function to show dataset summary
show_summary() {
    print_info "Getting dataset summary..."

    response=$(curl -s http://localhost:8000/dataset/summary)

    if [ $? -eq 0 ]; then
        echo "$response" | python3 -m json.tool
    else
        print_error "Failed to get dataset summary"
    fi
}

# Function to create dataset version
create_version() {
    description=${1:-""}

    if [ -z "$description" ]; then
        print_error "Usage: $0 version <description>"
        exit 1
    fi

    print_info "Creating dataset version..."

    response=$(curl -s -X POST "http://localhost:8000/dataset/version?description=$description")

    if [ $? -eq 0 ]; then
        version=$(echo $response | grep -o '"version":"[^"]*' | cut -d'"' -f4)
        print_success "Created dataset version: $version"
    else
        print_error "Failed to create version"
    fi
}

# Function to clean up data
cleanup() {
    print_warning "This will remove all crawled data and reset the database!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cleaning up data..."

        # Stop services
        docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME down

        # Remove volumes
        docker volume rm ${PROJECT_NAME}_postgres_data ${PROJECT_NAME}_redis_data ${PROJECT_NAME}_minio_data ${PROJECT_NAME}_prometheus_data ${PROJECT_NAME}_grafana_data 2>/dev/null || true

        # Remove dataset directory
        rm -rf dataset/

        print_success "Cleanup completed!"
    fi
}

# Function to show help
show_help() {
    echo "Professional Crawler Dataset Creator"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start          Start all services"
    echo "  stop           Stop all services"
    echo "  restart        Restart all services"
    echo "  status         Show service status"
    echo "  logs [service] View logs (all services or specific service)"
    echo "  crawl <url> [depth]  Start crawling a website"
    echo "  process        Process crawled data"
    echo "  tokenize       Create training shards"
    echo "  summary        Show dataset summary"
    echo "  version <desc> Create new dataset version"
    echo "  cleanup        Remove all data and reset"
    echo "  help           Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 start"
    echo "  $0 crawl https://kubernetes.io/docs/home/ 3"
    echo "  $0 logs crawler"
    echo "  $0 version 'Initial crawl of Kubernetes docs'"
    echo ""
    echo "Services:"
    echo "  Web UI:     http://localhost:3000"
    echo "  API:        http://localhost:8000"
    echo "  MinIO:      http://localhost:9001"
    echo "  Grafana:    http://localhost:3001"
    echo "  Prometheus: http://localhost:9090"
}

# Main script logic
check_docker
check_docker_compose

case "${1:-help}" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        check_status
        ;;
    logs)
        view_logs "$2"
        ;;
    crawl)
        run_crawl "$2" "$3"
        ;;
    process)
        run_process
        ;;
    tokenize)
        run_tokenize
        ;;
    summary)
        show_summary
        ;;
    version)
        create_version "$2"
        ;;
    cleanup)
        cleanup
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
