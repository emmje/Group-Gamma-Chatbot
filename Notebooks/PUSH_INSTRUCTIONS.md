# How to Push to GitHub - Fix Authentication Error

## The Error
```
fatal: could not read Username for 'https://github.com': No such device or address
```

This happens because Git can't prompt for credentials in non-interactive mode.

## Solutions (Choose One)

### Option 1: Use Personal Access Token in URL (Easiest)

Replace `YOUR_TOKEN` with your GitHub Personal Access Token:

```bash
cd /home/nico/Downloads/Notebooks-20251124T065302Z-1-001/Notebooks
git push https://YOUR_TOKEN@github.com/emmje/Group-Gamma-Chatbot.git main
```

**To get a token:**
1. Go to GitHub.com → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token (classic)
3. Give it `repo` permissions
4. Copy the token and use it above

### Option 2: Configure Git Credentials

```bash
# Set your username
git config --global user.name "emmje"

# Set credential helper
git config --global credential.helper store

# Then push (will prompt once, then save)
git push
# When prompted:
#   Username: emmje
#   Password: <paste your token>
```

### Option 3: Switch to SSH (If you have SSH keys)

```bash
# Change remote to SSH
git remote set-url origin git@github.com:emmje/Group-Gamma-Chatbot.git

# Push
git push
```

### Option 4: Use GitHub CLI (if installed)

```bash
gh auth login
git push
```

## Quick Test

After setting up, verify:
```bash
git remote -v
git push
```

## Security Note

⚠️ **Never commit tokens or passwords to Git!**
- Tokens in URLs are only for command line (not saved in repo)
- Use credential helper to store securely
- Or use SSH keys for better security

