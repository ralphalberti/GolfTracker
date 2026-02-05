import sys
import sqlite3
import re
import json
import os
import platform
import csv # Can remove this if I don't want to use the import feature any longer
from datetime import date, datetime
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.ticker import MaxNLocator
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, QDate, QPropertyAnimation
from PyQt5.QtGui import QColor, QIntValidator, QPixmap, QPalette
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QDateEdit, QAction, QCompleter, QAbstractItemView, QTabWidget, QComboBox, QFrame, QSizePolicy,
    QGraphicsOpacityEffect
)

DB_FILE = "golf_scores.db"

class GolfTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Golf Tracker")
        self.setGeometry(100, 100, 1100, 750)

        self.conn = sqlite3.connect(DB_FILE)
        self.create_table()

        self.current_edit_id = None
        self.filter_active = False

        self.current_chart_type = "average_score"

        self.initUI()
        self.load_data()

        # --- Apply system theme detection AFTER everything is built ---
        palette = QApplication.instance().palette()
        is_dark = palette.color(QPalette.Window).value() < 128

        if platform.system() == "Windows":
            try:
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                ) as key:
                    apps_use_light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
                    mode = "dark" if apps_use_light == 0 else "light"
            except Exception:
                mode = "dark" if is_dark else "light"
        else:
            mode = "dark" if is_dark else "light"

        self.set_theme(mode)

    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course TEXT,
                date TEXT,
                cost INTEGER,
                score INTEGER
            )
        """)
        self.conn.commit()

    def initUI(self):
        self.tabs = QTabWidget()

        # Create stats labels used by both tabs
        self.stats_label_main, self.stats_label_charts = self.create_stats_bar()

        # Initialize tabs
        self.init_main_tab()
        self.init_chart_tab()
        self.tabs.addTab(self.main_tab, "Main")
        self.tabs.addTab(self.chart_tab, "Charts")

        # Central layout with a shared filter bar sitting above the tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout()
        root_layout.addWidget(self.create_shared_filter_bar())  # shared filter bar
        # thin separator under the toolbar for polish
        hr = QFrame()
        hr.setFrameShape(QFrame.HLine)
        hr.setFrameShadow(QFrame.Sunken)
        root_layout.addWidget(hr)

        root_layout.addWidget(self.tabs)
        central_widget.setLayout(root_layout)

        menubar = self.menuBar()

        # --- File menu ---
        file_menu = menubar.addMenu("File")

        import_csv_action = QAction("Import CSV", self)
        import_csv_action.triggered.connect(self.import_csv)
        file_menu.addAction(import_csv_action)

        export_csv_action = QAction("Export CSV", self)
        export_csv_action.triggered.connect(self.export_csv)
        file_menu.addAction(export_csv_action)

        delete_all_action = QAction("Delete All Records", self)
        delete_all_action.triggered.connect(self.delete_all_records)
        file_menu.addAction(delete_all_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Help menu ---
        help_menu = menubar.addMenu("Help")

        help_action = QAction("Golf Tracker Help", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

        about_action = QAction("About Golf Tracker", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        # --- Restore column widths
        self.restore_column_widths()

        # --- Restore window size and position
        self.restore_window_settings()


        # Populate course autocomplete on startup
        try:
            self.refresh_autocomplete()
        except Exception:
            pass

    def set_theme(self, mode: str):
        """
        Apply light or dark mode styles to key widgets (table, labels, etc.)
        """
        if mode == "dark":
            bg = "#121212"
            fg = "#EEEEEE"
            alt_row = "#D9D9D9"  # clear, medium-light gray for strong contrast
            grid_color = "#B0B0B0"
            header_bg = "#1E1E1E"    # dark gray header
            header_fg = "#EEEEEE"
            stats_bg = "#3b3636"     # dark footer in dark mode
            stats_fg = "#FFFFFF"
        else:
            bg = "#FFFFFF"
            fg = "#111111"
            alt_row = "#E0E0E0"      # more pronounced light gray for alternating rows
            grid_color = "#BFBFBF"   # darker gridlines for separation
            header_bg = "#EAEAEA"    # soft gray header
            header_fg = "#111111"    # dark text for readability
            stats_bg = "#FFFFFF"     # light footer in light mode 
            stats_fg = "#111111"

        # --- QTableWidget (data grid) ---
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg};
                color: {fg};
                gridline-color: {grid_color};
                selection-background-color: #3CB371;
                selection-color: white;
                border: none;
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_fg};
                border: 1px solid {grid_color};
                padding: 4px;
                font-weight: bold;
            }}
        """)

        # --- Stats labels (bottom bars) ---
        for lbl in (self.stats_label_main, self.stats_label_charts):
            lbl.setStyleSheet(
                f"""
                background-color: {stats_bg};
                color: {stats_fg};
                font-size: 14px;
                padding: 4px 6px;
                border: 1px solid #B7950B;
                """
            )
        
    def refresh_stats_bar_style(self):
        """
        Reapply the theme style to the stats bar labels
        after text updates (like clearing filters),
        but skip if a red (filtered) style is active.
        """
        palette = QApplication.instance().palette()
        is_dark = palette.color(QPalette.Window).value() < 128
        mode = "dark" if is_dark else "light"

        # Check if any stats label is currently using the red (filtered) style
        for lbl in (self.stats_label_main, self.stats_label_charts):
            current_style = lbl.styleSheet().lower()
            if any(x in current_style for x in ["#b22222", "#ff4444", "background-color: red"]):
                # One or more labels are red → skip full theme reset
                return

        # If we reach here, no red styles are active → safe to reapply theme
        self.set_theme(mode)

    def fade_stats_bar(self, duration=300):
        """
        Fade animation for the stats bar labels (smooth transition between color changes).
        Ensures opacity is restored and animations don't stack.
        """
        for lbl in (self.stats_label_main, self.stats_label_charts):
            # Reuse or create opacity effect
            effect = lbl.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(lbl)
                lbl.setGraphicsEffect(effect)

            # Reset opacity before starting animation
            effect.setOpacity(0.0)

            # Create fade animation
            anim = QPropertyAnimation(effect, b"opacity", lbl)
            anim.setDuration(duration)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.start(QPropertyAnimation.DeleteWhenStopped)

            # Store reference to prevent garbage collection
            lbl._fade_anim = anim

    # --- Shared, single filter bar ---
    def create_shared_filter_bar(self):
        """One shared filter bar used by all tabs."""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(6, 6, 6, 0)   # small top margin, no bottom gap before tabs
        row.setSpacing(6)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("filter by course name, yyyy or yyyy-mm")
        self.filter_input.returnPressed.connect(self.apply_or_clear_filter)

        self.apply_button = QPushButton('Apply Filter')
        self.apply_button.clicked.connect(self.apply_or_clear_filter)

        row.addWidget(self.apply_button)
        row.addWidget(self.filter_input)
        return container

    def create_stats_bar(self):
        # Create two separate stats labels (one per tab)
        self.stats_label_main = QLabel("Stats will appear here")
        self.stats_label_charts = QLabel("Stats will appear here")

        for lbl in (self.stats_label_main, self.stats_label_charts):
            lbl.setStyleSheet(
                "background-color: #3b3636; color: white; font-size: 14px; "
                "padding: 4px 6px; border: 1px solid #B7950B;"
            )
            lbl.setFixedHeight(30)
            lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Return both so they can be added into their respective tabs
        return self.stats_label_main, self.stats_label_charts
    
    
    def create_main_inputs_panel(self):
        """
        Gold-standard input panel using a compact GridLayout.
        Labels are fixed-width and right-aligned; edits are 250px wide and left-aligned.
        """
        container = QWidget()
        grid = QGridLayout(container)
        # input spacing
        grid.setVerticalSpacing(6)
        grid.setHorizontalSpacing(10)
        grid.setContentsMargins(6, 6, 6, 0)

        LABEL_W = 90
        EDIT_W  = 250

        # --- Course ---
        course_lbl = QLabel("Course:")
        course_lbl.setFixedWidth(LABEL_W)
        self.course_input = QLineEdit()
        self.course_input.setPlaceholderText("e.g., Pebble Beach")
        self.course_input.setFixedWidth(EDIT_W)
        grid.addWidget(course_lbl, 0, 0, alignment=Qt.AlignRight)
        grid.addWidget(self.course_input, 0, 1, alignment=Qt.AlignLeft)

        # --- Date ---
        date_lbl = QLabel("Date:")
        date_lbl.setFixedWidth(LABEL_W)
        self.date_input = QDateEdit()
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setFixedWidth(EDIT_W)
        grid.addWidget(date_lbl, 1, 0, alignment=Qt.AlignRight)
        grid.addWidget(self.date_input, 1, 1, alignment=Qt.AlignLeft)

        # --- Cost ---
        cost_lbl = QLabel("Cost ($):")
        cost_lbl.setFixedWidth(LABEL_W)
        self.cost_input = QLineEdit()
        self.cost_input.setPlaceholderText("dollars only")
        self.cost_input.setValidator(QIntValidator(0, 10000, self))
        self.cost_input.setFixedWidth(EDIT_W)
        grid.addWidget(cost_lbl, 2, 0, alignment=Qt.AlignRight)
        grid.addWidget(self.cost_input, 2, 1, alignment=Qt.AlignLeft)

        # --- Score ---
        score_lbl = QLabel("Score:")
        score_lbl.setFixedWidth(LABEL_W)
        self.score_input = QLineEdit()
        self.score_input.setValidator(QIntValidator(0, 200, self))
        self.score_input.setFixedWidth(EDIT_W)
        grid.addWidget(score_lbl, 3, 0, alignment=Qt.AlignRight)
        grid.addWidget(self.score_input, 3, 1, alignment=Qt.AlignLeft)

        # Make the second column stretch to keep left alignment and prevent drifting
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        return container
    
    def create_button_bar(self):
        """
        Horizontal action bar placed between inputs and data grid.
        Buttons expand to use full width.
        """
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 6, 6, 6)
        h.setSpacing(10)

        # Buttons
        self.add_btn  = QPushButton("Add Record")
        self.edit_btn = QPushButton("Edit Record")   # toggles to "Update Record"
        self.del_btn  = QPushButton("Delete Record")
        self.clear_btn= QPushButton("Clear")

        # Make them expand equally
        for b in (self.add_btn, self.edit_btn, self.del_btn, self.clear_btn):
            b.setMinimumHeight(28)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Wire up actions
        self.add_btn.clicked.connect(self.add_record)
        self.edit_btn.clicked.connect(self.toggle_edit_update)
        self.del_btn.clicked.connect(self.delete_record)
        self.clear_btn.clicked.connect(self.clear_inputs)

        # Add in order; stretch not needed because buttons expand
        h.addWidget(self.add_btn)
        h.addWidget(self.edit_btn)
        h.addWidget(self.del_btn)
        h.addWidget(self.clear_btn)
        return bar


    def init_main_tab(self):
        self.main_tab = QWidget()
        main_layout = QVBoxLayout(self.main_tab)

        # --- Inputs panel (gold standard) ---
        main_layout.addWidget(self.create_main_inputs_panel())

        # --- Button bar (horizontal) ---
        main_layout.addWidget(self.create_button_bar())

        # --- Table (expanding) ---
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['ID', 'Course', 'Date', 'Cost ($)', 'Score'])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        # Column behavior
        header = self.table.horizontalHeader()
        try:
            header.setSectionResizeMode(QHeaderView.Interactive)
        except AttributeError:
            header.setResizeMode(QHeaderView.Interactive)  # Qt4 fallback
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(50)

        # Double-click to edit
        try:
            self.table.cellDoubleClicked.disconnect()
        except Exception:
            pass
        self.table.cellDoubleClicked.connect(self.load_record_for_edit)

        # Column sizing: Course stretchy; Date/Cost/Score fixed widths
        try:
            header.setSectionResizeMode(1, QHeaderView.Stretch)   # Course
            header.setSectionResizeMode(2, QHeaderView.Fixed)     # Date
            header.setSectionResizeMode(3, QHeaderView.Fixed)     # Cost
            header.setSectionResizeMode(4, QHeaderView.Fixed)     # Score
        except AttributeError:
            header.setResizeMode(1, QHeaderView.Stretch)
            header.setResizeMode(2, QHeaderView.Fixed)
            header.setResizeMode(3, QHeaderView.Fixed)
            header.setResizeMode(4, QHeaderView.Fixed)

        # Preferred fixed widths for Date/Cost/Score
        self.table.setColumnWidth(2, 110)   # Date
        self.table.setColumnWidth(3, 90)    # Cost
        self.table.setColumnWidth(4, 80)    # Score

        # Double-click to edit
        self.table.cellDoubleClicked.connect(self.load_record_for_edit)
        main_layout.addWidget(self.table, 1)  # stretch so table takes extra space

        # --- Stats bar (BOTTOM) ---
        stats_wrapper = QHBoxLayout()
        stats_wrapper.setContentsMargins(6, 6, 6, 6)
        stats_wrapper.addWidget(self.stats_label_main)
        main_layout.addLayout(stats_wrapper)

        self.main_tab.setLayout(main_layout)

    def change_chart(self, chart_type):
        self.current_chart_type = chart_type
        for key, (btn, color) in self.chart_buttons.items():
            if key == chart_type:
                btn.setStyleSheet(f"background-color: {color}; color: black; font-weight: bold;")
            else:
                btn.setStyleSheet("")
        self.update_charts(self.filter_input.text())

    def update_charts(self, filter_text):
        self.chart_axes.clear()
        # Re-apply chart theme after clearing
        # This is definitely the place to change chart color
        # My default colors are ("#d6dbdf", "#d6dbdf")
        # Parts of the chart  ("outside", "inside")
        self.apply_chart_theme("#c3c7c7", "#dbe2e9")
        cursor = self.conn.cursor()

        if self.current_chart_type == "average_score":
            if filter_text:
                cursor.execute(
                    "SELECT course, AVG(CAST(score AS INTEGER)) FROM scores "
                    "WHERE course LIKE ? OR date LIKE ? GROUP BY course",
                    (f"%{filter_text}%", f"%{filter_text}%")
                )
            else:
                cursor.execute("SELECT course, AVG(CAST(score AS INTEGER)) FROM scores GROUP BY course")
            results = sorted(cursor.fetchall(), key=lambda x: x[1])
            title = "Average Score per Course"
            ylabel = "Average Score"
            bar_color = "#4CAF50"

        elif self.current_chart_type == "rounds_per_course":
            if filter_text:
                cursor.execute(
                    "SELECT course, COUNT(*) FROM scores "
                    "WHERE course LIKE ? OR date LIKE ? GROUP BY course",
                    (f"%{filter_text}%", f"%{filter_text}%")
                )
            else:
                cursor.execute("SELECT course, COUNT(*) FROM scores GROUP BY course")
            results = sorted(cursor.fetchall(), key=lambda x: x[1], reverse=True)
            title = "Number of Rounds per Course"
            ylabel = "Rounds Played"
            bar_color = "#2196F3"
            self.chart_axes.yaxis.set_major_locator(MaxNLocator(integer=True))

        elif self.current_chart_type == "best_score":
            if filter_text:
                cursor.execute(
                    "SELECT course, MIN(CAST(score AS INTEGER)) FROM scores "
                    "WHERE course LIKE ? OR date LIKE ? GROUP BY course",
                    (f"%{filter_text}%", f"%{filter_text}%")
                )
            else:
                cursor.execute("SELECT course, MIN(CAST(score AS INTEGER)) FROM scores GROUP BY course")
            results = sorted(cursor.fetchall(), key=lambda x: x[1])
            title = "Best Score per Course"
            ylabel = "Best Score"
            bar_color = "#FF9800"

        else:
            return

        courses = [row[0] for row in results]
        values = [row[1] for row in results]

        bars = self.chart_axes.bar(courses, values, color=bar_color, edgecolor='black')

        self.chart_axes.set_title(title, fontsize=14, fontweight='bold')
        self.chart_axes.set_ylabel(ylabel, fontsize=12)
        self.chart_axes.set_xticks(range(len(courses)))
        self.chart_axes.set_xticklabels(courses, rotation=45, ha="right", fontsize=9)
        self.chart_axes.grid(axis='y', linestyle='--', alpha=0.7)

        # Add value labels
        for bar in bars:
            height = bar.get_height()
            self.chart_axes.annotate(
                f"{height:.0f}" if height == int(height) else f"{height:.2f}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 4),
                textcoords="offset points",
                ha='center',
                va='bottom',
                fontsize=9,
                color='black',
                fontweight='bold'
            )

        self.chart_canvas.draw()

    # --- Menu Helpers ---
    def show_help(self):
        QMessageBox.information(self, "Golf Tracker Help",
                                 "<h3>Golf Tracker Help</h3>"
                                 "<p>Use this app to track your golf rounds. "
                                 "Add, edit, delete, and filter rounds. "
                                 "Export or import CSV files from the File menu.</p>")

    def show_about(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        from PyQt5.QtGui import QPixmap, QFont
        from PyQt5.QtCore import Qt

        img_path = os.path.join(os.path.dirname(__file__), "assets", "titleist.png")

        if not os.path.exists(img_path):
            QMessageBox.warning(self, "Missing Image", f"Could not find image:\n{img_path}")
            return

        # --- Mode Toggle: "light" or "dark"
        # mode = "dark"  # change to "dark" if you want dark mode manually

        # --- Auto-detect mode using QPalette and platform hints
        palette = QApplication.instance().palette()
        is_dark = palette.color(QPalette.Window).value() < 128

        if platform.system() == "Darwin":  # macOS handles dark mode nicely
            mode = "dark" if is_dark else "light"
        elif platform.system() == "Windows":
            # Try to detect Windows dark mode via registry (optional, requires 'winreg')
            try:
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                ) as key:
                    apps_use_light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
                    mode = "dark" if apps_use_light == 0 else "light"
            except Exception:
                mode = "dark" if is_dark else "light"
        else:
            # Default heuristic for Linux and others
            mode = "dark" if is_dark else "light"

        # --- Theme settings
        if mode == "light":
            bg_color = "#fdfdfd"
            text_color = "#222"
            accent_color = "#2E8B57"
            button_color = "#2E8B57"
            button_hover = "#3CB371"
        else:  # dark mode
            bg_color = "#202020"
            text_color = "#ddd"
            accent_color = "#77DD77"
            button_color = "#3CB371"
            button_hover = "#2E8B57"

        # --- Create custom dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("About Golf Tracker")
        dlg.setModal(True)
        dlg.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
                border: 2px solid {accent_color};
                border-radius: 12px;
            }}
            QLabel {{
                color: {text_color};
            }}
            QPushButton {{
                background-color: {button_color};
                color: white;
                padding: 6px 16px;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: {button_hover};
            }}
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # --- Image
        img_label = QLabel()
        pix = QPixmap(img_path).scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        img_label.setPixmap(pix)
        img_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(img_label)

        # --- Title
        title_label = QLabel("Golf Tracker")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"color: {accent_color};")
        layout.addWidget(title_label)

        # --- Description
        desc_label = QLabel(f"""
            <p style='font-size:13px; color:{text_color}; text-align:center;'>
            <b>Version:</b> 1.1 (feat/about branch)<br>
            <b>Framework:</b> PyQt5 + SQLite + Matplotlib
            </p>
            <p style='font-size:13px; color:{text_color}; text-align:center;'>
            Track your rounds, analyze your scores,<br>
            and enjoy your game with style! 🏌️‍♂️
            </p>
        """)
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)

        # --- OK Button
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dlg.accept)
        layout.addWidget(ok_button, alignment=Qt.AlignCenter)

        # --- Center the dialog precisely on the main window
        if self.isVisible():
            dlg.adjustSize()  # force Qt to calculate final size before centering
            parent_rect = self.frameGeometry()
            dlg_rect = dlg.frameGeometry()
            center_point = parent_rect.center()
            dlg_rect.moveCenter(center_point)
            dlg.move(dlg_rect.topLeft())

        # --- Fade-in animation (subtle 250 ms)
        effect = QGraphicsOpacityEffect(dlg)
        dlg.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(400)                # milliseconds
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        dlg.exec_()

    # --- Autocomplete refresh ---
    def refresh_autocomplete(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT course FROM scores")
        courses = [row[0] for row in cursor.fetchall() if row[0]]
        completer = QCompleter(courses)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.course_input.setCompleter(completer)

    # --- Helpers ---
    def clear_inputs(self):
        self.course_input.clear()
        self.date_input.setDate(QDate.currentDate())
        self.cost_input.clear()
        self.score_input.clear()

    # --- Save and Restore column widths
    def save_column_widths(self):
        settings = self.load_settings()  # Merge with any existing settings
        col_widths = {
            str(col): self.table.columnWidth(col)
            for col in range(self.table.columnCount())
        }
        settings["column_widths"] = col_widths

        try:
            with open(self.get_settings_path(), "w") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save column widths: {e}")

    def restore_column_widths(self):
        if not os.path.exists("settings.json"):
            return

        with open("settings.json", "r") as f:
            try:
                settings = json.load(f)
                widths = settings.get("column_widths", {})
                for col_str, width in widths.items():
                    self.table.setColumnWidth(int(col_str), width)
            except json.JSONDecodeError:
                pass

    # --- Save and Restore window settings
    def save_window_settings(self):
        settings = self.load_settings()
        settings["window"] = {
            "x": self.x(),
            "y": self.y(),
            "width": self.width(),
            "height": self.height()
        }

        try:
            with open(self.get_settings_path(), "w") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def restore_window_settings(self):
        settings_path = self.get_settings_path()
        if not os.path.exists(settings_path):
            return

        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)

            geometry = settings.get("window", {})
            self.move(
                geometry.get("x", 100),
                geometry.get("y", 100)
            )
            self.resize(
                geometry.get("width", 800),
                geometry.get("height", 600)
            )
        except Exception as e:
            print(f"Failed to load window settings: {e}")

    def load_settings(self):
        settings_path = self.get_settings_path()
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def get_settings_path(self):
        return os.path.join(os.path.dirname(__file__), "settings.json")

    # --- Do these things when exiting the app
    def closeEvent(self, event):
        self.save_window_settings()
        self.save_column_widths()
        event.accept()

    def safe_text(self, item):
        return item.text() if item else ""

    # --- Data Loading ---
    def load_data(self, filter_text=None):
        self.table.setSortingEnabled(False)   # pause sorting
        self.table.clearContents()            # only clears the cells, keeps headers
        self.table.setRowCount(0)             # drop old rows
        cursor = self.conn.cursor()
        if filter_text:
            if re.match(r"^\d{4}-\d{2}$", filter_text):  # YYYY-MM
                cursor.execute(
                    "SELECT id, course, date, CAST(cost AS INTEGER), CAST(score AS INTEGER) "
                    "FROM scores WHERE date LIKE ? ORDER BY date ASC",
                    (f"%{filter_text}%",),
                )
            elif re.match(r"^\d{4}$", filter_text):  # YYYY
                cursor.execute(
                    "SELECT id, course, date, CAST(cost AS INTEGER), CAST(score AS INTEGER) "
                    "FROM scores WHERE strftime('%Y', date) = ? ORDER BY date ASC",
                    (filter_text,),
                )
            elif re.match(r"^\d{4}-\d{2}-\d{2}$", filter_text):  # YYYY-MM-DD
                cursor.execute(
                    "SELECT id, course, date, CAST(cost AS INTEGER), CAST(score AS INTEGER) "
                    "FROM scores WHERE date = ? ORDER BY date ASC",
                    (filter_text,),
                )
            else:  # Course name
                cursor.execute(
                    "SELECT id, course, date, CAST(cost AS INTEGER), CAST(score AS INTEGER) "
                    "FROM scores WHERE course LIKE ? COLLATE NOCASE ORDER BY date ASC",
                    (f"%{filter_text}%",),
                )
        else:
            cursor.execute(
                "SELECT id, course, date, CAST(cost AS INTEGER), CAST(score AS INTEGER) "
                "FROM scores ORDER BY date ASC"
            )
        rows = cursor.fetchall()
        self.table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                text_val = "" if val is None else str(val)

                # Default item
                item = QTableWidgetItem()

                if c in (2, 3, 4):  # Date, Cost, Score → center align
                    item.setTextAlignment(Qt.AlignCenter)

                if c in (3, 4):  # Cost and Score
                    try:
                        numeric_val = int(val)
                    except (TypeError, ValueError):
                        numeric_val = 0
                    # Use numeric for sorting + display
                    item.setData(Qt.DisplayRole, numeric_val)
                    item.setText(str(numeric_val))  # display text, but sorting uses int
                else:
                    # For non-numeric columns → just use string
                    item.setText(text_val)

                self.table.setItem(r, c, item)

        self.table.hideColumn(0)
        self.table.setSortingEnabled(True)

        # Default sort by Date descending (latest first)
        try:
            hdr = self.table.horizontalHeader()
            hdr.setSortIndicatorShown(True)
            hdr.setSortIndicator(2, Qt.DescendingOrder)
        except Exception:
            pass
        #You don’t have to change your SQL ORDER BY clauses
        #the view’s sort indicator will override the initial display. 
        #If you want the query itself to match, change ORDER BY date ASC to ORDER BY date DESC as well.

        self.update_stats(filter_text)
        self.apply_row_highlighting()
        self.update_charts(filter_text)

    def apply_row_highlighting(self):
        row_count = self.table.rowCount()
        if row_count == 0:
            return

        # Detect current mode from palette (light or dark)
        palette = QApplication.instance().palette()
        is_dark = palette.color(QPalette.Window).value() < 128
        mode = "dark" if is_dark else "light"

        # Theme-aware defaults
        default_fg = QColor("#EEEEEE") if mode == "dark" else QColor("#111111")

        # Gather all scores
        scores = []
        for r in range(row_count):
            item = self.table.item(r, 4)
            if item:
                try:
                    scores.append(int(item.text()))
                except ValueError:
                    pass

        if not scores:
            return

        min_score = min(scores)
        max_score = max(scores)

        for r in range(row_count):
            score_item = self.table.item(r, 4)
            if not score_item:
                continue
            try:
                score_val = int(score_item.text())
            except ValueError:
                continue

            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if not item:
                    continue

                # --- Manual alternating row base color ---
                if mode == "dark":
                    base_bg = QColor("#1E1E1E") if r % 2 else QColor("#121212")
                else:
                    base_bg = QColor("#E0E0E0") if r % 2 else QColor("#FFFFFF")
                base_fg = default_fg

                # --- Apply highlight colors ---
                if score_val == min_score:
                    item.setBackground(QColor("#2E8B57"))  # green
                    item.setForeground(QColor("#FFFFFF"))
                elif score_val == max_score:
                    item.setBackground(QColor("#FF8C00"))  # orange
                    item.setForeground(QColor("#FFFFFF"))
                else:
                    item.setBackground(base_bg)
                    item.setForeground(base_fg)

    # --- Stats Bar ---
    def update_stats(self, filter_text=None):
        cursor = self.conn.cursor()

        # Base style and label suffix depend on whether a filter is active
        style_default = (
            "background-color: #3b3636; color: #ffffff; font-size: 14px; "
            "padding: 4px; border: 1px solid #B7950B;"
        )
        # Theme-aware filtered style
        palette = QApplication.instance().palette()
        is_dark = palette.color(QPalette.Window).value() < 128
        if is_dark:
            filter_bg = "#B22222"  # dark red (Firebrick)
            filter_fg = "#FFFFFF"
        else:
            filter_bg = "#FF4444"  # bright red for light mode
            filter_fg = "#FFFFFF"

        style_filtered = (
            f"background-color: {filter_bg}; color: {filter_fg}; font-size: 14px; "
            f"padding: 4px 6px; border: 1px solid #B7950B;"
        )

        where_clause = ""
        params = ()
        style = style_default
        suffix = ""

        if filter_text:
            if len(filter_text) == 4 and filter_text.isdigit():
                where_clause = " WHERE strftime('%Y', date) = ?"
                params = (filter_text,)
            elif len(filter_text) == 7 and filter_text[4] == '-':
                where_clause = " WHERE strftime('%Y-%m', date) = ?"
                params = (filter_text,)
            else:
                where_clause = " WHERE course LIKE ? COLLATE NOCASE"
                params = (f"%{filter_text}%",)
            style = style_filtered
            suffix = " (Filtered)"

        cursor.execute(
            "SELECT COUNT(*), SUM(cost), AVG(cost), AVG(score), MIN(score), MAX(score) FROM scores"
            + where_clause,
            params,
        )
        rounds, total_cost, avg_cost, avg_score, best, worst = cursor.fetchone() or (0, 0, 0, 0, None, None)

        # If completely no data in DB and no filter: show message
        if not filter_text and rounds == 0:
            msg = "No data available."
            for lbl in (self.stats_label_main, self.stats_label_charts):
                lbl.setText(msg)
                lbl.setStyleSheet(style_default)
            return

        stats_html = (
            f"Total Rounds: <b>{rounds or 0}</b> &nbsp; | &nbsp; "
            f"Total Cost: <b>${(total_cost or 0):,.0f}</b> &nbsp; | &nbsp; "
            f"Avg Cost: <b>${(avg_cost or 0):,.0f}</b> &nbsp; | &nbsp; "
            f"Avg Score: <b>{(avg_score or 0):.1f}</b> &nbsp; | &nbsp; "
            f"Lowest Score: <b>{(best if best is not None else '--')}</b> &nbsp; | &nbsp; "
            f"Highest Score: <b>{(worst if worst is not None else '--')}</b>{suffix}"
        )

        for lbl in (self.stats_label_main, self.stats_label_charts):
            lbl.setText(stats_html)
            lbl.setStyleSheet(style)

        # --- Reapply theme styling and fade in for smooth transition ---
        self.refresh_stats_bar_style()
        self.fade_stats_bar(400)  # fade over 400ms

    def select_row_by_id(self, record_id):
        """Select and center the row in the table that matches record_id."""
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == str(record_id):
                self.table.selectRow(r)
                self.table.scrollToItem(
                    self.table.item(r, 1),
                    QAbstractItemView.PositionAtCenter
                )
                break

    # --- CRUD ---
    def add_record(self):
        course = self.course_input.text().strip()
        date = self.date_input.text().strip()
        cost = self.cost_input.text().strip()
        score = self.score_input.text().strip()

        if not course or not date or not cost or not score:
            QMessageBox.warning(self, "Input Error", "All fields are required.")
            return

        try:
            cost_val = int(cost)
            score_val = int(score)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter dollars only and a numeric score.")
            return

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO scores (course, date, cost, score) VALUES (?, ?, ?, ?)",
            (course, date, cost_val, score_val),
        )
        self.conn.commit()
        new_id = cursor.lastrowid
        self.load_data()
        self.select_row_by_id(new_id)

        # Clear inputs and refresh autocomplete (retain these!)
        self.clear_inputs()
        self.refresh_autocomplete()

    def load_record_for_edit(self, row, col):
        item_id = self.table.item(row, 0)
        if not item_id:
            QMessageBox.warning(self, "Selection Error", "Could not read ID from selected row.")
            return

        self.current_edit_id = int(item_id.data(Qt.DisplayRole))
        self.course_input.setText(self.safe_text(self.table.item(row, 1)))
        self.date_input.setDate(QDate.fromString(self.safe_text(self.table.item(row, 2)), "yyyy-MM-dd"))
        self.cost_input.setText(self.safe_text(self.table.item(row, 3)))
        self.score_input.setText(self.safe_text(self.table.item(row, 4)))
        self.edit_btn.setText("Update Record")

    def toggle_edit_update(self):
        if self.edit_btn.text() == "Edit Record":
            selected = self.table.currentRow()
            if selected < 0:
                QMessageBox.warning(self, "Selection Error", "Please select a row to edit.")
                return
            id_item = self.table.item(selected, 0)
            if not id_item:
                QMessageBox.warning(self, "Selection Error", "Could not read ID from selected row.")
                return
            self.current_edit_id = int(id_item.data(Qt.DisplayRole))
            self.course_input.setText(self.safe_text(self.table.item(selected, 1)))
            self.date_input.setDate(QDate.fromString(self.safe_text(self.table.item(selected, 2)), "yyyy-MM-dd"))
            self.cost_input.setText(self.safe_text(self.table.item(selected, 3)))
            self.score_input.setText(self.safe_text(self.table.item(selected, 4)))
            self.edit_btn.setText("Update Record")
        else:
            self.update_record()

    def update_record(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "No record selected for updating.")
            return

        course = self.course_input.text().strip()
        date = self.date_input.text().strip()
        cost = self.cost_input.text().strip()
        score = self.score_input.text().strip()

        if not course or not date or not cost or not score:
            QMessageBox.warning(self, "Input Error", "All fields are required.")
            return

        try:
            cost_val = int(cost)
            score_val = int(score)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter dollars only and a numeric score.")
            return

        record_id = self.table.item(selected_row, 0).text()
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE scores SET course=?, date=?, cost=?, score=? WHERE id=?",
            (course, date, cost_val, score_val, record_id),
        )
        self.conn.commit()
        self.load_data()
        self.select_row_by_id(record_id)

        # Clear inputs and refresh autocomplete (retain these!)
        self.clear_inputs()
        self.refresh_autocomplete()
        self.edit_btn.setText("Edit Record")

    def delete_record(self):
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "No Selection", "Please select a record to delete.")
            return

        course = self.table.item(selected, 1).text()
        date = self.table.item(selected, 2).text()

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the round at {course} on {date}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            record_id = int(self.table.item(selected, 0).text())
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM scores WHERE id = ?", (record_id,))
            self.conn.commit()
            self.load_data(self.filter_input.text().strip())
            self.clear_inputs()

    def delete_all_records(self):
        confirm = QMessageBox.question(self, "Confirm Delete All",
                                       "Are you sure you want to delete ALL records?",
                                       QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM scores")
            self.conn.commit()
            self.load_data()

    def apply_or_clear_filter(self):
        if not self.filter_active:
            filter_text = self.filter_input.text().strip()
            self.load_data(filter_text)
            # Update any known filter buttons if they exist
            for btn_attr in ("filter_btn", "apply_button"):
                btn = getattr(self, btn_attr, None)
                if btn:
                    btn.setText("Clear Filter")
            self.filter_active = True
        else:
            self.filter_input.clear()
            self.load_data()
            for btn_attr in ("filter_btn", "apply_button"):
                btn = getattr(self, btn_attr, None)
                if btn:
                    btn.setText("Apply Filter")
            self.filter_active = False

    # --- CSV ---
    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        cursor = self.conn.cursor()
        with open(path, "r") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 4:
                    cursor.execute("INSERT INTO scores (course, date, cost, score) VALUES (?, ?, ?, ?)",
                                   (row[0].strip(), row[1].strip(), int(float(row[2].strip())), int(float(row[3].strip()))))
        self.conn.commit()
        self.load_data()

    def export_csv(self):
        today = date.today().strftime("%Y-%m-%d")
        default_filename = f"golf_scores_{today}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", default_filename, "CSV Files (*.csv)")
        if not path:
            return
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM scores")
        rows = cursor.fetchall()
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Course", "Date", "Cost", "Score"])
            for row in rows:
                writer.writerow(row[1:])

    #def apply_chart_theme(self, fig_bg="#d6dbdf", ax_bg="#d6dbdf"):
    def apply_chart_theme(self, fig_bg="#d6dbdf", ax_bg="#d6dbdf"):
        """
        Apply figure and axes background colors for the charts.
        """
        try:
            fig = self.chart_canvas.figure
            ax = self.chart_axes
            fig.set_facecolor(fig_bg)
            ax.set_facecolor(ax_bg)
        except Exception:
            pass

    def init_chart_tab(self):

        self.chart_tab = QWidget()
        layout = QVBoxLayout(self.chart_tab)

        # --- Chart Selector Buttons ---
        button_layout = QHBoxLayout()
        btn_avg_score = QPushButton('Average Score')
        btn_num_rounds = QPushButton('Rounds per Course')
        btn_best_score = QPushButton('Best Score')
        button_layout.addWidget(btn_avg_score)
        button_layout.addWidget(btn_num_rounds)
        button_layout.addWidget(btn_best_score)
        layout.addLayout(button_layout)

        btn_avg_score.clicked.connect(lambda: self.change_chart('average_score'))
        btn_num_rounds.clicked.connect(lambda: self.change_chart('rounds_per_course'))
        btn_best_score.clicked.connect(lambda: self.change_chart('best_score'))

        # --- Chart Canvas (expands) ---
        self.chart_canvas = FigureCanvas(Figure(figsize=(5, 3), facecolor="#d6dbdf"))
        self.chart_axes = self.chart_canvas.figure.add_subplot(111)
        self.chart_axes.set_facecolor("#d6dbdf")
        # Apply theme (so future changes can be centralized)
        #self.apply_chart_theme("#d6dbdf", "#d6dbdf")
        self.apply_chart_theme("#d6dbdf", "#d6dbdf")
        layout.addWidget(self.chart_canvas, 1)  # stretch so canvas takes extra space

        # --- Stats bar (BOTTOM) ---
        stats_wrapper = QHBoxLayout()
        stats_wrapper.setContentsMargins(6, 6, 6, 6)
        stats_wrapper.addWidget(self.stats_label_charts)
        layout.addLayout(stats_wrapper)

        # Store chart buttons with highlight colors
        self.chart_buttons = {
            'average_score': (btn_avg_score, '#4CAF50'),
            'rounds_per_course': (btn_num_rounds, '#2196F3'),
            'best_score': (btn_best_score, '#FF9800')
        }

        # Default highlight
        btn_avg_score.setStyleSheet('background-color: #4CAF50; color: black; font-weight: bold;')

        self.chart_tab.setLayout(layout)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GolfTracker()
    window.show()
    sys.exit(app.exec_())
