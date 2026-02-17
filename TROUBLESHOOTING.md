# Troubleshooting Guide - PolicyCheck

This guide addresses common issues based on real user experiences.

---

## Issue: PowerShell Error - "https://localhost:8000/docs is not recognized"

### Symptoms
When trying to start the application, you see an error in PowerShell:
```
https://localhost:8000/docs : The term 'https://localhost:8000/docs' is not recognized as the name of a cmdlet...
```

### Root Cause
The startup script is trying to open a URL as if it were a command.

### Solution
Use the provided startup scripts instead:

**Windows:**
```cmd
start.bat
```

**Or manually:**
```cmd
docker-compose down
docker-compose build
docker-compose up -d
```

Then open your browser manually to: `http://localhost`

---

## Issue: "No crawl in progress"

### Symptoms
- Navigate to "Progress" page
- See message: "No crawl in progress"
- "Go to Crawl Manager" button is shown

### Root Cause
The Progress page expects a `crawl_id` URL parameter. If you navigate directly to `/progress` without starting a crawl, this message appears.

### Solution
1. Go to **"New Crawl"** page (navigation menu or "Crawl Manager" button)
2. Configure your crawl settings
3. Click **"Start Crawl"**
4. You'll be automatically redirected to the Progress page with the correct URL

**OR** if you have an existing crawl:
1. Go to **"New Crawl"** page
2. Find your crawl in the "Crawl History" section at the bottom
3. Click **"View"** button next to the crawl
4. This will load that crawl's progress

---

## Issue: "No audit entries found"

### Symptoms
- Audit Log page shows "No audit entries found"
- No filter dropdowns appear

### Root Cause
The audit log is empty because no actions have been performed yet.

### Solution
Audit entries are created when you:
- Start a crawl
- Download a document
- Approve or reject a document
- Delete a crawl

**To populate audit log:**
1. Start a crawl from "New Crawl" page
2. Wait for it to complete
3. Download a document from the Library
4. Check Audit Log - you'll see entries

**Alternative - Use test data:**
```cmd
create-test-data.bat
```
This creates sample data to explore the UI.

---

## Issue: "No documents found" in Library

### Symptoms
- Library page shows "No documents found"
- Filter dropdowns are empty
- Download All button is disabled

### Root Cause
No crawls have been completed yet, or completed crawls found no documents.

### Solutions

### Option 1: Run a Real Crawl
1. Go to **"New Crawl"**
2. Use the default seed URLs (NZ insurance companies)
3. Click **"Start Crawl"**
4. Wait for completion (check Progress page)
5. Documents will appear in Library

### Option 2: Use Test Data
```cmd
create-test-data.bat
```
Creates 10+ sample documents instantly for testing.

### Option 3: Check Seed URLs
If your crawl completed but found no documents:
- Verify seed URLs are accessible
- Check that URLs contain links to PDF files
- Review error count in crawl history
- Try different seed URLs

---

## Issue: Crawl Completes but Finds 0 PDFs

### Symptoms
- Crawl status shows "completed"
- Pages scanned: 1 or more
- PDFs Found: 0
- PDFs Downloaded: 0

### Root Cause
The seed URLs either:
1. Don't contain PDF links
2. Are blocked by robots.txt
3. Don't match the keyword filters
4. Had network issues

### Solutions

**Check Seed URLs Are Accessible:**
Open each seed URL in your browser. Do you see links to policy documents?

**Simplify Configuration:**
1. Remove all keyword filters (leave blank)
2. Remove policy type filters  
3. Increase max pages to 2000
4. Increase timeout to 90 minutes
5. Try again

**Try Different Seed URLs:**
Known working URLs (as of Feb 2026):
```
https://www.aainsurance.co.nz/products
https://www.ami.co.nz/insurance  
https://www.tower.co.nz/products
```

**Check Crawl Details:**
1. Go to "New Crawl" page
2. Find the crawl in history
3. Look at error count
4. If high errors, may be network/access issues

---

## Issue: Can't Download PDFs

### Symptoms
- Click "Download PDF" button
- Nothing happens or error appears
- Browser doesn't prompt to save file

### Solutions

**Check Browser:**
1. Disable popup blocker for localhost
2. Check browser downloads folder for blocks
3. Try different browser (Chrome, Firefox, Edge)
4. Check browser console for errors (F12 key)

**Verify Document Exists:**
If using test data, documents are mock entries. Try:
1. Run a real crawl first
2. Or use sample seed URLs that return PDFs

**Check File Permissions:**
```cmd
# Check storage directory exists and is writable
dir storage
```

**Backend Logs:**
```cmd
docker-compose logs backend | findstr download
```
Look for permission or file-not-found errors.

---

## Issue: Docker Container Won't Start

### Symptoms
```
ERROR: Cannot start service backend: ...
```

### Solutions

**Check Docker is Running:**
```cmd
docker ps
```
Should list running containers. If error, start Docker Desktop.

**Check Ports Are Available:**
```cmd
netstat -ano | findstr ":80 "
netstat -ano | findstr ":8000 "
netstat -ano | findstr ":3306 "
```
If ports are in use, stop other services or change ports in docker-compose.yml.

**Reset Everything:**
```cmd
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

**View Detailed Logs:**
```cmd
docker-compose logs backend
docker-compose logs frontend  
docker-compose logs db
```

---

## Issue: Database Connection Failed

### Symptoms
Backend logs show:
```
Can't connect to MySQL server
Connection refused
```

### Solutions

**Wait for Database:**
The database takes 30-60 seconds to fully initialize on first start.

```cmd
# Check database is ready
docker-compose logs db | findstr "ready for connections"
```

**Restart Services:**
```cmd
docker-compose restart backend
```

**Complete Reset:**
```cmd
docker-compose down -v
docker-compose up -d
```

**Check Database Health:**
```cmd
docker-compose ps
```
DB service should show "healthy" status.

---

## Issue: Frontend Shows "Failed to fetch" Errors

### Symptoms
- Can access frontend at localhost
- API calls fail with network errors
- Console shows CORS or connection errors

### Solutions

**Check Backend is Running:**
```cmd
docker-compose ps backend
```
Should show "Up" status.

**Test API Directly:**
Open in browser: `http://localhost:8000/health/liveness`
Should return: `{"status": "ok"}`

**Check Docker Network:**
```cmd
docker-compose down
docker-compose up -d
```

**View Backend Logs:**
```cmd
docker-compose logs backend -f
```
Look for startup errors.

---

## Issue: Login Fails

### Symptoms
- Enter username and password
- Login button doesn't work
- Error message appears

### Solutions

**Use Correct Credentials:**
```
Username: admin
Password: admin123
```
(Case sensitive!)

**Wait for System Startup:**
First time startup takes 60-90 seconds. Wait and try again.

**Check Backend Logs:**
```cmd
docker-compose logs backend | findstr "error\|Error\|ERROR"
```

**Reset Admin Password:**
```cmd
docker-compose exec backend python -c "
from app.database import SessionLocal
from app.models import User
from app.auth import get_password_hash
db = SessionLocal()
admin = db.query(User).filter(User.username == 'admin').first()
if admin:
    admin.hashed_password = get_password_hash('admin123')
    db.commit()
    print('Password reset!')
"
```

---

## General Debugging Commands

### View All Logs
```cmd
docker-compose logs -f
```

### View Specific Service
```cmd
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f db
docker-compose logs -f redis
```

### Check Service Status
```cmd
docker-compose ps
```

### Restart a Service
```cmd
docker-compose restart backend
docker-compose restart frontend
```

### Access Backend Shell
```cmd
docker-compose exec backend bash
```

### Access Database
```cmd
docker-compose exec db mysql -u policycheck -ppolicypass policycheck
```

### Check Disk Space
```cmd
docker system df
```

### Clean Up Docker
```cmd
docker system prune -a
```

---

## Getting Help

If issues persist:

1. **Collect Logs:**
   ```cmd
   docker-compose logs > logs.txt
   ```

2. **Check System Resources:**
   - Docker Desktop: 4GB+ RAM allocated
   - 10GB+ free disk space
   - No firewall blocking ports 80, 8000, 3306, 6379

3. **Document:**
   - What you did
   - What you expected
   - What happened instead
   - Error messages
   - Screenshots

4. **Restart Fresh:**
   ```cmd
   docker-compose down -v
   docker system prune -a
   docker-compose up -d
   ```

---

**Last Updated:** February 2026  
**Version:** v6-Fixed
