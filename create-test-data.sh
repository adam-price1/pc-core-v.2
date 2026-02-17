#!/bin/bash

echo ""
echo "========================================"
echo "  Creating Test Data"
echo "========================================"
echo ""

docker-compose exec backend python /app/create_test_data.py

echo ""
echo "Test data created!"
echo ""
echo "Visit http://localhost to see the data"
echo ""
