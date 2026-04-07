# EQ-Creds v1.1.0 Release Notes

## ✨ New Feature — Secure Export / Import

### Export
- New **⬆ Export** toolbar button opens the Export Accounts dialog.
- Select any subset of accounts via a checkable list (Select All / Deselect All).
- Set a dedicated export password — completely independent of the vault master password.
- Saves an encrypted `.eqcx` bundle; default filename is `eqcreds-export-YYYY-MM-DD.eqcx`.

### Import
- New **⬇ Import** toolbar button opens the Import Accounts dialog.
- Browse for a `.eqcx` file and enter its export password, then click **Preview**.
- A full-detail table shows every account in the bundle: label, username, character count, and action.
  - Clean accounts (no conflict) are marked **New**.
  - Conflicting accounts (matched by username, or label when username is blank) show a **Skip / Merge** selector.
- **Merge All** and **Skip All** bulk buttons available when conflicts exist.
- Merge keeps the existing account's ID and creation date while updating all other fields and characters.

### .eqcx Format
- Binary format: 5-byte magic + version header (used as AAD) + 16-byte Argon2id salt + 12-byte nonce + AES-256-GCM ciphertext.
- Tampered or truncated files are rejected with an authenticated-encryption integrity failure.
- No new runtime dependencies.

### Internals
- New `core/errors.py` module consolidates shared exception types (`WrongPasswordError`, `VaultNotInitializedError`, `VaultLockedError`) to eliminate a circular import.
- New `core/export_import.py` module handles all bundle encoding/decoding and conflict detection.
- 20 new unit tests; total test count: 47.

---

# EQ-Creds v1.0.1 Release Notes

## 🔧 Patch — Bug Fixes & Performance

### Bug Fixes
- **Memory safety**: `unlock()` now zeros the previous session key bytearray before replacing it; `change_password()` no longer calls `unlock()` internally, closing a key-orphaning code path.
- **Tag save atomicity**: `set_account_tags()` previously opened nested transactions that committed mid-loop; all tag operations now execute in a single atomic transaction.

### Performance
- `list_accounts()` now uses two batch queries for characters and tags regardless of vault size, replacing an O(N) per-account query loop.
- `search()` returns full account rows directly, eliminating a redundant per-account `get_account_raw()` round-trip.

### Internals
- `uuid4` and `hmac` imports moved to module level.
- Duplicate SQLite PRAGMAs removed from DDL (already set in connection factory).
- Build-only dependencies (`Pillow`, `pyinstaller`) moved to `requirements-build.txt`.

---

# EQ-Creds v1.0.0 Release Notes

## 🎉 Initial Release

EQ-Creds is a secure, standalone credential vault for managing shared P99 EverQuest account logins and character data. Built with strong encryption, an intuitive Windows UI, and comprehensive safeguards for your guild's shared credentials.

---

## ✨ Features

### Core Vault Management
- **Master Password Protection**: Argon2id key derivation (3+ second iterations) for strong password strength
- **AES-256-GCM Encryption**: Military-grade encryption for all stored credentials
- **Account Organization**: Create, edit, and manage multiple shared accounts with rich metadata:
  - Account label, username, password
  - Account owner and who shared it
  - Status (Active/Inactive)
  - Role and rotation flags
  - Custom tags for organization
  - Notes field for context
- **Character Tracking**: Store character details per account:
  - Character name, class, level (1-60)
  - Character-specific notes
  - One-to-many relationship management

### Security
- **Session-Based Access**: Vault locked until master password unlocked; in-memory session key zeroed on app close
- **Atomic Re-keying**: Change master password safely with atomic database re-encryption
- **Authenticated Encryption**: AES-GCM prevents tampering; account UUID used as Additional Authenticated Data
- **Clean Vault Files**: No temporary sidecars (SQLite WAL disabled) for portable deployments
- **Auto-Lock**: Vault automatically locks when app closes

### User Experience
- **Dual Themes**: Dark (default) and Light themes with persistent user preference
- **Search Anywhere**: Live full-text search across account labels, character names, owners, and tags
- **One-Click Reveal**: Password reveal button with automatic 15-second hide timer
- **Rich UI**: Responsive account detail view with character table, credentials section, and notes
- **Windows Integration**: Proper taskbar behavior, application ID, and icon support

### Technical
- **Standalone Executable**: Single `EQCreds.exe` file (PyInstaller onefile)
- **Cross-Platform Source**: Python 3.9 + PySide6 (easily portable to Linux/macOS)
- **SQLite Database**: Lightweight, portable vault storage
- **Comprehensive Tests**: 27 unit tests covering crypto, database, and re-key operations

---

## 🔒 Security Model

**Encryption Architecture:**
- Each credential field encrypted individually with unique random nonce
- Account UUID bound to encrypted fields via AAD to prevent cross-account decryption
- 256-bit session key derived from master password using Argon2id KDF
- No client-side secrets stored; session key destroyed on app close

**Trust Assumptions:**
- Master password is the single trust anchor
- Anyone with `vault.db` + master password can access all credentials
- Assumes no malware on the system during vault use
- Not suitable for scenarios requiring separation of duty

**Best Practices:**
- Use a strong master password (20+ characters recommended)
- Change master password if access is suspected
- Keep `vault.db` backups secured
- Lock the app when stepping away

---

## 📦 Installation & Build

### Option 1: Run Pre-Built Executable
Download `EQCreds.exe` from the GitHub release and run directly. No installation required.

### Option 2: Build from Source

**Prerequisites:**
- Python 3.9+
- Git

**Steps:**
```bash
git clone https://github.com/yourusername/eq-creds.git
cd eq-creds
python -m venv .venv
.venv\Scripts\activate  # Windows

pip install -r requirements.txt
python -m pytest tests/  # Optional: run test suite (27 tests)

# Build executable
python -m pyinstaller build.spec
# EQCreds.exe will be in dist/
```

---

## 🎮 Usage

1. **First Launch**: Create a master password (minimum length enforced, no strength requirements)
2. **Main View**: Search and browse accounts; click an account to view details
3. **Add Account**: "+ New Account" button to create new account with characters
4. **Edit Account**: "Edit" button on detail view to modify credentials or characters
5. **Delete Account**: "Delete" button removes account and all associated characters
6. **Lock Vault**: Lock button closes session and clears memory
7. **Change Password**: Settings → "Change Master Password" (atomic re-encryption)
8. **Theme**: Settings → Appearance dropdown (Dark/Light, requires app restart in some cases)

---

## 📋 What's Tested

- ✅ Argon2id KDF key derivation
- ✅ AES-256-GCM encryption/decryption with nonce uniqueness
- ✅ Tamper detection (AAD validation)
- ✅ SQLite CRUD operations (create, read, update, delete)
- ✅ One-to-many character relationships
- ✅ Full-text search across all fields
- ✅ Cascading deletes (accounts → characters)
- ✅ Atomic master password re-key operation
- ✅ UI rendering (both themes)

All 27 tests passing on Python 3.9+.

---

## 📝 Known Limitations

- **No Import/Export**: Vault backups are manual `vault.db` copies
- **No Sharing**: Credentials must be entered manually per user
- **No Audit Log**: No record of who accessed what or when
- **Single User Per Vault**: Not designed for concurrent multi-user access
- **No Sync**: Vault is local-only; syncing across devices requires manual file copy
- **Windows Only (Binary)**: Executable is Windows-only, but source is portable Python

---

## 🐛 Known Issues

None reported at release. Please submit issues on GitHub.

---

## 🛣️ Roadmap (Future)

Potential features for future releases:
- Biometric unlock (Windows Hello integration)
- Vault import/export (encrypted backup format)
- Character rotation tracking and history
- Audit log with timestamps and user tracking
- Multi-user vaults with controlled access per credential
- Dark mode auto-detect based on Windows settings

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 🤝 Contributing

Report bugs or suggest features via GitHub Issues. Pull requests welcome for bug fixes and enhancements.

---

## ❓ FAQ

**Q: Is my password stored?**  
A: No. Your master password is never stored. A 256-byte session key derived from it is held in memory only during app use and cleared when the app closes.

**Q: What if I forget my master password?**  
A: All credentials are permanently encrypted. Forgotten password means permanent data loss. Use a password manager for the master password itself.

**Q: Can I backup my vault?**  
A: Yes. Copy `vault.db` to a secure location. Restore by replacing the vault file and unlocking with your master password. **Keep backups secure!**

**Q: Can multiple people use the same vault?**  
A: The vault is single-user per unlock session. Multiple people can share access by knowing the master password, but concurrent edits will conflict.

**Q: Is the source code audited?**  
A: No professional security audit has been performed. Use at your own discretion and review the source on GitHub.

---

## 📞 Support

For issues, questions, or feature requests, please open a GitHub Issue or contact the project maintainer.

---

**Release Date:** March 31, 2026  
**Version:** 1.0.0  
**Status:** Production Ready
