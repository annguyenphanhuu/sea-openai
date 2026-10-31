# Task 01 controller research — 2026-10-31

Primary sources checked before state implementation:

- https://docs.python.org/3.11/library/sqlite3.html — executescript commits a pending transaction before running its script. Therefore bootstrap/migration must execute complete statements individually inside a controlled transaction, not executescript within BEGIN.
- https://www.sqlite.org/lang_transaction.html — BEGIN IMMEDIATE obtains a write transaction immediately and can return SQLITE_BUSY when another writer is active. Use bounded timeout and explicit rollback/error translation; test with separate connections to one real file.

These support transaction mechanics, not the project's business policy. Policy comes from the approved design plus latest user decisions. The fixed financial-key behavior after a blocked attempt is pending user choice and is outside Task 01.
