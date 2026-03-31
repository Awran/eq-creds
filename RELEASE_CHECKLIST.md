# Release Checklist

Use this checklist when publishing EQ-Creds on GitHub.

## Before Publishing

- Confirm the app launches from `dist/EQCreds.exe`
- Confirm unlock/create-vault flow works
- Confirm add/edit/delete account flow works
- Confirm password reveal works
- Confirm search works for account names, characters, and tags
- Confirm both dark and light themes work
- Confirm icon appears correctly on the EXE and running window
- Confirm `%APPDATA%\EQCreds\vault.db` is created as expected
- Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

## Build Release Binary

```powershell
Get-Process EQCreds -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
.\.venv\Scripts\pyinstaller.exe build.spec
```

Release artifact:

- `dist/EQCreds.exe`

## GitHub Repo Setup

- Create a new GitHub repository
- Push the source tree
- Include `README.md`
- Ensure `.gitignore` excludes `.venv/`, `dist/`, `build/`, and `*.db`

## GitHub Release Setup

Create a release such as:

- Tag: `v1.0.0`
- Title: `EQ-Creds 1.0.0`

Upload:

- `dist/EQCreds.exe`

## Suggested Release Notes

```text
EQ-Creds 1.0.0

Windows-first local desktop app for managing low-security shared Project 1999 / EverQuest account credentials.

Highlights
- Local encrypted credential vault
- Search by account, character, owner, and tags
- One account to many characters
- Password masked by default with explicit reveal
- Light and dark themes
- No cloud sync, no telemetry, no game client interaction

Important Notes
- Local-only release
- Vault stored under %APPDATA%\EQCreds\vault.db
- Not an enterprise password manager
```

## Post-Publish Check

- Download the release artifact from GitHub Releases
- Run it on a clean machine or clean user profile if possible
- Confirm first-launch flow works without Python installed
- Confirm icon and app name appear correctly
