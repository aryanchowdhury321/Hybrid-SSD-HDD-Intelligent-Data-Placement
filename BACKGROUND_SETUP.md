# Background monitoring setup (Windows)

This adds a separate headless process that reuses the existing Watchdog monitors,
SQLite database, reconciliation, and tiering optimizer. The desktop GUI can be
opened only when you want to inspect the system.

## 1. Test manually first

1. Open this project folder in VS Code.
2. Check `config.py`: `LOCAL_SSD_PATH` and `LOCAL_SECONDARY_PATH` must be correct.
3. Open a terminal in this folder and activate your existing environment:
   `.\venv\Scripts\Activate.ps1`
   If this project folder does not contain `venv`, create one and run
   `pip install -r requirements.txt`.
4. Run `python background_monitor.py`.
5. Leave it running and edit/create a test file inside a configured managed folder.
6. Check `logs\background_monitor.log` and the console output for events.
7. Press Ctrl+C to stop it.
8. Do not run the GUI and background worker at the same time during the first test:
   both can start filesystem monitors and optimization loops, which may cause
   duplicate event handling or competing migrations.

## 2. Configure automatic start with Task Scheduler

Use a logon trigger first (more reliable for user-writable storage folders and
an external drive than a SYSTEM startup task).

1. Press Win+R, type `taskschd.msc`, press Enter.
2. Choose **Create Task** (not Basic Task).
3. General tab:
   - Name: `Hybrid Storage Background Monitor`
   - Select **Run only when user is logged on** for the initial setup.
   - Do not select **Run with highest privileges** unless testing proves it is needed.
4. Triggers tab → New:
   - Begin the task: **At log on**
   - Select your user account.
   - Optional: delay by 30 seconds to allow drives to mount.
5. Actions tab → New:
   - Action: **Start a program**
   - Program/script: the full path to `pythonw.exe` inside this project's venv,
     e.g. `D:\ProjectOS\venv\Scripts\pythonw.exe`
   - Add arguments: the full path to `background_monitor.py`, e.g.
     `"D:\ProjectOS\background_monitor.py"`
   - Start in: the project folder, e.g. `D:\ProjectOS`
   Replace `D:\ProjectOS` with your actual project location. Do not include quotes
   around the Start in folder path.
6. Conditions tab:
   - For a laptop, optionally uncheck “Start the task only if the computer is on AC power”
     if you want it to run on battery too.
   - Keep the network condition disabled; this project does not require internet.
7. Settings tab:
   - Enable “Allow task to be run on demand”.
   - If the task is already running, choose “Do not start a new instance”.
8. Save the task. If asked for credentials, use the option to run only when logged on.
9. Right-click the task → Run.
10. Check `logs\background_monitor.log` for “Background monitoring is running”.

If `venv\Scripts\pythonw.exe` is missing, use the full path to your installed
Python's `pythonw.exe`, but ensure the project's dependencies are installed in
that same Python environment.

## 3. Verify after restart

1. Restart Windows and log in.
2. Wait 30–60 seconds.
3. Check `logs\background_monitor.log` for a new startup timestamp.
4. Edit a test file in a configured managed folder.
5. Open the GUI and verify the file/access/migration state in the shared database.

## 4. Stop or disable it

- Task Scheduler → Task Scheduler Library → `Hybrid Storage Background Monitor`
  → right-click **End** to stop the current run.
- Right-click **Disable** to prevent it from starting at the next login.
- To stop it manually while running in a visible terminal, press Ctrl+C.

## Important limitations / safety

- This watches only the managed folders in `config.py`, not every file on the PC.
- Watchdog filesystem notifications are not the same as complete OS-level READ auditing.
  External file modifications and create/delete/rename events can be tracked; ordinary
  reads are not reliably detected by Watchdog.
- The secondary tier must be available for it to be monitored. This worker retries
  unavailable configured roots periodically.
- Do not run this worker and the GUI together for the initial tests. The GUI currently
  starts its own monitors and optimizer too. A later integration should add a single
  instance/ownership mechanism or change the GUI to attach to the background process.
- Do not run a second instance of the scheduled task; set Task Scheduler to “Do not
  start a new instance”.
- This is a user-mode background process, not a Windows Service. It starts at login,
  not before login. A proper Windows Service is a separate, more advanced step.
