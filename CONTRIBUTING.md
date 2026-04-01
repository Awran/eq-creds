# Contributing to EQ-Creds

This project is not actively seeking external contributions, but this guide documents the development setup and release process for maintainers and anyone interested in building from source.

## Development Setup

### Prerequisites

- Python 3.9 or later
- Git
- pip

### Local Build

```bash
git clone https://github.com/yourusername/eq-creds.git
cd eq-creds

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Build executable
python -m pyinstaller build.spec
# Output: dist/EQCreds.exe
```

## Testing

All tests must pass before committing:

```bash
python -m pytest tests/ -v
```

Current test coverage:
- Crypto: key derivation, encryption/decryption, nonce uniqueness, AAD binding
- Database: account CRUD, character relationships, search, re-key operations
- Total: 27 tests

## Release Process (Maintainer Only)

### Pre-Release QA

Run these checks before creating a release:

- [ ] Confirm `dist/EQCreds.exe` launches without errors
- [ ] Confirm unlock/create-vault flow works
- [ ] Confirm add/edit/delete account flow works
- [ ] Confirm password reveal works (15-second auto-mask)
- [ ] Confirm search works across account names, characters, and tags
- [ ] Confirm both dark and light themes render correctly
- [ ] Confirm icon appears on EXE file properties and running window
- [ ] Confirm `%APPDATA%\EQCreds\vault.db` is created on first launch
- [ ] Run full test suite: `python -m pytest tests/ -v` (all 27 tests pass)

### Build Release Binary

```powershell
# Stop any running instance
Get-Process EQCreds -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Build
.\.venv\Scripts\pyinstaller.exe build.spec
```

Release artifact: `dist/EQCreds.exe`

### GitHub Release Steps

1. Create a tag: `git tag -a v1.0.0 -m "Release 1.0.0"`
2. Push tag: `git push origin v1.0.0`
3. On GitHub:
   - Go to Releases → Create Release
   - Tag: `v1.0.0`
   - Title: `EQ-Creds 1.0.0`
   - Description: Use [RELEASE_NOTES.md](RELEASE_NOTES.md) content
   - Upload `dist/EQCreds.exe` as asset

### Post-Release Verification

- [ ] Download EQCreds.exe from GitHub Releases
- [ ] Run on a clean machine or clean Windows user profile
- [ ] Confirm first-launch and unlock flows work without Python installed
- [ ] Confirm icon and taskbar display correctly

## Code Style

No strict style guide enforced. Please follow:
- PEP 8 for Python code
- Descriptive variable/function names
- Comments for non-obvious logic
- Type hints where practical (Pydantic models are already typed)

## Commit Messages

Use clear, descriptive messages:

```
Feature: Add clipboard auto-clear timer
Fix: Increase Show button width to 65px
Docs: Update README with build instructions
Tests: Add import/export roundtrip validation
```

## Project Scope

EQ-Creds intentionally excludes:
- Cloud sync
- Game client interaction
- Login automation
- Telemetry
- Browser extensions

These are permanent out-of-scope decisions to maintain the product's narrow focus and safety model.

## Questions?

Open an issue on GitHub for questions or suggestions.
