# PolicyCheck v6-Fixed - Complete Project

## 📁 Quick Navigation

### 🚀 Getting Started
1. **[QUICKSTART.md](QUICKSTART.md)** - Start here! Simple 3-step setup guide
2. **[README.md](README.md)** - Full technical documentation  
3. **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Solutions to common issues

### 🎬 Launch Scripts
- **start.bat** (Windows) - One-click startup
- **start.sh** (Mac/Linux) - One-click startup

### 🧪 Testing
- **create-test-data.bat** (Windows) - Generate sample data
- **create-test-data.sh** (Mac/Linux) - Generate sample data

---

## ⚡ Ultra-Quick Start

```bash
# Windows
start.bat

# Mac/Linux  
./start.sh
```

Then open: **http://localhost**

Login: `admin` / `admin123`

---

## 📦 What's Included

### Core Application
- ✅ **Frontend** - React + TypeScript UI
- ✅ **Backend** - FastAPI Python API  
- ✅ **Database** - MySQL 8.0
- ✅ **Cache** - Redis 7

### Features
- ✅ Web crawling for PDF discovery
- ✅ Automatic document classification
- ✅ Search and filter library
- ✅ Bulk downloads (ZIP)
- ✅ CSV exports
- ✅ Audit logging
- ✅ User management
- ✅ Progress tracking

### Documentation
- ✅ Quick start guide
- ✅ Full technical docs
- ✅ Troubleshooting guide
- ✅ API documentation
- ✅ Startup scripts

---

## 🎯 Common Tasks

### First Time Setup
```bash
# 1. Install Docker Desktop
# 2. Run startup script
start.bat  # or ./start.sh

# 3. Open browser
http://localhost

# 4. Login
admin / admin123
```

### Running a Crawl
1. Click "New Crawl" in navigation
2. Review default settings
3. Click "Start Crawl"
4. Monitor in "Progress" page
5. View results in "Library"

### Adding Test Data
```bash
# After application is running
create-test-data.bat  # or ./create-test-data.sh
```

### Viewing Logs
```bash
docker-compose logs -f
```

### Stopping Application  
```bash
docker-compose down
```

### Complete Reset
```bash
docker-compose down -v
docker-compose up -d
```

---

## 📊 System Requirements

### Minimum
- Docker Desktop
- 4GB RAM
- 10GB disk space
- Windows 10/11, macOS 10.15+, or Linux

### Recommended
- 8GB RAM
- 20GB disk space
- SSD storage
- Modern browser (Chrome, Firefox, Edge)

---

## 🔗 URLs When Running

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost | Main application |
| Backend | http://localhost:8000 | API server |
| API Docs | http://localhost:8000/docs | Interactive API documentation |
| ReDoc | http://localhost:8000/redoc | Alternative API docs |

---

## 📚 Project Structure

```
policy-project-v6-fixed/
│
├── 📄 START HERE
│   ├── QUICKSTART.md          ⭐ New user guide
│   ├── README.md              📖 Full documentation  
│   ├── TROUBLESHOOTING.md     🔧 Problem solving
│   └── INDEX.md               📑 This file
│
├── 🚀 LAUNCH SCRIPTS
│   ├── start.bat              🪟 Windows startup
│   ├── start.sh               🐧 Unix startup
│   ├── create-test-data.bat   🪟 Windows test data
│   └── create-test-data.sh    🐧 Unix test data
│
├── 🔧 CONFIGURATION
│   ├── docker-compose.yml     🐳 Service orchestration
│   ├── backend/.env           ⚙️ Backend config
│   └── backend/.env.example   📝 Config template
│
├── 💻 APPLICATION CODE  
│   ├── backend/               🔙 FastAPI application
│   │   ├── app/              📁 Source code
│   │   ├── alembic/          🗄️ Database migrations
│   │   ├── Dockerfile        🐳 Container definition
│   │   └── requirements.txt  📦 Python packages
│   │
│   ├── frontend/             🎨 React application
│   │   ├── src/             📁 Source code
│   │   ├── Dockerfile       🐳 Container definition
│   │   └── package.json     📦 Node packages
│   │
│   └── storage/             💾 Downloaded PDFs (created at runtime)
│
└── 📖 DOCUMENTATION
    └── [All .md files]
```

---

## 🎓 Learning Path

### Beginner
1. Read [QUICKSTART.md](QUICKSTART.md)
2. Start application with `start.bat` / `start.sh`
3. Run test crawl with default settings
4. Explore Library and filters
5. Download a document

### Intermediate
1. Read [README.md](README.md) technical docs
2. Customize crawl settings
3. Add your own seed URLs
4. Use review/approval workflow
5. Export data to CSV

### Advanced
1. Review API docs at `/docs`
2. Modify backend configuration in `.env`
3. Customize frontend components
4. Add custom classification rules
5. Integrate with external systems

---

## 🆘 Getting Help

### Issue | Where to Look
-|-
Can't start | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) → "Container Won't Start"
No documents | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) → "No documents found"
Login fails | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) → "Login Fails"
Crawl issues | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) → "Crawl Completes but Finds 0 PDFs"
Other | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) → Full guide

### Quick Fixes
```bash
# Restart everything
docker-compose restart

# View logs
docker-compose logs -f

# Complete reset
docker-compose down -v
docker-compose up -d
```

---

## ✅ Pre-Flight Checklist

Before starting, ensure:
- [ ] Docker Desktop is installed
- [ ] Docker Desktop is running
- [ ] You have 10GB+ free disk space
- [ ] Ports 80, 8000, 3306, 6379 are available
- [ ] You're in the project root directory

---

## 🎉 Success Indicators

You know it's working when:
- ✅ `docker-compose ps` shows all services "Up" and "healthy"
- ✅ http://localhost loads the login page
- ✅ http://localhost:8000/docs shows API documentation
- ✅ You can login with admin/admin123
- ✅ Dashboard shows statistics

---

## 📝 Notes

- **First startup takes 60-90 seconds** for database initialization
- **Default data is empty** - run a crawl or use test data script
- **Test URLs work best** - Pre-configured NZ insurance companies
- **Downloaded files** are stored in `./storage/` directory
- **All data persists** between restarts (unless you use `-v` flag)

---

## 🚦 Status

**Version:** v6-Fixed  
**Status:** ✅ Production Ready  
**Last Updated:** February 15, 2026  
**Tested On:** Windows 11, macOS, Ubuntu 22.04

---

## 🎯 Next Steps

1. ✅ Read [QUICKSTART.md](QUICKSTART.md)
2. ✅ Run `start.bat` or `./start.sh`
3. ✅ Open http://localhost
4. ✅ Start your first crawl
5. 📚 Read [README.md](README.md) for advanced features

---

**Ready to begin? Start with [QUICKSTART.md](QUICKSTART.md)**
