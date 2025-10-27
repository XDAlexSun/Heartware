"""
DCM — Deliverable 1 
==========================================================

HOW TO RUN
----------
RUN THROUGH IDLE, F5.
NEED PYQT5

MAIN FEATURES
-------------------
- Register/Login with a limit of 10 users (stored locally in JSON; passwords hashed)
- Dashboard  shows comms/device/telemetry state and lets you pick a pacing mode
- Opens a Mode Editor (AOO/VOO/AAI/VVI) with customizable parameters within provided ranges and steps:
    * URL, LRL, A/V Amplitude (+On/Off), A/V Pulse Width, Refractory Period, Hysteresis and Rate Smoothing Up/Down
- Summary tab that mirrors the current parameter set
- Egram (D2) tab with a live simulated 3-trace viewer and option ti save PNG 
- Exports: 
  • File → Reports → Bradycardia Parameters Report…  (PDF)
  • File → Reports → Temporary Parameters Report…    (PDF)
  • File → Export Saved Params JSON…                 (JSON backup)
- Simulator menu to change states: Comms Connected, Device Changed, Device ID, Telemetry (OK/Out of Range/Noise)
- Utilities → About… and Utilities → Set Clock… (change device time shown in status bar)

DATA IN LOCAL JSON FILE: dcm_d1_file.json
{
  "users":  [ {"username": "<name>", "password_hash": "<sha256>"}, ... ],
  "params": { "<user>:<mode>": { ... parameter dict ... }, ... }
}

Saved parameters are per-(user, mode). Unsaved (current) values are taken directly from the widgets.

WIDGETS emit signals, METHODS connected to them button.clicked.connect(self.on_click), button.clicked signal

Navigation works by passing CALLBACKS between pages
+ asking MainWindow for global state (active user, simulator flags).


MAP TO FOLLOW (Objects & Responsibilities)
------------------------------------------
MainWindow (QMainWindow)
  ├─ Database                   → JSON read/write for users & params
  ├─ QStackedWidget (self.stack)
  │   ├─ LoginPage              → Register/Login. On success calls MainWindow._on_login_ok(name)
  │   ├─ DashboardPage          → Shows status labels + 4 mode buttons; calls MainWindow._open_mode_editor(mode)
  │   └─ ModeEditorPage         → Parameter widgets, Summary, Egram
  │        ├─ Uses Database     → save_params()/load_params() for (user, mode)
  │        └─ D1EgramView       → Live simulated traces; Start/Stop/Save PNG
  ├─ Menus
  │   ├─ File → Reports         → _export_brady_params_report(), _export_temp_params_report()
  │   ├─ File → Export JSON     → _export_all_json()
  │   ├─ Simulator              → _toggle_comms(), _toggle_device_changed(),
  │   │                           _set_device_id(), _set_telemetry("ok|out_of_range|noise")
  │   └─ Utilities              → _show_about(), _set_clock_dialog()
  └─ QStatusBar                 → Shows Comms | Device ID | Change state | Telemetry | Clock

"""

# =========================
# 1) Standard library imports
# =========================
import json # read/write JSON file (our tiny database)
import os # file paths and existence checks
import hashlib # SHA256 to hash passwords (simple classroom security)
from typing import Dict, Any, List, Optional  # type hints (optional but helpful)

# =========================
# 2) PyQt5 GUI imports
# =========================
from PyQt5.QtCore import Qt, QSize, QDateTime, QTimer # QtCore has core types; Qt namespace
from PyQt5.QtGui import QIcon, QValidator, QTextDocument # QtGui has visual stuff (icons, validators)
from PyQt5.QtPrintSupport import QPrinter # printsupport for pdfs, 3.2.4


from PyQt5.QtGui import QIcon, QValidator 

from PyQt5.QtWidgets import (
    QApplication, # the global GUI application object (event loop here)
    QWidget, # base class for most things shown on screen
    QMainWindow, # main window with menu/status/central widget
    QStackedWidget, # "deck" to switch between multiple pages
    QVBoxLayout, # vertical layout manager
    QHBoxLayout, # horizontal layout manager
    QLabel, # shows text or rich text (HTML)
    QLineEdit, # single-line text input
    QPushButton, # clickable button
    QMessageBox, # modal dialogs (info/warning/errors)
    QFormLayout, # 2-column "Label : Field" layout
    QSpinBox, # integer input with arrows + typing
    QDoubleSpinBox, # floating-point input with arrows + typing
    QComboBox, # drop-down selection list
    QGroupBox, # box with a title around a group of widgets
    QTabWidget, # tabs (parameters / summary / egram)
    QFileDialog, # file picker dialog
    QAction, # menu item (can be clickable, checkable)
    QActionGroup, # group of actions (useful for radio-button behavior)
    QStatusBar,  # one-line bar at bottom for status text
    QDialog,
    QDialogButtonBox,
    QDateTimeEdit
)

# =========================
# 3) FILE STORAGE!!!!!!!!!!!
# =========================
DB_FILE = "dcm_d1_file.json" # JSON file path to store users + saved parameters
MAX_USERS = 10 # allow at most 10 users locally

class Database:
    """
    We store JSON like:
    {
      "users": [{"username": "alice", "password_hash": "..."}, ...],
      "params": {"alice:VVI": {...}, "alice:AAI": {...}, ...}
    }
    """

    def __init__(self, path: str): #string, path for location of json file, will be in current working directory
        self.path = path # saving incoming string path on the object itself as self.path so it can be used later

        # true if file exists, if not flips it
        if not os.path.exists(self.path):  # if file doesn't exist yet
            self._write({"users": [], "params": {}}) # create with empty structure

    # private read helper _ internal
    def _read(self) -> Dict[str, Any]:
        with open(self.path, "r", encoding="utf-8") as f: # open file for reading
            return json.load(f)  # parse JSON -> Python dict

    # private write helper
    def _write(self, data: Dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as f: # open for writing (overwrite)
            json.dump(data, f, indent=2) # dump dict -> json

    # public: count how many users are registered
    def user_count(self) -> int:
        return len(self._read()["users"])

    # public: add a new user (case-insensitive unique usernames; enforce MAX_USERS)
    def add_user(self, username: str, password_hash: str) -> bool:
        data = self._read()
        # check duplicate ignoring case (use .lower() on both sides)
        if any(u["username"].lower() == username.lower() for u in data["users"]):
            return False
        # enforce maximum user count
        if len(data["users"]) >= MAX_USERS:
            return False
        # append new record and save to file
        data["users"].append({"username": username, "password_hash": password_hash})
        self._write(data)
        return True

    # public: verify login (username+hash must match a stored record)
    def verify_user(self, username: str, password_hash: str) -> bool:
        data = self._read()
        user_lc = username.lower()
        for user in data["users"]:
            if user["username"].lower() == user_lc and user["password_hash"] == password_hash:
                return True
        return False

    # public: save parameter dict under key "<user>:<mode>"
    def save_params(self, username: str, mode: str, params: Dict[str, Any]) -> None:
        data = self._read()
        key = f"{username}:{mode}" # composite key simple lookup
        data["params"][key] = params
        self._write(data)

    # public: load parameter dict; if none saved, return empty dict
    def load_params(self, username: str, mode: str) -> Dict[str, Any]:
        data = self._read()
        return data["params"].get(f"{username}:{mode}", {})

# =========================
# 4) Parameters
# =========================

# LRL (Lower Rate Limit) has piecewise steps depending on the range
LRL_SEGMENTS = [
    (30, 50, 5),   # 30, 35, 40, 45, 50
    (50, 90, 1),   # 50..90 (1 step)
    (90, 175, 5),  # 90, 95, ..., 175
]
# URL (Upper Rate Limit): 50–175 step 5
URL_MIN, URL_MAX, URL_STEP = 50, 175, 5

# Amplitude choices: "Off", 0.5–3.2 (0.1 step) and 3.5–7.0 (0.5 step)
AMP_LOW_MIN,  AMP_LOW_MAX,  AMP_LOW_STEP  = 0.5, 3.2, 0.1 # SHOULD BE FOR ATRIAL
AMP_HIGH_MIN, AMP_HIGH_MAX, AMP_HIGH_STEP = 3.5, 7.0, 0.5 # SHOULD BE VENT

# Pulse width choices: 0.05 ms single value, then 0.1–1.9 in 0.1 steps
PW_SEGMENTS = [
    (0.05, 0.1, 0.05),  # only 0.05
    (0.1, 1.9, 0.1),
]

# Refractory periods: 150–500 ms in 10 ms steps
REF_MIN, REF_MAX, REF_STEP = 150, 500, 10

# D1 modes (used to generate buttons and choices)
MODES = ["AOO", "VOO", "AAI", "VVI"]

# Hysteresis:
# - enabled only for inhibiting modes (AAI, VVI)
# - when enabled, the Hysteresis Rate Limit (HRL) uses the same choices as LRL
HYSTERESIS_STATES = ["Off", "On"]

# Rate Smoothing:
# - two programmable parameters Up and Down
# - options Off, 3, 6, 9, 12, 15, 18, 21, 25 %
RATE_SMOOTH_CHOICES = ["Off", "3%", "6%", "9%", "12%", "15%", "18%", "21%", "25%"]

# -------------------------
# About / Utility constants
# -------------------------
APP_MODEL_NUMBER   = "DCM D1"
APP_SOFTWARE_REV   = "D1"
APP_SERIAL_NUMBER  = "SN"
APP_INSTITUTION    = "McMaster University"

# =========================
# 5) helpers
# =========================
def hash_password(plain: str) -> str: # chatgpt
    """
    Turn a plaintext password into a SHA256 hex string.
    - .encode("utf-8") converts Python str to bytes
    - hashlib.sha256(...).hexdigest() returns a hex string like 'a9f...'
    """
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()

def build_allowed_lrl(segments) -> List[int]: # doesnt need float range bc whole numbers
    """
    build allowed integer LRL values by merging each (lo,hi,step) segment
    """
    vals = set() # set prevents duplicates around edges 
    for lo, hi, st in segments:
        vals.update(range(lo, hi + 1, st))  # +1 makes hi inclusive
    return sorted(vals)


def build_allowed_url(min_v: int, max_v: int, step: int) -> List[int]: # doesnt need float range bc whole numbers
    """simple inclusive range for URL values"""
    return list(range(min_v, max_v + 1, step))

def build_pw_values() -> List[float]:
    """
    build pulse-width allowed values from the PW_SEGMENTS spec.
    uses set to avoid duplicates; sorted to make stepping nice.
    """
    vals = set()
    for lo, hi, st in PW_SEGMENTS:
        x = lo
        while x <= hi + 1e-12: # include hi
            vals.add(round(x, 2)) # keep two decimals for the 0.05
            x += st
    return sorted(vals)

def _percent_to_int(s: str) -> int:
    """'Off' -> 0, '12%' -> 12"""
    return 0 if s == "Off" else int(s.rstrip("%"))

def _int_to_percent(v: int) -> str:
    """0 -> 'Off', 12 -> '12%'"""
    return "Off" if v == 0 else f"{int(v)}%"


# all allowed lists to be used by Widgets
ALLOWED_LRL = build_allowed_lrl(LRL_SEGMENTS)
ALLOWED_URL = build_allowed_url(URL_MIN, URL_MAX, URL_STEP)
PW_VALUES   = build_pw_values()
REF_VALUES  = list(range(REF_MIN, REF_MAX + 1, REF_STEP))


# =========================
# 6) CUSTOM WIDGETS FOR PARAMETERS!!!!!!
# =========================
class LRLSpinBox(QSpinBox):
    """Integer spinbox for LRL; enforces allowed piecewise values"""

    def __init__(self, parent=None):
        super().__init__(parent) # call base class constructor
        self.allowed = ALLOWED_LRL # creating self.allowed to use ALLOWED_LRL in this class
        self.setRange(min(self.allowed), max(self.allowed)) # min/max bounds keep in list
        self.setSuffix(" ppm") # add " ppm" after number
        self.setValue(60) # default value 60, this is also the nominal value

    def stepBy(self, steps: int) -> None:
        """
        called when user presses the up/down arrows; override it to jump within self.allowed
        so it won't just go +1/-1
        """
        current = self.value()
        try:
            idx = self.allowed.index(current) # find current position
        except ValueError:
            # if user typed in-between value, find the nearest index
            idx = min(range(len(self.allowed)), key=lambda i: abs(self.allowed[i] - current))
        idx = max(0, min(len(self.allowed) - 1, idx + steps))  # clamp to ends of list
        self.setValue(self.allowed[idx]) # set the new value

    def validate(self, text: str, pos: int):
        """
        controls whats accepted when you type in the box
        validator states!
        intermediate = allow typing to continue, so like 6 towards 60
        invalid = stops typing
        acceptable = what we want, in range
        """
        # strip the suffix to check number
        raw = text.replace(" ppm", "").strip()
        if raw == "":
            return (QValidator.Intermediate, text, pos) #space/empty, allow

        # if it's not an integer yet, let the user keep typing
        if not raw.lstrip("-").isdigit():
            return (QValidator.Intermediate, text, pos)

        val = int(raw)

        # while typing up to the minimum (ex 6 on the way to 60), allow it
        if val < self.minimum():
            return (QValidator.Intermediate, text, pos)

        # above maximum is invalid
        if val > self.maximum():
            return (QValidator.Invalid, text, pos)

        # inside bounds: only exact allowed values are acceptable
        if val in self.allowed:
            return (QValidator.Acceptable, text, pos)

        # within numeric bounds but not an allowed discrete value
        return (QValidator.Invalid, text, pos)

class URLSpinBox(QSpinBox):
    """SAME CONCEPT AS LRL!! except using allowed url"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.allowed = ALLOWED_URL # multiples of 5
        self.setRange(min(self.allowed), max(self.allowed))
        self.setSuffix(" ppm")
        self.setValue(120)

    def stepBy(self, steps: int) -> None:
        current = self.value()
        try:
            idx = self.allowed.index(current)
        except ValueError:
            # if user typed in-between value, find the nearest legal index
            idx = min(range(len(self.allowed)), key=lambda i: abs(self.allowed[i] - current)) # clamp to [0, last]
        idx = max(0, min(len(self.allowed) - 1, idx + steps)) # new value
        self.setValue(self.allowed[idx])

    def validate(self, text: str, pos: int):
        # strip the suffix the widget appends
        raw = text.replace(" ppm", "").strip()
        if raw == "":
            return (QValidator.Intermediate, text, pos)

        # if it's not an integer yet, let the user keep typing
        if not raw.lstrip("-").isdigit():
            return (QValidator.Intermediate, text, pos)

        val = int(raw)

        # while typing up to the minimum (ex 6 on the way to 60), allow it
        if val < self.minimum():
            return (QValidator.Intermediate, text, pos)

        # above maximum is invalid (you could also choose Intermediate if you prefer)
        if val > self.maximum():
            return (QValidator.Invalid, text, pos)

        # inside bounds: only exact allowed values are acceptable
        if val in self.allowed:
            return (QValidator.Acceptable, text, pos)

        # within numeric bounds but not an allowed discrete value
        return (QValidator.Invalid, text, pos)

class PWSpinBox(QDoubleSpinBox):
    """double spinbox for pulse width, 0.05 then 0.1–1.9 stepping"""
    # used by ModeEditorPage -> self.a/v_pw
    # values retrieved and saved in _collect_params()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.allowed = PW_VALUES
        self.setRange(min(self.allowed), max(self.allowed))
        self.setDecimals(2) # show two decimals (0.05)
        self.setSingleStep(0.05) 
        self.setSuffix(" ms")
        self.setValue(0.4) # nominal value

    def stepBy(self, steps: int) -> None: # same pattern
        """jump along our allowed values list rather than raw 0.05 steps"""
        cur = self.value()
        try:
            idx = self.allowed.index(cur)
        except ValueError:
            idx = min(range(len(self.allowed)), key=lambda i: abs(self.allowed[i] - cur))
        idx = max(0, min(len(self.allowed) - 1, idx + steps))
        self.setValue(self.allowed[idx])

    def validate(self, text: str, pos: int): # same pattern
        """accept only exact members of PW_VALUES""" 
        try:
            val = float(text.replace(" ms", "").strip())
        except ValueError:
            return (QValidator.Intermediate, text, pos)
        if any(abs(val - a) < 1e-9 for a in self.allowed):
            return (QValidator.Acceptable, text, pos)
        if self.minimum() <= val <= self.maximum():
            return (QValidator.Invalid, text, pos)
        return (QValidator.Invalid, text, pos)

class RefPeriodSpinBox(QSpinBox):
    """ppinbox for ARP/VRP"""
    # no floats no validate . saved and loaded like other stuff
    # used by ModeEditorPage -> self.a/vrp
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(REF_MIN, REF_MAX)
        self.setSingleStep(REF_STEP)
        self.setSuffix(" ms")
        self.setValue(250)


class AmplitudeWidget(QWidget):
    """
    widget w/ [Label] [Off/On dropdown] [Voltage spinbox]
    - If "Off" selected -> .value() returns "Off" (string)
    - If "On" selected  -> .value() returns a float snapped to valid step range

    A and V different ranges
    """
    # ModeEditorPage creates self.a_amp, self.v_amp = AmplitudeWidget("")
    # _collect_params() calls .value() on each
    # _apply_params_to_widgets() calls .setValue(...) on each

    def __init__(self, label_text: str,
                 min_v: float, max_v: float, step_v: float, default_v: float, # range and number shown when on
                 parent=None): # defining values
        super().__init__(parent)

        # remember range so snapping knows what to do
        self._min_v = float(min_v)
        self._max_v = float(max_v)
        self._step_v = float(step_v)

        # build a horizontal row: label | combo | spin
        row = QHBoxLayout(self) # 'self' is the container widget
        row.setContentsMargins(0, 0, 0, 0) # no extra padding inside

        self.label = QLabel(label_text) # ex "Atrial Amplitude:" 
        self.state_combobox = QComboBox() # dropdown with "Off"/"On"
        self.state_combobox.addItems(["Off", "On"]) # add the two choices

        self.volt_spinbox = QDoubleSpinBox() # voltage input
        self.volt_spinbox.setDecimals(1) # show 1 decimal place
        self.volt_spinbox.setRange(self._min_v, self._max_v)  # chamber-specific range
        self.volt_spinbox.setSingleStep(self._step_v) # chamber-specific step
        self.volt_spinbox.setSuffix(" V") # add suffix
        self.volt_spinbox.setValue(default_v) # starting value

        # react when combo changes (disable/enable the spinbox)
        self.state_combobox.currentIndexChanged.connect(self._update_enabled_state) # ref to _update_enabled_state
        self._update_enabled_state() # set initial enabled state

        # add all three widgets into the row
        row.addWidget(self.label)
        row.addWidget(self.state_combobox)
        row.addWidget(self.volt_spinbox)

    def _update_enabled_state(self) -> None:
        """enable the number field only if 'On' is selected"""
        self.volt_spinbox.setEnabled(self.state_combobox.currentText() == "On")

    def value(self):
        """return either 'Off' (str) or a float rounded to grid"""
        if self.state_combobox.currentText() == "Off":
            return "Off"

        v = float(self.volt_spinbox.value()) # whats in the box rn, can be anything, need to snap/modify
        # snap to the nearest limit defined by (min, step)
        steps = round((v - self._min_v) / self._step_v)
        snapped = round(self._min_v + steps * self._step_v, 1)
        # clamp 
        snapped = max(self._min_v, min(self._max_v, snapped))
        return snapped

    ## ^^ basically whats happening is taking the current value - minimum and dividing by the step
    ## ex. current (2.87 - min 0.5)/0.1 step = 23.7 round to 24 steps
    ## then add to min and multiply by step to get actual value of 2.9

    def setValue(self, val) -> None:
        """set widget value from saved data: 'Off' or number volt"""
        if val == "Off":
            self.state_combobox.setCurrentText("Off")
        else:
            self.state_combobox.setCurrentText("On")
            self.volt_spinbox.setValue(float(val))

# =========================
# 7) screens/pages inside the stacked widget
# =========================
class LoginPage(QWidget):
    """
    registration + login page.
    - receive 'db' (Database) and 'on_login_ok' (callback) from MainWindow*
    - when login succeeds, we call on_login_ok(username) to tell MainWindow
    """

    def __init__(self, db: Database, on_login_ok, parent=None): # depends on db
        super().__init__(parent) # build the QWidget base
        self.db = db # remember the database so we can query it
        self.on_login_ok = on_login_ok  # remember callback to MainWindow *

        page = QVBoxLayout(self) # vertical page layout
        page.addWidget(QLabel("<h2>DCM — Welcome!</h2>"))  # simple title

        # registration group (top)
        reg_group = QGroupBox("New user registration")
        reg_form = QFormLayout(reg_group) # label : field pairs inside the group

        self.reg_name = QLineEdit() # name input
        self.reg_pass = QLineEdit() # password input
        self.reg_pass.setEchoMode(QLineEdit.Password) # hide characters

        RegisterButton = QPushButton("Register")# button the user clicks to register
        RegisterButton.clicked.connect(self._handle_register)  # connect signal -> slot (method below)

        reg_form.addRow("Name:", self.reg_name)
        reg_form.addRow("Password:", self.reg_pass)
        reg_form.addRow(RegisterButton)

        # login group (bottom) 
        login_group = QGroupBox("Login")
        login_form = QFormLayout(login_group)

        self.login_name = QLineEdit()
        self.login_pass = QLineEdit()
        self.login_pass.setEchoMode(QLineEdit.Password)

        LoginButton = QPushButton("Login")
        LoginButton.clicked.connect(self._handle_login)

        login_form.addRow("Name:", self.login_name)
        login_form.addRow("Password:", self.login_pass)
        login_form.addRow(LoginButton)

        # add both groups to the page layout
        page.addWidget(reg_group)
        page.addWidget(login_group)
        page.addStretch(1) # spacing

    # slots (handlers) for the two buttons 
    def _handle_register(self) -> None:
        """validate inputs, enforce limits, then add user to db"""
        name = self.reg_name.text().strip()  # .text() gets the text; .strip() trims spaces
        pw   = self.reg_pass.text()
        if not name or not pw:
            QMessageBox.warning(self, "Missing info", "Please enter a name and password!")
            return
        if self.db.user_count() >= MAX_USERS:
            QMessageBox.critical(self, "Max user capacity reached", f"Maximum of {MAX_USERS} users stored.")
            return
        if not self.db.add_user(name, hash_password(pw)):  # returns False if duplicate or full
            QMessageBox.warning(self, "Registration failed!", "User exists or capacity reached.")
            return
        QMessageBox.information(self, "Success!", "Registration complete. Please log in.")
        self.reg_pass.clear()                 # clear password field for safety

    def _handle_login(self) -> None:
        """check user and pass against db; if success, notify MainWindow."""
        name = self.login_name.text().strip()
        pw   = self.login_pass.text()
        if self.db.verify_user(name, hash_password(pw)):
            self.on_login_ok(name)            # <- calls the callback passed from MainWindow
        else:
            QMessageBox.critical(self, "Login failed", "Invalid username or password.")


class DashboardPage(QWidget):
    """
    dashboard shows current device/comms state and mode buttons
    receive 'on_mode_click(mode)' callback to inform MainWindow which mode to open.
    """

    def __init__(self, on_mode_click, parent=None): # we call on_mode_click later in MainWindow._open_mode_editor
        super().__init__(parent)
        self.on_mode_click = on_mode_click  # remember the callback

        page = QVBoxLayout(self) # vertical page layout
        page.addWidget(QLabel("<h2>Device Controller–Monitor</h2>"))

        # row of status labels
        status = QHBoxLayout()
        self.label_comms = QLabel("Comms: <b>Not Connected</b>")
        self.label_device = QLabel("Device: <i>None</i>")
        self.label_changed = QLabel("Status: <b>Last Device OK</b>")
        self.label_telemetry = QLabel("Telemetry: <b>OK</b>")
        for w in (self.label_comms, self.label_device, self.label_changed, self.label_telemetry):
            status.addWidget(w)
            status.addSpacing(20) # small space between labels
        status.addStretch(1)
        page.addLayout(status)

        # row of modes (AOO/VOO/AAI/VVI)
        row = QHBoxLayout()
        for mode in MODES:
            ModeButton = QPushButton(mode) # text/label is the mode
            ModeButton.setMinimumWidth(120) # make them wide enough
            # lambda captures 'mode' into 'm' so each button calls with its own value
            ModeButton.clicked.connect(lambda _, m=mode: self.on_mode_click(m))
            row.addWidget(ModeButton)
        row.addStretch(1)
        page.addLayout(row)
        page.addStretch(1)

    # public methods called by MainWindow to update the labels
    def show_comms(self, connected: bool) -> None:
        self.label_comms.setText(f"Comms: <b>{'Connected' if connected else 'Not Connected'}</b>")

    def show_device(self, device_id: str) -> None:
        self.label_device.setText(f"Device: <b>{device_id or 'None'}</b>")

    def show_changed(self, changed: bool) -> None:
        self.label_changed.setText("Status: <b>Device Changed</b>" if changed else "Status: <b>Last Device OK</b>")

    def show_telemetry(self, state: str) -> None:
        mapping = {
            "ok": "Telemetry: <b>OK</b>",
            "out_of_range": "Telemetry: <b>Lost – Out of Range</b>",
            "noise": "Telemetry: <b>Lost – Noise</b>",
        }
        self.label_telemetry.setText(mapping.get(state, "Telemetry: <b>OK</b>"))

# EGRAM GRAPHS 3.2.5 
class D1EgramView(QWidget):
    """
    real-time egram viewer with random data
    click start tart to begin and stop to pause
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.timer = None # using qtimer, not running yet
        self.t = 0.0 # running time advanced on each tick
        self.dt = 0.02 # 0.02 s timestep or 50 Hz 1/0.02
        self.buffer_len = 400 # buffer 400 samples per trace
        self.atrialList = [] # empty lists for samples
        self.ventricularList = []
        self.surfaceList = []
        self.show_atrial = True # visibility
        self.show_ventricular = True
        self.show_surface = True

    def start(self):
        if self.timer is None: # if no timer make one
            from PyQt5.QtCore import QTimer
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick) # every time timer fires call _tick() to gen new data
            self.timer.start(int(self.dt * 1000)) # to ms

    def stop(self):
        if self.timer: # if timer running stop
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None

    def _tick(self):
        import math, random
        self.t += self.dt

        # generate random sinusoidal data (simple sinusoids + noise)
        atrial_data = 0.4 * math.sin(2 * math.pi * 1.5 * self.t) + 0.05 * random.uniform(-1, 1)
        ventricular_data = 0.8 * math.sin(2 * math.pi * 1.0 * self.t + 1.0) + 0.05 * random.uniform(-1, 1)
        surface_data = 0.6 * math.sin(2 * math.pi * 1.2 * self.t + 0.5) + 0.04 * random.uniform(-1, 1)

        self.atrialList.append(atrial_data) # append data to list
        self.ventricularList.append(ventricular_data)
        self.surfaceList.append(surface_data)

        if len(self.atrialList) > self.buffer_len:
            self.atrialList.pop(0)
            self.ventricularList.pop(0)
            self.surfaceList.pop(0)

        self.update() # trigger repaint

    def paintEvent(self, ev): # need to repaint
        from PyQt5.QtGui import QPainter, QPen, QColor
        from PyQt5.QtCore import QPointF, Qt

        p = QPainter(self)
        try:
            p.fillRect(self.rect(), self.palette().base()) # clear background using widget base colour

            w = self.width() # for layout math
            h = self.height()

            # 3 signal baselines
            row_h = h / 3.0 # divide widget into 3 horizontal bands, row_h each
            bases = [row_h * 0.5, row_h * 1.5, row_h * 2.5] # positions
            names = ["Atrial", "Ventricular", "Surface ECG"]
            colors = [QColor("red"), QColor("blue"), QColor("green")]
            series = [self.atrialList, self.ventricularList, self.surfaceList]
            shown = [self.show_atrial, self.show_ventricular, self.show_surface]

            for i in range(3): # for each bamd, set gray pen and draw horizontal baseline across width and lbel above baseline
                base = bases[i]
                p.setPen(QPen(Qt.gray))
                p.drawLine(0, int(base), w, int(base))
                p.drawText(5, int(base - 5), names[i])

                if not shown[i] or len(series[i]) < 2:
                    continue # skip drawing if trace hidden or not enough pts to draw line

                s = series[i] # list of samples
                step_x = w / max(1, len(s) - 1) # horizontal spacing between sequential points so the whole buffer spans the full width
                scale = row_h * 0.35
                pen = QPen(colors[i]) # design and colours
                pen.setWidth(2)
                p.setPen(pen)

                last = QPointF(0, base - scale * s[0]) # convert samples into pixels, x increase linear by step_x, y is base-scale*value. higher value above baseline
                for j in range(1, len(s)):
                    pt = QPointF(j * step_x, base - scale * s[j])
                    p.drawLine(last, pt)
                    last = pt
        finally:
            p.end() # finalize


# ABOUT !!!
class AboutDialog(QDialog): #QDialog popup windows, vs QWidget for normal page
    """
    'About' panel listing model, software rev, serial, institution. 3.2.3
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About DCM")
        lay = QFormLayout(self)
        lay.addRow("Application model number:", QLabel(APP_MODEL_NUMBER))
        lay.addRow("Software revision:",       QLabel(APP_SOFTWARE_REV))
        lay.addRow("DCM serial number:",       QLabel(APP_SERIAL_NUMBER))
        lay.addRow("Institution name:",        QLabel(APP_INSTITUTION))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok, parent=self)# ok button
        buttons.accepted.connect(self.accept)
        lay.addRow(buttons)


class SetClockDialog(QDialog): # popup
    """
    "The Set Clock function shall set the date and time of the device" 3.2.3
    """
    def __init__(self, current_DeviceTime: QDateTime, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Clock")
        lay = QFormLayout(self)

        self.dt_edit = QDateTimeEdit(current_DeviceTime) # picker widget internalized w current date/time
        self.dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss") # how it appears to user
        self.dt_edit.setCalendarPopup(True)

        lay.addRow("Device date/time:", self.dt_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self) # ok and cancel, Q handles layout
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addRow(buttons)

    def selected_datetime(self) -> QDateTime:
        return self.dt_edit.dateTime()


class ModeEditorPage(QWidget):
    """
    mode editor:
    - parameters tab: edit LRL, URL, A/V amplitude + width, ARP/VRP
    - summary tab: read-only summary of current values
    - egram (D2): placeholder text for next deliverable

    receives:
      db: Database     (for load/save)
      get_active_user: callable returning the username (or none)
    """

    def __init__(self, db: Database, get_active_user, parent=None):
        super().__init__(parent)
        self.db = db
        self.get_active_user = get_active_user
        self.current_mode: str = MODES[0] # default mode until changed

        # outer layout abd tavs
        page = QVBoxLayout(self)
        self.tabs = QTabWidget() # creates tabs along the top
        page.addWidget(self.tabs)

        # parameters tab
        self.tab_params = QWidget()
        self.tabs.addTab(self.tab_params, "Parameters")
        form = QFormLayout(self.tab_params) # two-column "Label : Widget"

        # choose mode at the top of the form
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODES)
        self.mode_combo.currentTextChanged.connect(self.set_mode)  # when user changes, call set_mode()
        form.addRow("Pacing Mode:", self.mode_combo)

        # widgets for each parameter
        self.lrl   = LRLSpinBox()
        self.url   = URLSpinBox()

        # atrial: 0.5–3.2 V, step 0.1  (default 3.0 V)
        self.atrial_amp = AmplitudeWidget("Atrial Amplitude:",
                                     AMP_LOW_MIN, AMP_LOW_MAX, AMP_LOW_STEP, 3.0)

        # ventricular: 3.5–7.0 V, step 0.5 (default 3.5 V)
        self.ventricular_amp = AmplitudeWidget("Ventricular Amplitude:",
                                     AMP_HIGH_MIN, AMP_HIGH_MAX, AMP_HIGH_STEP, 3.5)

        self.atrial_pw  = PWSpinBox()
        self.ventricular_pw  = PWSpinBox()
        self.arp   = RefPeriodSpinBox()
        self.vrp   = RefPeriodSpinBox()

        # add them to the form with labels where appropriate
        form.addRow("Lower Rate Limit (LRL):", self.lrl)
        form.addRow("Upper Rate Limit (URL):", self.url)
        form.addRow(self.atrial_amp)   # AmplitudeWidget includes its own label
        form.addRow("Atrial Pulse Width:", self.atrial_pw)
        form.addRow(self.ventricular_amp)
        form.addRow("Ventricular Pulse Width:", self.ventricular_pw)
        form.addRow("Atrial Refractory Period (ARP):", self.arp)
        form.addRow("Ventricular Refractory Period (VRP):", self.vrp)

        # hysteresis AAI/VVI only
        self.hysteresis_state = QComboBox()
        self.hysteresis_state.addItems(HYSTERESIS_STATES) # "Off" | "On"
        self.HysRateLimit = LRLSpinBox() # use same choices as LRL
        self.HysRateLimit.setEnabled(False) # only enabled when "On"

        # when user flips Off/On, enable/disable HRL field
        self.hysteresis_state.currentTextChanged.connect(
            lambda s: self.HysRateLimit.setEnabled(s == "On")
        )

        form.addRow("Hysteresis:", self.hysteresis_state)
        form.addRow("Hysteresis Rate Limit (HRL):", self.HysRateLimit)

        # rate Smoothing AAI/VVI only
        self.smooth_up = QComboBox()
        self.smooth_up.addItems(RATE_SMOOTH_CHOICES)
        self.smooth_down = QComboBox()
        self.smooth_down.addItems(RATE_SMOOTH_CHOICES)
        form.addRow("Rate Smoothing Up:", self.smooth_up)
        form.addRow("Rate Smoothing Down:", self.smooth_down)


        # buttons: save / revert
        buttons = QHBoxLayout()
        self.SaveButton = QPushButton("Save Parameters")
        self.RevertButton = QPushButton("Revert to Saved")
        self.SaveButton.clicked.connect(self._handle_save) # connect click -> save
        self.RevertButton.clicked.connect(self._handle_revert) # connect click -> revert
        buttons.addWidget(self.SaveButton)
        buttons.addWidget(self.RevertButton)
        buttons.addStretch(1)
        form.addRow(buttons)

        # SUMMARY
        self.tab_summary = QWidget()
        self.tabs.addTab(self.tab_summary, "Summary")
        summary_layout = QVBoxLayout(self.tab_summary)
        self.label_summary = QLabel("")  # will show HTML text with values
        summary_layout.addWidget(self.label_summary)
        summary_layout.addStretch(1)

        # EGRAM D2 TAB
        self.tab_egram = QWidget()
        self.tabs.addTab(self.tab_egram, "Egram (D2)")
        egram_layout = QVBoxLayout(self.tab_egram)

        # the viewer
        self.egram_view = D1EgramView()
        egram_layout.addWidget(self.egram_view)

        # controls
        EgramButtons = QHBoxLayout()
        self.StartEgramButton = QPushButton("Start")
        self.StopEgramButton  = QPushButton("Stop")
        self.SaveEgramButton  = QPushButton("Save Strip (PNG)")
        self.StartEgramButton.clicked.connect(self.egram_view.start)
        self.StopEgramButton.clicked.connect(self.egram_view.stop)
        self.SaveEgramButton.clicked.connect(self._save_egram_png)
        EgramButtons.addWidget(self.StartEgramButton)
        EgramButtons.addWidget(self.StopEgramButton)
        EgramButtons.addWidget(self.SaveEgramButton)
        EgramButtons.addStretch(1)
        egram_layout.addLayout(EgramButtons)


        # initialize the page to the default mode (enable/disable fields + load saved if any)
        self.set_mode(self.current_mode)

        # after: self.tabs.addTab(self.tab_egram, "Egram (D2)")
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, idx: int) -> None:
        # auto start when the Egram tab is visible; stop when leaving
        if self.tabs.widget(idx) is self.tab_egram:
            self.egram_view.start()
        else:
            self.egram_view.stop()


    # public method: MainWindow calls this before showing the page
    def set_mode(self, mode: str) -> None: # remember newly selected mode
        """switch editor to a given mode; enable correct chamber fields and load saved data"""
        self.current_mode = mode
        # keep the combo box synchronized without re-triggering this method recursively, dont trigger currentTextChanged
        if self.mode_combo.currentText() != mode:
            old = self.mode_combo.blockSignals(True)  # temporarily silence signals
            self.mode_combo.setCurrentText(mode) # set the visible value
            self.mode_combo.blockSignals(old) # restore signal behavior

        # enable only the chamber widgets that make sense for this mode, booleans true
        
        atrial_on = mode in ("AOO", "AAI")
        ventricular_on = mode in ("VOO", "VVI")
        inhibiting  = mode in ("AAI", "VVI")   # hysteresis + smoothing apply here
        
        #enabling amp depending on the modes
        self.atrial_amp.setEnabled(atrial_on); self.atrial_pw.setEnabled(atrial_on); self.arp.setEnabled(atrial_on)
        self.ventricular_amp.setEnabled(ventricular_on); self.ventricular_pw.setEnabled(ventricular_on); self.vrp.setEnabled(ventricular_on)

        # hysteresis + smoothing
        self.hysteresis_state.setEnabled(inhibiting) # on/enabled when inhibiting
        self.HysRateLimit.setEnabled(inhibiting and self.hysteresis_state.currentText() == "On")
        self.smooth_up.setEnabled(inhibiting)
        self.smooth_down.setEnabled(inhibiting)

        # load any saved params for the active user+mode; if none, keep current values
        self._handle_revert()

    # pulls current values from widgets into a plain dict ready for saving/export. at modes
    def _collect_params(self) -> Dict[str, Any]:
        return {
            "mode": self.current_mode,
            "LRL_ppm": self.lrl.value(),
            "URL_ppm": self.url.value(),
            "AtrialAmplitude_V": self.atrial_amp.value(),
            "AtrialPulseWidth_ms": round(self.atrial_pw.value(), 2),
            "VentricularAmplitude_V": self.ventricular_amp.value(),
            "VentricularPulseWidth_ms": round(self.ventricular_pw.value(), 2),
            "ARP_ms": self.arp.value(),
            "VRP_ms": self.vrp.value(),
            
            "Hysteresis": self.hysteresis_state.currentText(), # "Off"/"On"
            "HRL_ppm": self.HysRateLimit.value(), # used when Hysteresis == "On"
            "RateSmoothingUp_percent": _percent_to_int(self.smooth_up.currentText()),
            "RateSmoothingDown_percent": _percent_to_int(self.smooth_down.currentText()),
        }

    # apply a dict of params back onto the widgets, use for revert
    def _apply_params_to_widgets(self, p: Dict[str, Any]) -> None:
        self.lrl.setValue(p.get("LRL_ppm", self.lrl.value()))
        self.url.setValue(p.get("URL_ppm", self.url.value()))
        self.atrial_amp.setValue(p.get("AtrialAmplitude_V", self.atrial_amp.value()))
        self.atrial_pw.setValue(p.get("AtrialPulseWidth_ms", self.atrial_pw.value()))
        self.ventricular_amp.setValue(p.get("VentricularAmplitude_V", self.ventricular_amp.value()))
        self.ventricular_pw.setValue(p.get("VentricularPulseWidth_ms", self.ventricular_pw.value()))
        self.arp.setValue(p.get("ARP_ms", self.arp.value()))
        self.vrp.setValue(p.get("VRP_ms", self.vrp.value()))

        # NEW fields
        self.hysteresis_state.setCurrentText(p.get("Hysteresis", self.hysteresis_state.currentText()))
        # enable/disable HRL based on state
        self.HysRateLimit.setEnabled(self.hysteresis_state.currentText() == "On")
        self.HysRateLimit.setValue(p.get("HRL_ppm", self.HysRateLimit.value()))
        self.smooth_up.setCurrentText(_int_to_percent(p.get("RateSmoothingUp_percent", _percent_to_int(self.smooth_up.currentText()))))
        self.smooth_down.setCurrentText(_int_to_percent(p.get("RateSmoothingDown_percent", _percent_to_int(self.smooth_down.currentText()))))


    # EGRAM GRAPH PHOTOS 3.2.5
    def _save_egram_png(self) -> None:
        # self parent, dialog title, suggested default file name, file type filter only shows png returns selected path, type
        path, _ = QFileDialog.getSaveFileName(self, "Save Egram Snapshot", "egram.png", "PNG Files (*.png)")
        if not path:
            return
        screenshot = self.egram_view.grab()
        photoTaken = screenshot.save(path, "PNG")
        if photoTaken:
            QMessageBox.information(self, "Saved!", f"Egram snapshot saved to:\n{path}")
        else:
            QMessageBox.warning(self, "Error!", "Could not save the image.")


    # rebuild the HTML text for summary tab
    def _refresh_summary(self) -> None:
        p = self._collect_params()
        lines = [
            f"<b>Mode:</b> {p['mode']}",
            f"<b>LRL:</b> {p['LRL_ppm']} ppm",
            f"<b>URL:</b> {p['URL_ppm']} ppm",
            f"<b>Atrial:</b> Amp {p['AtrialAmplitude_V']} V, PW {p['AtrialPulseWidth_ms']} ms",
            f"<b>Ventricular:</b> Amp {p['VentricularAmplitude_V']} V, PW {p['VentricularPulseWidth_ms']} ms",
            f"<b>ARP:</b> {p['ARP_ms']} ms, <b>VRP:</b> {p['VRP_ms']} ms",
        ]
        # hysteresis params for aai and vvi
        if self.current_mode in ("AAI", "VVI"):
            lines.append(f"<b>Hysteresis:</b> {p['Hysteresis']}"
                         + (f", HRL {p['HRL_ppm']} ppm" if p['Hysteresis']=='On' else ""))
            lines.append(f"<b>Rate Smoothing:</b> Up {_int_to_percent(p['RateSmoothingUp_percent'])}, "
                         f"Down {_int_to_percent(p['RateSmoothingDown_percent'])}")
        self.label_summary.setText("<br>".join(lines))

    def _defaults(self, mode: str) -> Dict[str, Any]:
        """general defaults based on nominal values, to refer back to"""
        base = {
            "LRL_ppm": 60,
            "URL_ppm": 120,
            "AtrialPulseWidth_ms": 0.40,
            "VentricularPulseWidth_ms": 0.40,
            "ARP_ms": 250,
            "VRP_ms": 320,
            "Hysteresis": "Off",
            "HRL_ppm": 60,
            "RateSmoothingUp_percent": 0,
            "RateSmoothingDown_percent": 0,
        }
        # only amplitudes depend on the mode, rest general
        base["AtrialAmplitude_V"]      = 3.0 if mode in ("AOO", "AAI") else "Off"
        base["VentricularAmplitude_V"] = 3.5 if mode in ("VOO", "VVI") else "Off"
        return base

    def _apply_defaults_for_mode(self, mode: str) -> None:
        """write defaults into the widgets (go back to when nothing saved)"""
        d = self._defaults(mode)
        self.lrl.setValue(d["LRL_ppm"])
        self.url.setValue(d["URL_ppm"])
        self.atrial_amp.setValue(d["AtrialAmplitude_V"])
        self.atrial_pw.setValue(d["AtrialPulseWidth_ms"])
        self.ventricular_amp.setValue(d["VentricularAmplitude_V"])
        self.ventricular_pw.setValue(d["VentricularPulseWidth_ms"])
        self.arp.setValue(d["ARP_ms"])
        self.vrp.setValue(d["VRP_ms"])
        self.hysteresis_state.setCurrentText(d["Hysteresis"])
        self.HysRateLimit.setEnabled(self.hysteresis_state.currentText() == "On")
        self.HysRateLimit.setValue(d["HRL_ppm"])
        self.smooth_up.setCurrentText(_int_to_percent(d["RateSmoothingUp_percent"]))
        self.smooth_down.setCurrentText(_int_to_percent(d["RateSmoothingDown_percent"]))


    # SAVE!!!!!!!!!!
    def _handle_save(self) -> None:
        user = self.get_active_user()
        if not user:
            QMessageBox.warning(self, "No user", "Please log in first.")
            return
        # safety: LRL should not exceed URL
        if self.lrl.value() > self.url.value():
            QMessageBox.warning(self, "Check Parameters!", "LRL must be <= URL.")
            return
        params = self._collect_params()
        self.db.save_params(user, self.current_mode, params)
        QMessageBox.information(self, "Saved", f"Parameters saved for {user} [{self.current_mode}].")
        self._refresh_summary()


    # REVERT!!!! (also called by set_mode)
    def _handle_revert(self) -> None:
        user = self.get_active_user()
        saved = self.db.load_params(user, self.current_mode) if user else {}
        if saved:
            self._apply_params_to_widgets(saved)
        else:
            # no saved params, go to default
            self._apply_defaults_for_mode(self.current_mode)
        self._refresh_summary()


# =========================
# 8) Egram container (for D2)
# =========================
class EgramData:
    """Egram page placeholder for streaming data in D2"""
    def __init__(self, time_ms: List[int], atrial_mv: List[float], ventricular_mv: List[float]):
        self.time_ms = time_ms # time in ms
        self.atrial_mv = atrial_mv # in mv
        self.ventricular_mv = ventricular_mv

    def __repr__(self) -> str: # printing in debug contexts
        return f"EgramData(n_samples={len(self.time_ms)})"


# =========================
# 9) Main application window (owns pages + menus + status bar)
# =========================
class MainWindow(QMainWindow):
    """
    MainWindow is the top-level frame:
      - creates a QStackedWidget to hold three pages
      - wires callbacks between pages (login -> dashboard -> editor)
      - hosts "Simulator" menu to flip comms/device/telemetry flags
      - shows status bar text based on those flags
    """

    def __init__(self):
        super().__init__()  # QMainWindow init
        self.setWindowTitle("DCM — Deliverable 1")
        self.resize(900, 600)

        # global app state
        self.db = Database(DB_FILE) # database instance pointing at json shared to children
        self.active_user: Optional[str] = None  # None until someone logs in

        # simulated states (D1: no real hardware)
        self.comms_connected = False
        self.device_id = ""
        self.device_changed = False
        self.telemetry_state = "ok"  # one of "ok" | "out_of_range" | "noise"

        # device clock 3.2.3 #2
        self.device_clock = QDateTime.currentDateTime()
        
        # creates a QStackedWidget (a deck where exactly one “page” is shown).
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # create the pages and pass callbacks/DB as needed
        self.page_login = LoginPage(self.db, self._on_login_ok)
        self.page_dash  = DashboardPage(self._open_mode_editor)
        self.page_edit  = ModeEditorPage(self.db, self._get_active_user) # active user?

        # add all pages to the stack 
        for p in (self.page_login, self.page_dash, self.page_edit):
            self.stack.addWidget(p)

        self.stack.setCurrentWidget(self.page_login)  # start on login page

        # status bar at the bottom 
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._refresh_status_bar() # fills w initial status text

        # build top menu bar ("File", "Simulator")
        self._build_menus()

    # build menus and wire actions to methods
    def _build_menus(self) -> None:
        MenuBar = self.menuBar() # QMainWindow gives us a menu bar

        # file menu (export / reports / quit)
        menu_file = MenuBar.addMenu("File")

        # reports submenu as per 3.2.4 1,2
        menu_reports = menu_file.addMenu("Reports")
        action_r1 = QAction("Bradycardia Parameters Report…", self)
        action_r2 = QAction("Temporary Parameters Report…", self)
        action_r1.triggered.connect(self._export_brady_params_report) # when clicked generate pdf
        action_r2.triggered.connect(self._export_temp_params_report)
        menu_reports.addAction(action_r1)
        menu_reports.addAction(action_r2)

        action_export = QAction("Export Saved Params JSON…", self) # export json
        action_export.triggered.connect(self._export_all_json)
        menu_file.addAction(action_export)

        menu_file.addSeparator() # visual separator line in menu
        action_quit = QAction("Quit", self)
        action_quit.triggered.connect(self.close)
        menu_file.addAction(action_quit)

        # simulator menu (toggles and radio options for telemetry)
        menu_sim = MenuBar.addMenu("Simulator")

        # checkable action behaves like a checkbox in a menu
        self.action_comms = QAction("Toggle Comms Connected", self, checkable=True)
        self.action_comms.triggered.connect(self._toggle_comms)
        menu_sim.addAction(self.action_comms)

        self.action_changed = QAction("Toggle Device Changed", self, checkable=True)
        self.action_changed.triggered.connect(self._toggle_device_changed)
        menu_sim.addAction(self.action_changed)

        self.action_set_device = QAction("Set Device ID…", self)
        self.action_set_device.triggered.connect(self._set_device_id)
        menu_sim.addAction(self.action_set_device)

        # radio group for telemetry  ok default
        self.telemetry_group = QActionGroup(self)
        self.telemetry_group.setExclusive(True)  # makes them mutual-exclusive

        self.action_tel_ok = QAction("Telemetry OK", self, checkable=True)
        self.action_tel_oor = QAction("Loss: Out of Range", self, checkable=True)
        self.action_tel_noise = QAction("Loss: Noise", self, checkable=True)
        self.action_tel_ok.setChecked(True) # default selection

        # utilities menu (about/set clock)
        menu_utilities = MenuBar.addMenu("Utilities")

        action_about = QAction("About…", self)
        action_about.triggered.connect(self._show_about)
        menu_utilities.addAction(action_about)

        action_clock = QAction("Set Clock…", self)
        action_clock.triggered.connect(self._set_clock_dialog)
        menu_utilities.addAction(action_clock)

        # put actions in the group + menu
        for a in (self.action_tel_ok, self.action_tel_oor, self.action_tel_noise):
            self.telemetry_group.addAction(a)
            menu_sim.addAction(a)

        # connect each radio action to a lambda that sets the string state
        self.action_tel_ok.triggered.connect(lambda: self._set_telemetry("ok"))
        self.action_tel_oor.triggered.connect(lambda: self._set_telemetry("out_of_range"))
        self.action_tel_noise.triggered.connect(lambda: self._set_telemetry("noise"))

    #file menu handler: export our JSON DB to a chosen file path
    def _export_all_json(self) -> None: # opens save file dialog, dest is full chosen path or empty if canceled
        dest, _ = QFileDialog.getSaveFileName(self, "Export database JSON", "dcm_params.json")
        if not dest:  # user hit cancel
            return # exit
        with open(DB_FILE, "r", encoding="utf-8") as source, open(dest, "w", encoding="utf-8") as out:
            out.write(source.read())
        QMessageBox.information(self, "Exported", f"Saved to {dest}")
        # ^^ source: current database file on disk, out is file user picked in dialog

    # PNGS 3.2.4
    def _current_params(self) -> Optional[Dict[str, Any]]:
        """get currently shown editor parameters, or None if no user"""
        user = self._get_active_user()
        if not user:
            return None
        return self.page_edit._collect_params() # ask modeeditorpage to collect whats currently in widgets and return dict

    def _report_header_html(self, report_name: str) -> str:
        # spec header fields
        now = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss") # get current time as string
        return f"""
        <h2 style="margin-bottom:2px;">{report_name}</h2> 
        <hr>
        <table cellspacing="4">
          <tr><td><b>Institution:</b></td><td>{APP_INSTITUTION}</td></tr>
          <tr><td><b>Printed:</b></td><td>{now}</td></tr>
          <tr><td><b>DCM Model/Version:</b></td><td>{APP_MODEL_NUMBER} / {APP_SOFTWARE_REV}</td></tr>
          <tr><td><b>DCM Serial:</b></td><td>{APP_SERIAL_NUMBER}</td></tr>
          <tr><td><b>Device ID:</b></td><td>{self.device_id or 'None'}</td></tr>
          <tr><td><b>Report Name:</b></td><td>{report_name}</td></tr>
        </table>
        <br>
        """
    #^^ html string

    def _params_table_html(self, p: Dict[str, Any]) -> str:
        rows = []
        def row(k, v): rows.append(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>")

        row("Mode", p["mode"])
        row("LRL", f'{p["LRL_ppm"]} ppm')
        row("URL", f'{p["URL_ppm"]} ppm')
        row("Atrial Amplitude", f'{p["AtrialAmplitude_V"]} V')
        row("Atrial Pulse Width", f'{p["AtrialPulseWidth_ms"]} ms')
        row("Ventricular Amplitude", f'{p["VentricularAmplitude_V"]} V')
        row("Ventricular Pulse Width", f'{p["VentricularPulseWidth_ms"]} ms')
        row("ARP", f'{p["ARP_ms"]} ms')
        row("VRP", f'{p["VRP_ms"]} ms')
        if p["mode"] in ("AAI", "VVI"):
            row("Hysteresis", p["Hysteresis"] + (f' (HRL {p["HRL_ppm"]} ppm)' if p["Hysteresis"]=="On" else ""))
            row("Rate Smoothing Up", f'{p["RateSmoothingUp_percent"]}%')
            row("Rate Smoothing Down", f'{p["RateSmoothingDown_percent"]}%')

        return f"""
        <table border="1" cellspacing="0" cellpadding="4">
            {''.join(rows)}
        </table>
        """

    def _save_pdf(self, html: str, suggested: str) -> None:
        dest, _ = QFileDialog.getSaveFileName(self, "Save PDF", suggested, "PDF Files (*.pdf)")
        if not dest:
            return
        # print HTML to PDF
        doc = QTextDocument()
        doc.setHtml(html)
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(dest)
        doc.print_(printer)
        QMessageBox.information(self, "Saved", f"PDF saved to:\n{dest}")

    def _export_brady_params_report(self) -> None:
        p = self._current_params()
        if not p:
            QMessageBox.warning(self, "No user", "Please log in and open the Mode Editor first.")
            return
        html = self._report_header_html("Bradycardia Parameters Report") + self._params_table_html(p)
        self._save_pdf(html, "Bradycardia Parameters Report.pdf")

    def _export_temp_params_report(self) -> None:
        p = self._current_params()
        if not p:
            QMessageBox.warning(self, "No user", "Please log in and open the Mode Editor first.")
            return
        html = self._report_header_html("Temporary Parameters Report") + self._params_table_html(p)
        self._save_pdf(html, "Temporary Parameters Report.pdf")


    # NAVIGATION CALLED BY LoginPage when login OK
    def _on_login_ok(self, username: str) -> None:
        self.active_user = username
        self.stack.setCurrentWidget(self.page_dash)  # switch to dashboard
        self.status_bar.showMessage(f"Logged in as {username}", 4000)

    # navigation: called by DashboardPage when a mode button clicked 
    def _open_mode_editor(self, mode: str) -> None:
        self.page_edit.set_mode(mode) # tell editor which mode
        self.stack.setCurrentWidget(self.page_edit) # switch to editor page

    # helper passed to ModeEditorPage so it can ask who is logged in
    def _get_active_user(self) -> Optional[str]:
        return self.active_user

    # simulator handlers: flip internal flags and update labels/status 
    def _toggle_comms(self) -> None:
        self.comms_connected = self.action_comms.isChecked()
        self.page_dash.show_comms(self.comms_connected)
        self._refresh_status_bar()

    def _toggle_device_changed(self) -> None:
        self.device_changed = self.action_changed.isChecked()
        self.page_dash.show_changed(self.device_changed)
        self._refresh_status_bar()

    def _set_device_id(self) -> None:
        # reuse a save dialog as a crude "enter a string" prompt.
        path, _ = QFileDialog.getSaveFileName(self, "Enter Device ID then Cancel or Save", "device-1234.txt")
        if path:
            # get just filename without folder or extension
            self.device_id = os.path.splitext(os.path.basename(path))[0]
        self.page_dash.show_device(self.device_id)
        self._refresh_status_bar()

    def _set_telemetry(self, state: str) -> None:
        self.telemetry_state = state
        self.page_dash.show_telemetry(state)
        self._refresh_status_bar()

    # status bar
    def _refresh_status_bar(self) -> None:
        comms = "Connected" if self.comms_connected else "Not Connected"
        changed = "Device Changed" if self.device_changed else "Last Device OK"
        tel = {
            "ok": "Telemetry: OK",
            "out_of_range": "Telemetry: Lost – Out of Range",
            "noise": "Telemetry: Lost – Noise"
        }[self.telemetry_state]
        clock_str = self.device_clock.toString("yyyy-MM-dd HH:mm:ss")
        text = f"{comms} | Device: {self.device_id or 'None'} | {changed} | {tel} | Clock: {clock_str}"

        self.status_bar.showMessage(text)

    def _show_about(self) -> None:
        AboutDialog(self).exec_()

    def _set_clock_dialog(self) -> None:
        dlg = SetClockDialog(self.device_clock, self)
        if dlg.exec_() == QDialog.Accepted:
            self.device_clock = dlg.selected_datetime()
            self._refresh_status_bar()



# =========================
# 10) RUNNING!!!!
# =========================
if __name__ == "__main__":
    app = QApplication([]) # create the app object (one per process)

    win = MainWindow() # create main window
    win.show() # make it visible
    app.exec_() # enter Qt event loop (blocks until window closes)

