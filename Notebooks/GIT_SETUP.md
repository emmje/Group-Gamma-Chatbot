# Git & GitHub Setup Guide

## Step 1: Add and Commit Your Files

```bash
cd /home/nico/Downloads/Notebooks-20251124T065302Z-1-001/Notebooks

# Add all project files (venv is now ignored)
git add .

# Commit your changes
git commit -m "Initial commit: UCU Chatbot with zero-shot classification"
```

## Step 2: Create GitHub Repository

1. Go to [GitHub.com](https://github.com) and sign in
2. Click the **"+"** icon in the top right → **"New repository"**
3. Name your repository (e.g., `ucu-chatbot`)
4. Choose **Public** or **Private**
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click **"Create repository"**

## Step 3: Connect Local Repository to GitHub

After creating the repository, GitHub will show you commands. Use these:

```bash
# Add GitHub remote (replace YOUR_USERNAME and REPO_NAME)
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# Or if using SSH:
git remote add origin git@github.com:YOUR_USERNAME/REPO_NAME.git

# Push your code
git branch -M main
git push -u origin main
```

## Step 4: Verify

Check that everything is connected:

```bash
git remote -v
```

You should see your GitHub repository URL.

## What Gets Pushed

✅ **Included:**
- `chatbot_zeroshot.py` - Main chatbot
- `app.py` - Streamlit interface
- `intents.json` - Intent data
- `requirements_zeroshot.txt` - Dependencies
- `setup_zeroshot.sh` - Setup script
- `README.md` - Documentation
- `.gitignore` - Git ignore rules

❌ **Excluded (via .gitignore):**
- `venv/` - Virtual environment
- `__pycache__/` - Python cache
- `.ipynb_checkpoints/` - Jupyter checkpoints

## Future Updates

After making changes:

```bash
git add .
git commit -m "Description of your changes"
git push
```

## Troubleshooting

**"remote origin already exists":**
```bash
git remote remove origin
git remote add origin YOUR_GITHUB_URL
```

**"Permission denied":**
- Make sure you're authenticated with GitHub
- Use `gh auth login` if you have GitHub CLI
- Or use SSH keys instead of HTTPS

