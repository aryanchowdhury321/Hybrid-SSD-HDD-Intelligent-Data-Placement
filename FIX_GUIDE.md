# Step-by-step: Verify the storage fixes

## Before changing anything
1. Close the application.
2. Copy `data/hybrid_storage.db` to a safe backup outside this project.
3. Keep the external drive connected during the test.

## Apply the updated project
1. Extract this project to a new folder, for example `HybridStorageProject_Fixed`.
2. Open `config.py`.
3. Confirm `LOCAL_SSD_PATH` points to the SSD-managed folder on this PC.
4. Confirm `LOCAL_SECONDARY_PATH` points to the secondary drive's managed folder. If the drive letter differs, change it here.
5. Install dependencies in your own virtual environment:
   `pip install -r requirements.txt`
6. Run from the project root:
   `python app.py`

## Test 1 — external edit should update heat
1. In the app, confirm the file is listed under Storage Blocks and note its block ID and temperature.
2. Open the *physical file inside* `C:\HybridStorageSSD` or `E:\HybridStorageHDD` in Notepad.
3. Add a line and save. If using an editor that replaces files atomically, the app now handles the resulting MOVED event as a WRITE.
4. Check the terminal and Live Access / Storage Blocks for WRITE and a recalculated temperature.
5. Repeat several saves. A single WRITE adds 22.5 heat points before decay with the current settings; one write does not necessarily make a file HOT (threshold 70).

Important: edit a file inside the configured managed roots, not a copy elsewhere on the PC. Watchdog is not a system-wide monitor.

## Test 2 — stale database records on another PC
1. Confirm both configured managed roots are correct. If a root is unavailable, records whose files cannot currently be found are hidden as OFFLINE rather than shown as active.
2. Start the app. It reconciles database rows with physical files, then scans the managed roots.
3. Storage Blocks and dashboard counts should include only ACTIVE records for files discovered in the configured folders.
4. If both roots are available and a database file has no matching physical file in either root, its status becomes DELETED (history is retained).
5. If a tier drive was disconnected, reconnect it; the monitor recovery path rescans the tier and can reactivate blocks whose files are found.

## What was changed
- MOVED events caused by editor save/replace are treated as WRITE when the destination is a registered managed file.
- Modified/moved/deleted file lookups use both filename and tier to reduce wrong-block matches.
- Startup reconciliation marks files absent from both available roots as DELETED; when a root is unavailable, missing files are hidden as OFFLINE rather than being treated as confirmed deletions.
- When a storage root reconnects, its contents are rescanned.

## If you need a completely clean database on a second PC
Back up the database, close the app, and rename `data/hybrid_storage.db` to `hybrid_storage_backup.db`. Run the app again; it will create a fresh database and register only files found in the configured managed folders. Do not delete your only copy of the old DB.
