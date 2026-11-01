# Hybrid Storage Management System
### Hybrid SSD–HDD Intelligent Data Placement Framework

A Windows desktop application that implements dynamic storage tiering using a real internal SSD and an external secondary storage drive. The system monitors filesystem changes, maintains metadata and access history in SQLite, calculates logical data heat, and automatically migrates files between storage tiers according to their access patterns and available SSD capacity.

---

## Project Information

**Project Title:** Hybrid Storage Management System  
**Research Framework:** Hybrid SSD–HDD Intelligent Data Placement Framework  
**Project Type:** Operating Systems / Storage Management  
**Platform:** Windows  
**Faculty Guide:** Dr Ruby D

### Project Team

| S. No. | Team Member | Registration Number |
|---|---|---|
| 1 | Aryan Chowdhury | 24BCE0535 |
| 2 | Shubham Gupta | 24BCE2346 |
| 3 | Sudeep Mukherjee | 24BCE0525 |

---

## 1. Project Overview

Modern computer systems use different storage devices to balance performance, capacity, and cost. SSDs provide fast access but generally offer less capacity per unit cost than HDDs. HDDs provide larger, economical storage but have higher access latency.

The Hybrid Storage Management System implements an intelligent storage-tiering prototype that places frequently accessed data on the SSD and less frequently accessed data on secondary storage.

The system combines filesystem monitoring, logical data-heat estimation, automatic placement decisions, physical file migration, persistent database records, and a desktop dashboard.

## 2. Technology Stack

- **Programming Language:** Python
- **GUI Framework:** CustomTkinter
- **Database:** SQLite
- **Filesystem Monitoring:** Watchdog
- **Storage and System Information:** psutil
- **File Operations:** Python filesystem utilities
- **Background Execution:** Python worker with Windows Task Scheduler
- **Development Environment:** Visual Studio Code

## 3. Storage Architecture

The application uses two physically distinct managed storage locations.

| Storage Tier | Configured Location | Purpose |
|---|---|---|
| Primary SSD | `C:\HybridStorageSSD` | Stores hot and frequently accessed files |
| Secondary Storage | `E:\HybridStorageHDD` | Stores colder files and provides additional capacity |

The configured locations must exist and be accessible. The secondary drive should be connected whenever the application is expected to monitor or migrate files to it.

The storage locations are configurable in `config.py`, allowing the project to be adapted to another computer with different drive letters.

**Important:** These are managed folders on physical drives, not virtual storage devices. File migrations move actual files between the configured directories.

## 4. Key Features and Implemented Functionality

### 4.1 Dynamic Filesystem Monitoring

- Uses Watchdog to monitor both managed storage directories.
- Detects filesystem events such as file creation, modification, deletion, and movement.
- Handles common editor save patterns in which a temporary file is renamed over an existing file.
- Identifies migration-generated events to avoid treating the system's own file movements as new user activity.
- Records relevant filesystem activity in the background log.

Filesystem event detection is event-driven and does not depend on the optimizer's periodic execution interval.

### 4.2 Logical Data-Heat Estimation

The system maintains a logical heat score for each managed file based on recorded access activity.

- READ and WRITE events contribute weighted heat.
- Older access events contribute progressively less heat.
- Exponential time decay models the reduction in data activity over time.
- Updated heat values support dynamic storage-placement decisions.

The heat score represents estimated data activity; it is **not a physical temperature measured in Celsius**.

### 4.3 Hot, Warm, and Cold Classification

The current classification policy is:

| Classification | Logical Heat Score |
|---|---:|
| HOT | 70 or above |
| WARM | 40–69 |
| COLD | Below 40 |

Cold SSD data becomes eligible for demotion when its heat reaches the configured SSD demotion threshold of 25 or below.

### 4.4 Automatic Data Placement

The placement engine determines whether a managed file should remain on its current tier or move to another tier.

- Hot files on secondary storage are candidates for promotion to SSD.
- Cold files on SSD are candidates for demotion to secondary storage.
- Hysteresis reduces unnecessary back-and-forth migrations.
- Placement decisions use the current logical heat score and configured thresholds.

### 4.5 Capacity-Aware SSD Management

- Checks available SSD capacity before promoting files.
- Maintains a configurable minimum free-space reserve.
- Can demote eligible cold SSD files when additional space is required.
- Supports storage placement decisions that account for the size of files being migrated.

### 4.6 Physical File Migration

- Performs actual file movement between the configured SSD and secondary-storage directories.
- Verifies the destination file after migration.
- Records migration outcomes in the database.
- Includes safeguards for migration failures and physical-state reconciliation.
- Records migration reasons, including temperature-based promotion or demotion and capacity-related eviction.

### 4.7 SQLite Database Management

The application uses SQLite for persistent storage metadata and historical records.

The main database tables include:

- **`blocks`:** Logical block identifiers, filenames, sizes, current tiers, access counters, heat scores, and status.
- **`access_history`:** Recorded READ/WRITE activity with timestamps.
- **`migration_history`:** Source tier, destination tier, migration timestamp, heat at migration, and migration reason.

The database is stored locally at:

`data/hybrid_storage.db`

The database can be inspected using DB Browser for SQLite or SQL queries.

### 4.8 Startup Discovery and Database Reconciliation

- Discovers files physically present in the configured managed directories.
- Synchronizes discovered files with database metadata.
- Reconciles database records against the physical storage state during startup.
- Marks files absent from both successfully checked managed directories as deleted while retaining their historical records.
- Supports recovery and reconciliation after application or system restarts.

For a clean installation on another computer, a fresh local database can be created so that the application does not display stale records from another machine.

### 4.9 Headless Background Monitoring

The project includes `background_monitor.py`, which runs monitoring and optimization without opening the desktop GUI.

The background worker:

- Initializes the database and reconciles storage state.
- Starts filesystem monitors for the configured storage folders.
- Runs periodic optimization cycles.
- Attempts to restart monitors when a storage drive becomes available again.
- Records filesystem events, migrations, errors, and startup information.
- Stops its filesystem observers during a graceful shutdown.

### 4.10 Windows Automatic Startup

Windows Task Scheduler can launch the background worker automatically when the configured Windows user logs in.

The task runs the project's virtual-environment Python executable in windowless mode using `pythonw.exe`, so VS Code does not need to remain open.

The background worker can continue monitoring independently of the desktop GUI. Monitoring begins at the configured login trigger, not before Windows login.

### 4.11 Log Management and Optimization Scheduling

The background worker uses Python's rotating file handler to limit individual log-file size.

Current logging configuration:

- Maximum size per log file: 2 MB
- Backup files retained: 4
- Routine optimization summaries: approximately every five minutes, or when a cycle reports migrations
- Filesystem events, migration records, and errors: logged separately

The optimization interval is configurable through `OPTIMIZATION_INTERVAL_SECONDS` in `config.py`. A 60-second interval means the optimizer runs approximately once per minute, while filesystem events continue to be detected independently.

The five-minute summary interval controls routine logging; it does not control the frequency of filesystem monitoring.

### 4.12 Desktop Dashboard and Analytics

The CustomTkinter interface provides:

- Dashboard with storage and system status
- Storage Blocks view
- Migration History
- Live Access controls for controlled READ/WRITE workloads
- Optimization Analytics
- Logical heat and placement information
- Migration records and reasons

The GUI provides a convenient way to inspect the system's operation without manually querying the database.

## 5. System Architecture

The application follows a modular architecture:

1. **Filesystem and User Interaction Layer:** Monitors filesystem changes and accepts controlled workload operations.
2. **Access Monitoring Layer:** Records supported filesystem events and access activity.
3. **Data-Heat Layer:** Calculates logical heat using weighted, time-decaying activity.
4. **Placement Decision Layer:** Classifies files and determines their target storage tier.
5. **Tiering and Capacity Layer:** Coordinates optimization cycles and available SSD capacity.
6. **Migration Layer:** Moves files physically and records migration outcomes.
7. **Persistence Layer:** Stores metadata, access history, and migration history in SQLite.
8. **Presentation Layer:** Displays storage state, heat scores, activity, and analytics through the desktop GUI.
9. **Background Execution Layer:** Runs monitoring and optimization independently of the GUI.

## 6. Project Directory Structure

```text
ProjectOS/
├── app.py
├── background_monitor.py
├── config.py
├── database.py
├── system_diagnostics.py
├── requirements.txt
├── README.md
├── UPGRADE_NOTES.md
├── FIX_GUIDE.md
├── data/
│   └── hybrid_storage.db
├── engine/
│   ├── access_monitor.py
│   ├── migration_engine.py
│   ├── placement_engine.py
│   ├── storage_controller.py
│   ├── temperature_engine.py
│   └── tiering_engine.py
├── models/
│   ├── block.py
│   └── storage_tier.py
├── storage/
│   ├── device_manager.py
│   ├── device_monitor.py
│   ├── ssd_tier/
│   └── secondary_tier/
├── workload/
│   ├── generator.py
│   └── trace_loader.py
└── logs/
    └── background_monitor.log
```

The database, logs, virtual environment, and runtime-generated files may vary depending on the local installation.

## 7. Installation and Execution

### Prerequisites

- Windows 10 or Windows 11
- Python 3.12 or a compatible Python version
- A writable internal SSD managed directory
- An accessible secondary storage directory
- Required Python packages installed in the project virtual environment

### Step 1: Open the Project

Open the `ProjectOS` folder in Visual Studio Code.

### Step 2: Activate the Virtual Environment

In PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

If the virtual environment does not exist, create it and install the dependencies listed in `requirements.txt`.

### Step 3: Launch the Desktop Application

```powershell
python app.py
```

### Step 4: Run System Diagnostics

```powershell
python system_diagnostics.py
```

### Step 5: Run the Background Worker Manually

For debugging, the worker can be started in the terminal:

```powershell
python background_monitor.py
```

For automatic background operation, configure Windows Task Scheduler to launch `background_monitor.py` using the virtual environment's `pythonw.exe`.

**Avoid running multiple background workers simultaneously**, as duplicate workers may compete to monitor and optimize the same storage locations.

## 8. Configuration

Important settings are defined in `config.py`.

| Parameter | Current Value | Purpose |
|---|---|---|
| `LOCAL_SSD_PATH` | `C:\HybridStorageSSD` | Managed SSD directory |
| `LOCAL_SECONDARY_PATH` | `E:\HybridStorageHDD` | Managed secondary directory |
| `HOT_THRESHOLD` | 70 | Threshold for HOT classification |
| `WARM_THRESHOLD` | 40 | Lower boundary of WARM classification |
| `SSD_DEMOTION_THRESHOLD` | 25 | SSD demotion eligibility threshold |
| `HEAT_HALF_LIFE_SECONDS` | 600 | Ten-minute heat half-life |
| `OPTIMIZATION_INTERVAL_SECONDS` | 60, if configured | Periodic optimizer interval |
| `SSD_MIN_FREE_MB` | 512, if configured | Minimum SSD free-space reserve |

Check the actual values in `config.py` before reproducing experiments, as settings may be changed during testing.

## 9. Important Research Limitation

Watchdog primarily detects filesystem changes, such as CREATE, MODIFY, DELETE, and MOVE events. It **does not capture every ordinary Windows file READ operation**.

The GUI's READ/WRITE controls generate controlled workload events for testing and demonstration. These events should not be represented as comprehensive operating-system-level read telemetry.

Genuine Windows READ auditing requires a separate OS-level instrumentation or auditing mechanism, which must be configured and verified independently.

Accordingly, the current implementation demonstrates dynamic heat-based placement using recorded and controlled activity rather than complete observation of every file access performed by Windows applications.

## 10. Testing and Verification

The following tests can be used to evaluate the system:

1. Verify that both configured storage directories are accessible.
2. Create a test file inside a managed directory.
3. Modify and save the file using an external editor such as Notepad.
4. Verify that the filesystem event appears in the background log.
5. Inspect the corresponding database record and logical heat score.
6. Generate controlled READ/WRITE activity through the GUI.
7. Verify that the heat score changes as activity is recorded and decays over time.
8. Verify that a hot secondary file can be promoted to SSD when placement conditions are satisfied.
9. Verify that an eligible cold SSD file can be demoted to secondary storage.
10. Inspect Migration History for source, destination, heat, timestamp, and reason.
11. Restart the application and verify physical-state reconciliation.
12. Test automatic background startup after Windows login.
13. Verify that the log rotates when its configured size limit is reached.

Perform migration tests only with disposable test files and ensure important files are backed up.

## 11. Current Scope and Future Enhancements

Potential future improvements include:

- Verified Windows-level file-read telemetry.
- Predictive data placement using workload forecasting.
- Migration-cost and latency-aware optimization.
- More comprehensive performance benchmarking against fixed-tier placement.
- Improved visualization of access patterns, heat decay, and migration decisions.
- Enhanced handling of unavailable drives and recovery failures.
- Packaging as a Windows background service.
- More detailed storage-performance measurements using representative workloads.

These items are future enhancements unless implemented and verified in the current source code.

## 12. Conclusion

The Hybrid Storage Management System demonstrates a modular approach to SSD–HDD storage tiering on Windows. It combines filesystem monitoring, logical data-heat estimation, threshold-based placement, capacity-aware migration, SQLite persistence, startup reconciliation, and a desktop dashboard.

Its headless background worker supports monitoring and periodic optimization independently of the GUI, while Windows Task Scheduler enables automatic startup at user login.

The prototype provides a foundation for studying dynamic storage placement and can be extended with more advanced telemetry, predictive policies, and systematic performance evaluation.

---

**Project Team**

Aryan Chowdhury — 24BCE0535  
Shubham Gupta — 24BCE2346  
Sudeep Mukherjee — 24BCE0525  

**Faculty Guide:** 
Dr Ruby D
