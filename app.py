import customtkinter as ctk
import queue
import os
import threading
from datetime import datetime

from storage.device_manager import (
    get_drive_info,
    is_drive_available
)

from storage.device_monitor import (
    start_monitor,
    handle_storage_event
)

from config import (
    LOCAL_SSD_PATH,
    LOCAL_SECONDARY_PATH
)

from database import (
    initialize_database,
    get_system_statistics,
    get_all_blocks,
    get_migration_history,
    discover_managed_files
)

from engine.temperature_engine import (
    get_temperature_label
)

from engine.storage_controller import (
    process_access
)
from engine.migration_engine import (
    is_internal_migration,
    reconcile_physical_state
)

from engine.tiering_engine import (
    run_optimization_cycle
)


# ============================================================
# CUSTOMTKINTER SETTINGS
# ============================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ============================================================
# MAIN APPLICATION
# ============================================================

class HybridStorageApp(ctk.CTk):

    def __init__(self):

        super().__init__()

        # ----------------------------------------------------
        # DATABASE
        # ----------------------------------------------------

        initialize_database()
        repaired = reconcile_physical_state()
        if repaired:
            print(f"Reconciled physical tier state for {len(repaired)} block(s).")

        discovered = discover_managed_files([
            ("SSD", LOCAL_SSD_PATH),
            ("SECONDARY", LOCAL_SECONDARY_PATH),
        ])
        if discovered:
            print(f"Startup scan synchronized {len(discovered)} managed file(s).")

        # ----------------------------------------------------
        # WINDOW
        # ----------------------------------------------------

        self.title(
            "Hybrid Storage Management System"
        )

        self.geometry("1200x750")

        self.minsize(
            1000,
            650
        )

        # ----------------------------------------------------
        # LIVE MONITORING VARIABLES
        # ----------------------------------------------------

        self.event_queue = queue.Queue()

        self.live_events = []
        self.current_view = "dashboard"
        self.optimizer_stop_event = threading.Event()

        # ----------------------------------------------------
        # START REAL FILESYSTEM MONITORS FOR BOTH TIERS
        # ----------------------------------------------------

        self.secondary_monitor = start_monitor(
            LOCAL_SECONDARY_PATH,
            self.handle_monitor_event
        )

        self.ssd_monitor = start_monitor(
            LOCAL_SSD_PATH,
            self.handle_monitor_event
        )

        # Backward-compatible alias.
        self.monitor = self.secondary_monitor

        # ----------------------------------------------------
        # START AUTOMATIC TIER OPTIMIZER
        # ----------------------------------------------------

        self.optimizer_thread = threading.Thread(
            target=self.optimization_worker,
            daemon=True
        )
        self.optimizer_thread.start()

        # ----------------------------------------------------
        # CHECK FOR MONITOR EVENTS
        # ----------------------------------------------------

        self.after(
            500,
            self.process_live_events
        )

        self.after(
            5000,
            self.refresh_current_view
        )

        self.after(
            5000,
            self.monitor_health_check
        )

        # ----------------------------------------------------
        # CREATE GUI
        # ----------------------------------------------------

        self.create_sidebar()

        self.create_main_frame()

        self.show_dashboard()

        # ----------------------------------------------------
        # SAFE APPLICATION CLOSE
        # ----------------------------------------------------

        self.protocol(
            "WM_DELETE_WINDOW",
            self.close_application
        )


    # ========================================================
    # SIDEBAR
    # ========================================================

    def create_sidebar(self):

        self.sidebar = ctk.CTkFrame(
            self,
            width=220,
            corner_radius=0
        )

        self.sidebar.pack(
            side="left",
            fill="y"
        )

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        title = ctk.CTkLabel(
            self.sidebar,
            text="HYBRID\nSTORAGE",
            font=ctk.CTkFont(
                size=24,
                weight="bold"
            )
        )

        title.pack(
            pady=(30, 40)
        )

        # ----------------------------------------------------
        # DASHBOARD BUTTON
        # ----------------------------------------------------

        dashboard_button = ctk.CTkButton(
            self.sidebar,
            text="Dashboard",
            height=45,
            command=self.show_dashboard
        )

        dashboard_button.pack(
            padx=20,
            pady=10,
            fill="x"
        )

        # ----------------------------------------------------
        # STORAGE BLOCKS BUTTON
        # ----------------------------------------------------

        blocks_button = ctk.CTkButton(
            self.sidebar,
            text="Storage Blocks",
            height=45,
            command=self.show_blocks
        )

        blocks_button.pack(
            padx=20,
            pady=10,
            fill="x"
        )

        # ----------------------------------------------------
        # MIGRATION HISTORY BUTTON
        # ----------------------------------------------------

        migration_button = ctk.CTkButton(
            self.sidebar,
            text="Migration History",
            height=45,
            command=self.show_migration_history
        )

        migration_button.pack(
            padx=20,
            pady=10,
            fill="x"
        )

        # ----------------------------------------------------
        # LIVE ACCESS BUTTON
        # ----------------------------------------------------

        access_button = ctk.CTkButton(
            self.sidebar,
            text="Live Access",
            height=45,
            command=self.show_live_access
        )

        access_button.pack(
            padx=20,
            pady=10,
            fill="x"
        )

        analytics_button = ctk.CTkButton(
            self.sidebar,
            text="Optimization Analytics",
            height=45,
            command=self.show_analytics
        )

        analytics_button.pack(
            padx=20,
            pady=10,
            fill="x"
        )


    # ========================================================
    # MAIN FRAME
    # ========================================================

    def create_main_frame(self):

        self.main_frame = ctk.CTkFrame(
            self,
            corner_radius=0
        )

        self.main_frame.pack(
            side="right",
            fill="both",
            expand=True
        )


    # ========================================================
    # CLEAR MAIN FRAME
    # ========================================================

    def clear_main_frame(self):

        for widget in self.main_frame.winfo_children():

            widget.destroy()


    # ========================================================
    # WATCHDOG CALLBACK
    # ========================================================

    def handle_monitor_event(
        self,
        event_type,
        file_path,
        old_path=None
    ):

        event_data = {
            "event": event_type,
            "file": file_path,
            "old_path": old_path,
            "time": datetime.now().strftime(
                "%H:%M:%S"
            )
        }

        # Watchdog works in another thread.
        # Put event into a thread-safe queue.
        self.event_queue.put(
            event_data
        )


    # ========================================================
    # PROCESS LIVE EVENTS
    # ========================================================

    def process_live_events(self):

        while not self.event_queue.empty():

            event_data = self.event_queue.get()

            event_type = event_data["event"]

            file_path = event_data["file"]

            old_path = event_data["old_path"]

            event_time = event_data["time"]

            # ------------------------------------------------
            # BACKGROUND OPTIMIZATION EVENT
            # ------------------------------------------------

            if event_type == "OPTIMIZATION":

                display_text = (
                    f"{event_time}  |  OPTIMIZE | "
                    f"{file_path} | "
                    f"{event_data.get('message', '')}"
                )

                self.live_events.insert(0, display_text)
                self.live_events = self.live_events[:50]
                continue


            # ------------------------------------------------
            # INTERNAL MIGRATION EVENT
            # ------------------------------------------------

            if is_internal_migration(file_path):
                continue


            # ------------------------------------------------
            # SEND EVENT TO STORAGE ENGINE
            # ------------------------------------------------

            try:

                if old_path is not None:

                    handle_storage_event(
                        event_type,
                        file_path,
                        old_path
                    )

                else:

                    handle_storage_event(
                        event_type,
                        file_path
                    )

            except Exception as error:

                print(
                    f"Live engine error: {error}"
                )


            # ------------------------------------------------
            # GET FILE NAME
            # ------------------------------------------------

            filename = os.path.basename(
                file_path
            )


            # ------------------------------------------------
            # FORMAT RENAME EVENT
            # ------------------------------------------------

            if (
                event_type == "MOVED"
                and old_path is not None
            ):

                old_filename = os.path.basename(
                    old_path
                )

                display_text = (
                    f"{event_time}  |  "
                    f"RENAME   |  "
                    f"{old_filename} -> "
                    f"{filename}"
                )


            else:

                display_text = (
                    f"{event_time}  |  "
                    f"{event_type:<8} |  "
                    f"{filename}"
                )


            # ------------------------------------------------
            # ADD TO ACTIVITY LOG
            # ------------------------------------------------

            self.live_events.insert(
                0,
                display_text
            )

            self.live_events = (
                self.live_events[:50]
            )


        # ----------------------------------------------------
        # UPDATE GUI SAFELY
        # ----------------------------------------------------

        if hasattr(
            self,
            "activity_textbox"
        ):

            try:

                if self.activity_textbox.winfo_exists():

                    self.update_activity_display()

            except Exception:

                pass


        # ----------------------------------------------------
        # CHECK AGAIN
        # ----------------------------------------------------

        self.after(
            500,
            self.process_live_events
        )

    # ========================================================
    # BACKGROUND OPTIMIZATION
    # ========================================================

    def optimization_worker(self):

        from config import OPTIMIZATION_INTERVAL_SECONDS

        while not self.optimizer_stop_event.wait(
            OPTIMIZATION_INTERVAL_SECONDS
        ):

            try:
                result = run_optimization_cycle()

                for migration in result.get("migrations", []):
                    self.event_queue.put({
                        "event": "OPTIMIZATION",
                        "file": migration["block_id"],
                        "old_path": None,
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "message": migration["message"]
                    })

            except Exception as error:
                print(f"Optimization worker error: {error}")


    def refresh_current_view(self):

        try:
            if self.current_view == "dashboard":
                self.show_dashboard()
            elif self.current_view == "blocks":
                self.show_blocks()
            elif self.current_view == "migration_history":
                self.show_migration_history()
            elif self.current_view == "analytics":
                self.show_analytics()
        except Exception as error:
            print(f"GUI refresh error: {error}")

        self.after(5000, self.refresh_current_view)


    def monitor_health_check(self):

        monitors = [
            (getattr(self, "secondary_monitor", None), LOCAL_SECONDARY_PATH),
            (getattr(self, "ssd_monitor", None), LOCAL_SSD_PATH),
        ]

        for monitor, path in monitors:
            if monitor is None:
                continue

            available = os.path.exists(path)

            try:
                if not available and monitor.running:
                    monitor.stop()
                elif available and not monitor.is_healthy():
                    if monitor.running:
                        monitor.stop()
                    monitor.start()
                    # Re-scan a tier when it becomes available again so blocks
                    # previously marked OFFLINE can be reactivated.
                    try:
                        from database import discover_managed_files
                        discover_managed_files([( "SSD" if path == LOCAL_SSD_PATH else "SECONDARY", path )])
                    except Exception as error:
                        print(f"Storage rescan error for {path}: {error}")
            except Exception as error:
                print(f"Monitor recovery error for {path}: {error}")

        self.after(5000, self.monitor_health_check)


    # ========================================================
    # DASHBOARD
    # ========================================================

    def show_dashboard(self):

        self.current_view = "dashboard"

        self.clear_main_frame()

        # ----------------------------------------------------
        # HEADING
        # ----------------------------------------------------

        heading = ctk.CTkLabel(
            self.main_frame,
            text="Hybrid Storage Management Dashboard",
            font=ctk.CTkFont(
                size=30,
                weight="bold"
            )
        )

        heading.pack(
            anchor="w",
            padx=35,
            pady=(30, 5)
        )

        # ----------------------------------------------------
        # SUBTITLE
        # ----------------------------------------------------

        subtitle = ctk.CTkLabel(
            self.main_frame,
            text=(
                "Intelligent Hot and Cold Data "
                "Placement System"
            ),
            font=ctk.CTkFont(
                size=16
            )
        )

        subtitle.pack(
            anchor="w",
            padx=35,
            pady=(0, 30)
        )

        # ----------------------------------------------------
        # STATISTICS
        # ----------------------------------------------------

        statistics = get_system_statistics()

        cards_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="transparent"
        )

        cards_frame.pack(
            fill="x",
            padx=35,
            pady=10
        )

        for column in range(4):

            cards_frame.grid_columnconfigure(
                column,
                weight=1
            )

        self.create_stat_card(
            cards_frame,
            "TOTAL BLOCKS",
            statistics["total_blocks"],
            0
        )

        self.create_stat_card(
            cards_frame,
            "SSD BLOCKS",
            statistics["ssd_blocks"],
            1
        )

        self.create_stat_card(
            cards_frame,
            "SECONDARY BLOCKS",
            statistics["secondary_blocks"],
            2
        )

        self.create_stat_card(
            cards_frame,
            "HOT BLOCKS",
            statistics["hot_blocks"],
            3
        )

        # ----------------------------------------------------
        # PHYSICAL STORAGE STATUS
        # ----------------------------------------------------

        drive_frame = ctk.CTkFrame(
            self.main_frame
        )

        drive_frame.pack(
            fill="x",
            padx=35,
            pady=(30, 10)
        )

        drive_heading = ctk.CTkLabel(
            drive_frame,
            text="PHYSICAL STORAGE STATUS",
            font=ctk.CTkFont(
                size=16,
                weight="bold"
            )
        )

        drive_heading.pack(
            anchor="w",
            padx=20,
            pady=(15, 5)
        )

        # ----------------------------------------------------
        # SSD INFORMATION
        # ----------------------------------------------------

        ssd_info = get_drive_info(
            LOCAL_SSD_PATH
        )

        if ssd_info:

            ssd_text = (
                f"SSD  |  {LOCAL_SSD_PATH}  |  "
                f"{ssd_info['used_gb']} GB used / "
                f"{ssd_info['total_gb']} GB"
            )

        else:

            ssd_text = (
                f"SSD  |  {LOCAL_SSD_PATH}  |  "
                "Unavailable"
            )

        # ----------------------------------------------------
        # SECONDARY INFORMATION
        # ----------------------------------------------------

        secondary_info = get_drive_info(
            LOCAL_SECONDARY_PATH
        )

        if secondary_info:

            secondary_text = (
                f"HDD  |  {LOCAL_SECONDARY_PATH}  |  "
                f"{secondary_info['used_gb']} GB used / "
                f"{secondary_info['total_gb']} GB"
            )

        else:

            secondary_text = (
                f"HDD  |  {LOCAL_SECONDARY_PATH}  |  "
                "Unavailable"
            )

        # ----------------------------------------------------
        # DISPLAY SSD
        # ----------------------------------------------------

        ctk.CTkLabel(
            drive_frame,
            text=ssd_text,
            font=ctk.CTkFont(
                size=14
            )
        ).pack(
            anchor="w",
            padx=20,
            pady=5
        )

        # ----------------------------------------------------
        # DISPLAY HDD
        # ----------------------------------------------------

        ctk.CTkLabel(
            drive_frame,
            text=secondary_text,
            font=ctk.CTkFont(
                size=14
            )
        ).pack(
            anchor="w",
            padx=20,
            pady=(5, 15)
        )

        # ----------------------------------------------------
        # SYSTEM STATUS
        # ----------------------------------------------------

        status_frame = ctk.CTkFrame(
            self.main_frame
        )

        status_frame.pack(
            fill="x",
            padx=35,
            pady=(15, 10)
        )

        ssd_status = "ONLINE" if is_drive_available(LOCAL_SSD_PATH) else "OFFLINE"
        secondary_status = "ONLINE" if is_drive_available(LOCAL_SECONDARY_PATH) else "OFFLINE"

        status_label = ctk.CTkLabel(
            status_frame,
            text=(
                "● SYSTEM STATUS: RUNNING\n"
                f"SSD: {ssd_status}    |    SECONDARY: {secondary_status}\n"
                "Automatic temperature optimization: ACTIVE"
            ),
            justify="left",
            font=ctk.CTkFont(
                size=16,
                weight="bold"
            )
        )

        status_label.pack(
            anchor="w",
            padx=20,
            pady=15
        )

        # ----------------------------------------------------
        # INFORMATION
        # ----------------------------------------------------

        info_label = ctk.CTkLabel(
            self.main_frame,
            text=(
                "Hybrid storage engine is active.\n"
                "Live filesystem monitoring is enabled.\n"
                "Monitoring real storage placement "
                "and file activity."
            ),
            justify="left",
            font=ctk.CTkFont(
                size=15
            )
        )

        info_label.pack(
            anchor="w",
            padx=35,
            pady=20
        )


    # ========================================================
    # STAT CARD
    # ========================================================

    def create_stat_card(
        self,
        parent,
        title,
        value,
        column
    ):

        card = ctk.CTkFrame(
            parent,
            height=130
        )

        card.grid(
            row=0,
            column=column,
            padx=8,
            pady=5,
            sticky="ew"
        )

        # ----------------------------------------------------
        # CARD TITLE
        # ----------------------------------------------------

        title_label = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(
                size=13,
                weight="bold"
            )
        )

        title_label.pack(
            pady=(20, 5)
        )

        # ----------------------------------------------------
        # CARD VALUE
        # ----------------------------------------------------

        value_label = ctk.CTkLabel(
            card,
            text=str(value),
            font=ctk.CTkFont(
                size=36,
                weight="bold"
            )
        )

        value_label.pack(
            pady=(0, 15)
        )


    # ========================================================
    # STORAGE BLOCKS
    # ========================================================

    def show_blocks(self):

        self.current_view = "blocks"
        self.clear_main_frame()

        # ----------------------------------------------------
        # HEADING
        # ----------------------------------------------------

        heading = ctk.CTkLabel(
            self.main_frame,
            text="Storage Blocks",
            font=ctk.CTkFont(
                size=30,
                weight="bold"
            )
        )

        heading.pack(
            anchor="w",
            padx=35,
            pady=(30, 5)
        )

        # ----------------------------------------------------
        # SUBTITLE
        # ----------------------------------------------------

        subtitle = ctk.CTkLabel(
            self.main_frame,
            text=(
                "Real-time monitoring of managed "
                "files and storage placement"
            ),
            font=ctk.CTkFont(
                size=15
            )
        )

        subtitle.pack(
            anchor="w",
            padx=35,
            pady=(0, 20)
        )

        # ----------------------------------------------------
        # TABLE
        # ----------------------------------------------------

        table_frame = ctk.CTkScrollableFrame(
            self.main_frame
        )

        table_frame.pack(
            fill="both",
            expand=True,
            padx=35,
            pady=(10, 30)
        )

        headers = [
            "Block ID",
            "File Name",
            "Size (KB)",
            "Accesses",
            "Reads",
            "Writes",
            "Temperature",
            "Status",
            "Current Tier",
            "Migrations",
            "State"
        ]

        # ----------------------------------------------------
        # TABLE HEADERS
        # ----------------------------------------------------

        for column, header in enumerate(
            headers
        ):

            label = ctk.CTkLabel(
                table_frame,
                text=header,
                font=ctk.CTkFont(
                    size=13,
                    weight="bold"
                )
            )

            label.grid(
                row=0,
                column=column,
                padx=10,
                pady=12,
                sticky="w"
            )

        # ----------------------------------------------------
        # GET BLOCKS
        # ----------------------------------------------------

        blocks = get_all_blocks()

        # ----------------------------------------------------
        # DISPLAY BLOCKS
        # ----------------------------------------------------

        for row, block in enumerate(
            blocks,
            start=1
        ):

            block_id = block[0]

            filename = block[1]

            size_kb = block[2]

            current_tier = block[3]

            access_count = block[4]

            read_count = block[5]

            write_count = block[6]

            temperature = block[8]

            migration_count = block[9]
            state = block[10] if len(block) > 10 else "ACTIVE"

            status = get_temperature_label(
                temperature
            )

            values = [
                block_id,
                filename,
                str(size_kb),
                str(access_count),
                str(read_count),
                str(write_count),
                str(temperature),
                status,
                current_tier,
                str(migration_count),
                state
            ]

            for column, value in enumerate(
                values
            ):

                label = ctk.CTkLabel(
                    table_frame,
                    text=value,
                    font=ctk.CTkFont(
                        size=13
                    )
                )

                label.grid(
                    row=row,
                    column=column,
                    padx=10,
                    pady=10,
                    sticky="w"
                )


    # ========================================================
    # MIGRATION HISTORY
    # ========================================================

    def show_migration_history(self):

        self.current_view = "migration_history"
        self.clear_main_frame()

        # ----------------------------------------------------
        # HEADING
        # ----------------------------------------------------

        heading = ctk.CTkLabel(
            self.main_frame,
            text="Migration History",
            font=ctk.CTkFont(
                size=30,
                weight="bold"
            )
        )

        heading.pack(
            anchor="w",
            padx=35,
            pady=(30, 10)
        )

        # ----------------------------------------------------
        # SUBTITLE
        # ----------------------------------------------------

        subtitle = ctk.CTkLabel(
            self.main_frame,
            text=(
                "Real migration activity recorded "
                "by the hybrid storage engine"
            ),
            font=ctk.CTkFont(
                size=16
            )
        )

        subtitle.pack(
            anchor="w",
            padx=35,
            pady=(0, 20)
        )

        # ----------------------------------------------------
        # GET MIGRATION HISTORY
        # ----------------------------------------------------

        migrations = get_migration_history()

        # ----------------------------------------------------
        # NO MIGRATIONS
        # ----------------------------------------------------

        if not migrations:

            no_data = ctk.CTkLabel(
                self.main_frame,
                text="No migrations have occurred yet.",
                font=ctk.CTkFont(
                    size=18
                )
            )

            no_data.pack(
                pady=50
            )

            return

        # ----------------------------------------------------
        # TABLE
        # ----------------------------------------------------

        table_frame = ctk.CTkScrollableFrame(
            self.main_frame,
            corner_radius=10
        )

        table_frame.pack(
            fill="both",
            expand=True,
            padx=35,
            pady=10
        )

        headers = [
            "Block ID",
            "Source Tier",
            "Destination Tier",
            "Temperature",
            "Reason",
            "Timestamp"
        ]

        # ----------------------------------------------------
        # TABLE HEADERS
        # ----------------------------------------------------

        for column, header in enumerate(
            headers
        ):

            label = ctk.CTkLabel(
                table_frame,
                text=header,
                font=ctk.CTkFont(
                    size=15,
                    weight="bold"
                )
            )

            label.grid(
                row=0,
                column=column,
                padx=20,
                pady=15,
                sticky="w"
            )

        # ----------------------------------------------------
        # TABLE DATA
        # ----------------------------------------------------

        for row, migration in enumerate(
            migrations,
            start=1
        ):

            for column, value in enumerate(
                migration
            ):

                label = ctk.CTkLabel(
                    table_frame,
                    text=str(value),
                    font=ctk.CTkFont(
                        size=14
                    )
                )

                label.grid(
                    row=row,
                    column=column,
                    padx=20,
                    pady=12,
                    sticky="w"
                )


    # ========================================================
    # OPTIMIZATION ANALYTICS
    # ========================================================

    def show_analytics(self):

        self.current_view = "analytics"
        self.clear_main_frame()

        heading = ctk.CTkLabel(
            self.main_frame,
            text="Optimization Analytics",
            font=ctk.CTkFont(size=30, weight="bold")
        )
        heading.pack(anchor="w", padx=35, pady=(30, 5))

        subtitle = ctk.CTkLabel(
            self.main_frame,
            text="Research-oriented metrics from the real hybrid storage engine",
            font=ctk.CTkFont(size=15)
        )
        subtitle.pack(anchor="w", padx=35, pady=(0, 25))

        statistics = get_system_statistics()
        ssd_info = get_drive_info(LOCAL_SSD_PATH)
        secondary_info = get_drive_info(LOCAL_SECONDARY_PATH)

        metrics_frame = ctk.CTkScrollableFrame(self.main_frame)
        metrics_frame.pack(fill="both", expand=True, padx=35, pady=10)

        metrics = [
            ("Total Active Blocks", statistics["total_blocks"]),
            ("SSD Blocks", statistics["ssd_blocks"]),
            ("Secondary Blocks", statistics["secondary_blocks"]),
            ("HOT Blocks", statistics["hot_blocks"]),
            ("WARM Blocks", statistics["warm_blocks"]),
            ("COLD Blocks", statistics["cold_blocks"]),
            ("SSD Promotions", statistics["promotions"]),
            ("HDD Demotions", statistics["demotions"]),
            ("Total Migrations", statistics["total_migrations"]),
            ("Average Data Heat", statistics["average_temperature"]),
        ]

        for index, (name, value) in enumerate(metrics):
            row = index // 3
            column = index % 3
            card = ctk.CTkFrame(metrics_frame, height=100)
            card.grid(row=row, column=column, padx=8, pady=8, sticky="ew")
            metrics_frame.grid_columnconfigure(column, weight=1)
            ctk.CTkLabel(
                card, text=name, font=ctk.CTkFont(size=13, weight="bold")
            ).pack(pady=(15, 3))
            ctk.CTkLabel(
                card, text=str(value), font=ctk.CTkFont(size=28, weight="bold")
            ).pack(pady=(0, 12))

        capacity_text = "Physical capacity status unavailable."
        if ssd_info and secondary_info:
            capacity_text = (
                f"SSD: {ssd_info['free_gb']} GB free ({ssd_info['used_percentage']}% used)\n"
                f"Secondary: {secondary_info['free_gb']} GB free ({secondary_info['used_percentage']}% used)\n"
                "Placement decisions use actual free SSD capacity and maintain a safety reserve."
            )

        ctk.CTkLabel(
            metrics_frame, text=capacity_text, justify="left",
            font=ctk.CTkFont(size=15)
        ).grid(row=3, column=0, columnspan=3, padx=10, pady=25, sticky="w")

        policy_text = (
            "Policy: HOT >= 70 promotes Secondary -> SSD. "
            "SSD data is demoted only at <= 25. "
            "Heat uses exponential time decay with a 10-minute half-life."
        )
        ctk.CTkLabel(
            metrics_frame, text=policy_text, justify="left", wraplength=850,
            font=ctk.CTkFont(size=14)
        ).grid(row=4, column=0, columnspan=3, padx=10, pady=10, sticky="w")


    # ========================================================
    # LIVE ACCESS
    # ========================================================

    def show_live_access(self):

        self.current_view = "live_access"
        self.clear_main_frame()

        # ----------------------------------------------------
        # HEADING
        # ----------------------------------------------------

        heading = ctk.CTkLabel(
            self.main_frame,
            text="Live Storage Activity",
            font=ctk.CTkFont(
                size=30,
                weight="bold"
            )
        )

        heading.pack(
            anchor="w",
            padx=35,
            pady=(30, 5)
        )

        # ----------------------------------------------------
        # SUBTITLE
        # ----------------------------------------------------

        subtitle = ctk.CTkLabel(
            self.main_frame,
            text=(
                "Automatic filesystem monitoring and "
                "manual block access"
            ),
            font=ctk.CTkFont(
                size=16
            )
        )

        subtitle.pack(
            anchor="w",
            padx=35,
            pady=(0, 20)
        )

        # ----------------------------------------------------
        # MONITOR STATUS
        # ----------------------------------------------------

        monitor_frame = ctk.CTkFrame(
            self.main_frame
        )

        monitor_frame.pack(
            fill="x",
            padx=35,
            pady=10
        )

        monitor_label = ctk.CTkLabel(
            monitor_frame,
            text=(
                "● LIVE MONITORING ACTIVE\n"
                f"SSD: {LOCAL_SSD_PATH}\n"
                f"SECONDARY: {LOCAL_SECONDARY_PATH}"
            ),
            justify="left",
            font=ctk.CTkFont(
                size=15,
                weight="bold"
            )
        )

        monitor_label.pack(
            anchor="w",
            padx=20,
            pady=15
        )

        # ----------------------------------------------------
        # MANUAL ACCESS CONTROL
        # ----------------------------------------------------

        control_frame = ctk.CTkFrame(
            self.main_frame,
            corner_radius=10
        )

        control_frame.pack(
            fill="x",
            padx=35,
            pady=10
        )

        # ----------------------------------------------------
        # BLOCK LABEL
        # ----------------------------------------------------

        block_label = ctk.CTkLabel(
            control_frame,
            text="Select File / Block:",
            font=ctk.CTkFont(
                size=16
            )
        )

        block_label.pack(
            side="left",
            padx=(25, 10),
            pady=20
        )

        # ----------------------------------------------------
        # GET BLOCKS DYNAMICALLY
        # ----------------------------------------------------

        blocks = get_all_blocks()

        block_mapping = {}

        for block in blocks:

            block_id = block[0]

            filename = block[1]

            display_name = (
                f"{block_id} — {filename}"
            )

            block_mapping[
                display_name
            ] = block_id

        # ----------------------------------------------------
        # HANDLE EMPTY DATABASE
        # ----------------------------------------------------

        if not block_mapping:

            block_mapping[
                "NO BLOCKS"
            ] = None

        display_values = list(
            block_mapping.keys()
        )

        # ----------------------------------------------------
        # FILE / BLOCK SELECTOR
        # ----------------------------------------------------

        block_selector = ctk.CTkOptionMenu(
            control_frame,
            values=display_values,
            width=240
        )

        block_selector.pack(
            side="left",
            padx=10,
            pady=20
        )

        # ----------------------------------------------------
        # RESULT LABEL
        # ----------------------------------------------------

        result_label = ctk.CTkLabel(
            self.main_frame,
            text="Ready to monitor block access.",
            font=ctk.CTkFont(
                size=15
            ),
            justify="left"
        )

        result_label.pack(
            anchor="w",
            padx=35,
            pady=15
        )

        # ----------------------------------------------------
        # MANUAL ACCESS FUNCTION
        # ----------------------------------------------------

        def perform_access(operation):

            selected_name = (
                block_selector.get()
            )

            block_id = block_mapping.get(
                selected_name
            )

            if block_id is None:

                result_label.configure(
                    text="No storage blocks available."
                )

                return

            selected_filename = "Unknown"

            for block in blocks:
                if block[0] == block_id:
                    selected_filename = block[1]
                    break

            success, result = process_access(
                block_id,
                operation
            )

            if success:

                result_text = (
                    f"Block: "
                    f"{result['block_id']}\n"
                    f"File: "
                    f"{selected_filename}\n"
                    f"Operation: "
                    f"{result['operation']}\n"
                    f"Temperature: "
                    f"{result['temperature']}\n"
                    f"Status: "
                    f"{result['label']}\n"
                    f"Current Tier: "
                    f"{result['current_tier']}\n"
                    f"Recommended Tier: "
                    f"{result['recommended_tier']}\n"
                    f"Migration: "
                    f"{result['migration']}"
                )

            else:

                result_text = (
                    f"Error: "
                    f"{result['message']}"
                )

            result_label.configure(
                text=result_text
            )

            # ------------------------------------------------
            # ADD MANUAL ACCESS TO ACTIVITY LOG
            # ------------------------------------------------

            self.live_events.insert(
                0,
                (
                    f"{datetime.now().strftime('%H:%M:%S')}"
                    f" | {operation}"
                    f" | Block {block_id}"
                    f" | {selected_filename}"
                )
            )

            self.live_events = (
                self.live_events[:50]
            )

            self.update_activity_display()

        # ----------------------------------------------------
        # READ BUTTON
        # ----------------------------------------------------

        read_button = ctk.CTkButton(
            control_frame,
            text="READ",
            command=lambda: perform_access(
                "READ"
            ),
            width=120
        )

        read_button.pack(
            side="left",
            padx=15,
            pady=20
        )

        # ----------------------------------------------------
        # WRITE BUTTON
        # ----------------------------------------------------

        write_button = ctk.CTkButton(
            control_frame,
            text="WRITE",
            command=lambda: perform_access(
                "WRITE"
            ),
            width=120
        )

        write_button.pack(
            side="left",
            padx=10,
            pady=20
        )

        # ----------------------------------------------------
        # ACTIVITY TITLE
        # ----------------------------------------------------

        activity_label = ctk.CTkLabel(
            self.main_frame,
            text="RECENT STORAGE ACTIVITY",
            font=ctk.CTkFont(
                size=16,
                weight="bold"
            )
        )

        activity_label.pack(
            anchor="w",
            padx=35,
            pady=(15, 5)
        )

        # ----------------------------------------------------
        # ACTIVITY TEXTBOX
        # ----------------------------------------------------

        self.activity_textbox = ctk.CTkTextbox(
            self.main_frame,
            height=180,
            font=ctk.CTkFont(
                size=13
            )
        )

        self.activity_textbox.pack(
            fill="both",
            expand=True,
            padx=35,
            pady=(5, 25)
        )

        # ----------------------------------------------------
        # INITIAL ACTIVITY DISPLAY
        # ----------------------------------------------------

        self.update_activity_display()


    # ========================================================
    # UPDATE ACTIVITY DISPLAY
    # ========================================================

    def update_activity_display(self):

        if not hasattr(
            self,
            "activity_textbox"
        ):

            return

        try:

            if not self.activity_textbox.winfo_exists():

                return

            # ------------------------------------------------
            # ENABLE TEXTBOX
            # ------------------------------------------------

            self.activity_textbox.configure(
                state="normal"
            )

            # ------------------------------------------------
            # CLEAR OLD CONTENT
            # ------------------------------------------------

            self.activity_textbox.delete(
                "1.0",
                "end"
            )

            # ------------------------------------------------
            # DISPLAY EMPTY STATE
            # ------------------------------------------------

            if not self.live_events:

                self.activity_textbox.insert(
                    "end",
                    "No live storage activity yet.\n"
                )

            # ------------------------------------------------
            # DISPLAY EVENTS
            # ------------------------------------------------

            else:

                for event in self.live_events:

                    self.activity_textbox.insert(
                        "end",
                        event + "\n"
                    )

            # ------------------------------------------------
            # DISABLE TEXTBOX
            # ------------------------------------------------

            self.activity_textbox.configure(
                state="disabled"
            )

        except Exception:

            return


    # ========================================================
    # CLOSE APPLICATION
    # ========================================================

    def close_application(self):

        try:
            self.optimizer_stop_event.set()
        except Exception:
            pass

        for monitor in (
            getattr(self, "secondary_monitor", None),
            getattr(self, "ssd_monitor", None),
        ):
            try:
                if monitor:
                    monitor.stop()
            except Exception:
                pass

        self.destroy()


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":

    app = HybridStorageApp()

    app.mainloop()