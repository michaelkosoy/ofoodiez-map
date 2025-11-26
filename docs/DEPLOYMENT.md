# Ofoodiez Map - Deployment Guide

## Quick Deploy to Render (FREE)

### Prerequisites
1. Create a free account at [render.com](https://render.com)
2. Install Git if you haven't already
3. Push your code to GitHub (or GitLab/Bitbucket)

### Step 1: Prepare Your Repository

```bash
# Initialize git if not already done
cd "/Users/mkosoy/Projects/Ofoodiez Map"
git init
git add .
git commit -m "Initial commit - Ofoodiez Map"

# Create a new repository on GitHub, then:
git remote add origin YOUR_GITHUB_REPO_URL
git push -u origin main
```

### Step 2: Deploy on Render

1. Go to [render.com](https://render.com) and sign in
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub account and select your repository
4. Configure:
   - **Name**: `ofoodiez-map` (or your preferred name)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: `Free`

5. Add Environment Variable:
   - Key: `GOOGLE_MAPS_API_KEY`
   - Value: `AIzaSyBdh_bKAGD6ZFbNpq3G_2tmV1BlaedFcPU`

6. Click **"Create Web Service"**

### Step 3: Wait for Deployment

Render will automatically:
- Install dependencies
- Start your Flask app
- Provide you with a URL like: `https://ofoodiez-map.onrender.com`

**Note**: Free tier may take 30-60 seconds to wake up on first visit after inactivity.

---

## Alternative: Deploy to PythonAnywhere (FREE)

1. Create account at [pythonanywhere.com](https://www.pythonanywhere.com)
2. Upload your files via their web interface
3. Configure a web app with Flask
4. Set your working directory and WSGI configuration

---

## Alternative: Deploy to Railway (FREE with limits)

1. Go to [railway.app](https://railway.app)
2. Click "Start a New Project"
3. Select "Deploy from GitHub repo"
4. Railway auto-detects Flask and deploys

---

## Important Notes

- **Excel File**: Your `places.xlsx` will be read-only on most free hosts. For production, consider using a database (PostgreSQL/MySQL).
- **API Key**: Keep your Google Maps API key secure. Consider restricting it to your domain in Google Cloud Console.
- **Free Tier Limits**: 
  - Render: 750 hours/month, sleeps after 15 min inactivity
  - PythonAnywhere: Always on, but limited CPU
  - Railway: 500 hours/month

## Recommended: Render.com

**Why Render?**
- ✅ Easiest setup
- ✅ Auto-deploys from GitHub
- ✅ Free SSL certificate
- ✅ Good performance
- ✅ No credit card required
