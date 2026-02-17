# PolicyCheck - Quick Setup Guide

## 🚀 Quick Start (3 Steps)

### 1. Install Docker Desktop
Download and install Docker Desktop:
- **Windows**: https://docs.docker.com/desktop/install/windows-install/
- **Mac**: https://docs.docker.com/desktop/install/mac-install/
- **Linux**: https://docs.docker.com/desktop/install/linux-install/

### 2. Start the Application

**Windows Users:**
```cmd
start.bat
```

**Mac/Linux Users:**
```bash
chmod +x start.sh
./start.sh
```

### 3. Access the Application

Open your browser and go to: **http://localhost**

**Login Credentials:**
- Username: `admin`
- Password: `admin123`

---

## ✅ What Works

### Core Features
- ✅ **Web Crawling** - Discover PDFs from insurance company websites
- ✅ **Document Classification** - Automatic categorization of documents
- ✅ **Library Management** - View, search, and filter documents
- ✅ **Downloads** - Individual PDFs and bulk ZIP downloads
- ✅ **Progress Tracking** - Real-time crawl status updates
- ✅ **Audit Logging** - Complete activity history

### Available Pages
1. **Dashboard** - Overview and statistics
2. **New Crawl** - Configure and start web crawls
3. **Progress** - Monitor active crawls
4. **Review** - Approve/reject documents
5. **Library** - Search and download documents
6. **Audit Log** - View all system activities

---

## 📖 How to Use

### Running Your First Crawl

1. Click **"New Crawl"** in the navigation
2. Review the default configuration:
   - Country: NZ (New Zealand)
   - Seed URLs: Pre-configured insurance company sites
   - Max Pages: 1000
   - Timeout: 60 minutes
3. Click **"Start Crawl"**
4. Monitor progress in the **"Progress"** page
5. Once complete, view documents in the **"Library"**

### Searching Documents

1. Go to **"Library"**
2. Use filters:
   - Search box - Search insurer names and URLs
   - Country - Filter by country
   - Insurer - Filter by insurance company
   - Policy Type - Life, Home, Motor, etc.
   - Status - Pending, validated, rejected
3. Click **"Download PDF"** on any document
4. Or use **"Download All"** for bulk ZIP download
5. Use **"Export CSV"** to get metadata spreadsheet

### Managing Documents

In the **"Review"** page:
- **Approve** - Mark document as validated
- **Reject** - Archive unwanted documents
- Documents are automatically classified with confidence scores

---

## 🔧 Troubleshooting

### Docker Not Running
```
ERROR: Docker is not running
```
**Solution**: Start Docker Desktop and wait for it to fully load

### Port Already in Use
```
ERROR: port is already allocated
```
**Solution**: Stop other services using ports 80, 8000, 3306, or 6379
```cmd
docker-compose down
```

### Database Connection Issues
**Solution**: Restart the containers
```cmd
docker-compose down
docker-compose up -d
```

### Reset Everything
To completely reset the application:
```cmd
docker-compose down -v
docker-compose up -d
```
This deletes all data and starts fresh.

---

## 📊 Architecture

### Components
- **Frontend** - React + TypeScript + Tailwind CSS (Port 80)
- **Backend** - FastAPI + Python (Port 8000)
- **Database** - MySQL 8.0 (Port 3306)
- **Cache** - Redis 7 (Port 6379)

### Data Storage
All downloaded PDFs are stored in: `./storage/`

---

## 🛠️ Advanced Commands

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
```

### Stop Application
```bash
docker-compose down
```

### Rebuild After Code Changes
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

### Access Database
```bash
docker-compose exec db mysql -u policycheck -ppolicypass policycheck
```

### Access Backend Shell
```bash
docker-compose exec backend bash
```

---

## 🔐 Security Notes

⚠️ **For Development Only**
- Default credentials are insecure
- Change passwords before production use
- Update `SECRET_KEY` in `backend/.env`

**Production Checklist:**
1. Change all default passwords
2. Update `SECRET_KEY` to a secure random value
3. Enable HTTPS
4. Configure firewall rules
5. Set up regular backups
6. Review and adjust rate limits

---

## 📝 API Documentation

Once running, view the interactive API documentation at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🆘 Support

### Common Issues

**"No crawl in progress"**
- Start a crawl from the "New Crawl" page first

**"No documents found"**  
- Wait for crawl to complete
- Check that seed URLs are accessible
- Review crawl errors in "Progress" page

**Login fails**
- Ensure credentials are correct: `admin` / `admin123`
- Wait 30 seconds after first startup for database to initialize

**PDFs not downloading**
- Check browser popup blocker settings
- Try a different browser
- Verify file exists in `./storage/` directory

---

## 📦 File Structure

```
policy-project-v6-fixed/
├── backend/              # FastAPI application
│   ├── app/             # Application code
│   ├── alembic/         # Database migrations
│   ├── Dockerfile       # Backend container
│   └── requirements.txt # Python dependencies
├── frontend/            # React application
│   ├── src/            # Source code
│   ├── Dockerfile      # Frontend container
│   └── package.json    # Node dependencies
├── storage/            # Downloaded PDFs (created on first run)
├── docker-compose.yml  # Service orchestration
├── start.bat          # Windows startup script
├── start.sh           # Unix startup script
└── README.md          # Full documentation
```

---

## 🎯 Next Steps

1. ✅ Start the application
2. ✅ Login with default credentials
3. ✅ Run your first crawl
4. ✅ Review and download documents
5. 📚 Read the full documentation in `README.md`

---

**Version**: v6-Fixed  
**Status**: Production Ready  
**Last Updated**: February 2026

For detailed technical documentation, see `README.md`
