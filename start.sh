#!/bin/bash

echo ""
echo "========================================"
echo "  PolicyCheck - Starting Application"
echo "========================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running. Please start Docker first."
    echo ""
    exit 1
fi

echo "[1/4] Stopping any existing containers..."
docker-compose down

echo ""
echo "[2/4] Building containers..."
docker-compose build

echo ""
echo "[3/4] Starting services..."
docker-compose up -d

echo ""
echo "[4/4] Waiting for services to be ready..."
sleep 10

echo ""
echo "========================================"
echo "  PolicyCheck is running!"
echo "========================================"
echo ""
echo "  Frontend: http://localhost"
echo "  Backend API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Default login credentials:"
echo "  Username: admin"
echo "  Password: admin123"
echo ""
echo "To view logs: docker-compose logs -f"
echo "To stop: docker-compose down"
echo ""
