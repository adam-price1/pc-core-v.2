@echo off
echo.
echo ========================================
echo   PolicyCheck - Starting Application
echo ========================================
echo.

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running. Please start Docker Desktop first.
    echo.
    pause
    exit /b 1
)

echo [1/4] Stopping any existing containers...
docker-compose down

echo.
echo [2/4] Building containers...
docker-compose build

echo.
echo [3/4] Starting services...
docker-compose up -d

echo.
echo [4/4] Waiting for services to be ready...
timeout /t 10 /nobreak > nul

echo.
echo ========================================
echo   PolicyCheck is starting!
echo ========================================
echo.
echo   Frontend: http://localhost
echo   Backend API: http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
echo Default login credentials:
echo   Username: admin
echo   Password: admin123
echo.
echo To view logs: docker-compose logs -f
echo To stop: docker-compose down
echo.
pause
