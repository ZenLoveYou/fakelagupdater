import os, sys, time, json, ctypes, threading, re
import getpass

# ===== Windows beep =====
try:
    import winsound
    IS_WINDOWS = True
except:
    IS_WINDOWS = False

# ===== PyQt6 =====
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

# ===== Network =====
import pydivert
import keyboard
from pynput.mouse import Listener as MouseListener

# ===== AuthlyX =====
from AuthlyX import AuthlyX

# ===== CONFIG =====
CONFIG_FILE = "config.json"
AUTH_FILE   = "auth.json"

AUTHLYX_OWNER_ID = "4d1b4f07c486"
AUTHLYX_APP_NAME = "Project"
AUTHLYX_VERSION  = "1.0.0"
AUTHLYX_SECRET   = "ZKubX839K3Rgs5f8HHbqr5ZbkNngiOdXJRNQTwBi"

authly_client = None

# ===== APP STATE =====
tele_mode   = False
freeze_mode = False
ghost_mode  = False

running = True
lock = threading.Lock()

hotkeys = {
    "tele":   "V",
    "ghost":  "G",
    "freeze": "B"
}

FILTER_TELE   = "(udp.DstPort>=10011 and udp.DstPort<=10020) and udp.PayloadLength>=45"
FILTER_FREEZE = "(udp.SrcPort >= 10011 and udp.SrcPort <= 10019) and ip and ip.Protocol == 17 and ip.Length >= 52 and ip.Length <= 1491"
FILTER_GHOST  = "(udp.PayloadLength>=50 and udp.PayloadLength<=300) and (udp.DstPort>=10011 and udp.DstPort<=10020)"

# ---------------------------- CONFIG ----------------------------

def load_config():
    global hotkeys
    if os.path.exists(CONFIG_FILE):
        try:
            data = json.load(open(CONFIG_FILE))
            if "hotkeys" in data:
                hotkeys.update({k: v.upper() for k,v in data["hotkeys"].items()})
        except:
            pass

def save_config():
    json.dump({"hotkeys": hotkeys}, open(CONFIG_FILE, "w"), indent=4)

# ---------------------------- AUTH ----------------------------

def load_auth():
    if os.path.exists(AUTH_FILE):
        try:
            return json.load(open(AUTH_FILE))
        except:
            return None

def save_auth(u,p):
    json.dump({"username":u,"password":p}, open(AUTH_FILE,"w"), indent=4)

def play_beep(state=True):
    if not IS_WINDOWS: return
    winsound.Beep(1500 if state else 1000, 80)

def auth_login():
    global authly_client

    print(" Đang kết nối...")

    authly_client = AuthlyX(
        owner_id=AUTHLYX_OWNER_ID,
        app_name=AUTHLYX_APP_NAME,
        version=AUTHLYX_VERSION,
        secret=AUTHLYX_SECRET
    )

    if not authly_client.init():
        print("❌ Init failed:", authly_client.response["message"])
        input(); sys.exit()

    # Try auto login
    saved = load_auth()
    if saved:
        print("🔄 Auto login:", saved["username"])
        if authly_client.login(saved["username"], saved["password"]):
            print("✅ Login OK:", authly_client.user_data["username"])
            return True

    # Manual login
    u = input("Username: ")
    p = getpass.getpass("Password: ")

    if authly_client.login(u,p):
        print("✅ Login OK:", authly_client.user_data["username"])
        save_auth(u,p)
        return True
    else:
        print("❌ Login failed")
        return False

# ---------------------------- SIGNAL ----------------------------

class StatusUpdater(QObject):
    tele_toggled   = pyqtSignal(bool)
    freeze_toggled = pyqtSignal(bool)
    ghost_toggled  = pyqtSignal(bool)
    hotkey_captured = pyqtSignal(str,str)
    log_status = pyqtSignal(str)

up = StatusUpdater()

# ==================================================================
#                         OVERLAY UI
# ==================================================================
class Overlay(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.opacity = 0.69

        self.build_ui()
        self.old_pos = None

        up.tele_toggled.connect(lambda s: self.update_label("Tele", s))
        up.freeze_toggled.connect(lambda s: self.update_label("Freeze", s))
        up.ghost_toggled.connect(lambda s: self.update_label("Ghost", s))

    def build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10,10,10,10)
        layout.setSpacing(10)

        self.labels = {}

        for mode in ["Tele","Freeze","Ghost"]:
            lab = QLabel(f"{mode}: OFF")
            lab.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setMinimumWidth(110)
            lab.setStyleSheet(self.style_off())
            self.labels[mode] = lab
            layout.addWidget(lab)

        self.resize(360, 55)

    def style_on(self):
        return """
            color:#00FF66;
            padding:6px;
            border:2px solid #00FF66;
            border-radius:6px;
            background-color: rgba(20,20,20,220);
        """

    def style_off(self):
        return """
            color:white;
            padding:6px;
            border:2px solid #555;
            border-radius:6px;
            background-color: rgba(20,20,20,220);
        """

    def update_label(self, mode, state):
        lab = self.labels[mode]
        lab.setText(f"{mode}: {'ON' if state else 'OFF'}")
        lab.setStyleSheet(self.style_on() if state else self.style_off())

    # Dragging
    def mousePressEvent(self, e):
        if e.button()==Qt.MouseButton.LeftButton:
            self.old_pos = e.pos()

    def mouseMoveEvent(self, e):
        if self.old_pos:
            self.move(self.pos() + (e.pos()-self.old_pos))

    def mouseReleaseEvent(self, e):
        self.old_pos = None


# ==================================================================
#                          HOTKEY INPUT BOX
# ==================================================================
class HotInput(QLineEdit):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.setReadOnly(True)
        self.setText(hotkeys[mode])
        self.setFixedSize(65,30)
        self.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self.setStyleSheet("""
            QLineEdit {
                background:#2f2f2f;
                color:white;
                border:1px solid #555;
                border-radius:6px;
                text-align:center;
            }
        """)

    def mousePressEvent(self, e):
        MainWindow.is_listening = True
        MainWindow.listen_mode  = self.mode
        self.setText("...")
        self.setStyleSheet("background:#777; color:black; border-radius:6px;")

    def set_new_key(self, k):
        hotkeys[self.mode] = k
        save_config()
        setup_hotkeys()
        self.setText(k)
        self.setStyleSheet("""
            background:#2f2f2f;
            color:white;
            border:1px solid #555;
            border-radius:6px;
        """)

# ==================================================================
#                            MAIN WINDOW
# ==================================================================
class MainWindow(QMainWindow):

    is_listening = False
    listen_mode  = None

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FakeLag")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(370,300)

        self.build_ui()
        self.old_pos = None

        up.hotkey_captured.connect(self.set_hotkey)
        up.log_status.connect(self.set_status)

    def build_ui(self):
        wrap = QWidget()
        self.setCentralWidget(wrap)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(10,10,10,10)
        v.setSpacing(12)

        # Title bar
        top = QHBoxLayout()
        name = QLabel("FakeLag")
        name.setFont(QFont("Consolas",13,QFont.Weight.Bold))
        name.setStyleSheet("color:white;")

        btn_min = QPushButton("-")
        btn_min.setFixedSize(25,25)
        btn_min.clicked.connect(self.showMinimized)

        btn_close = QPushButton("X")
        btn_close.setFixedSize(25,25)
        btn_close.clicked.connect(lambda: os._exit(0))

        for b in (btn_min,btn_close):
            b.setStyleSheet("""
                QPushButton {
                    background:#3a3a3a; color:white;
                    border-radius:4px;
                }
                QPushButton:hover { background:#555; }
            """)

        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(btn_min)
        top.addWidget(btn_close)
        v.addLayout(top)

        # Mode buttons + hotkey row
        modes = [("tele","Telekill"),
                 ("ghost","Ghost"),
                 ("freeze","Freeze")]

        for m, label in modes:
            box = QHBoxLayout()
            btn = QPushButton(label)
            btn.setFixedHeight(35)
            btn.setFont(QFont("Consolas",11,QFont.Weight.Bold))
            btn.setStyleSheet(self.style_button(False))

            if m=="tele":   btn.clicked.connect(toggle_tele)
            if m=="ghost":  btn.clicked.connect(toggle_ghost)
            if m=="freeze": btn.clicked.connect(toggle_freeze)

            inp = HotInput(m)

            setattr(self, f"btn_{m}", btn)
            setattr(self, f"in_{m}", inp)

            box.addWidget(btn,4)
            box.addWidget(inp,1)
            v.addLayout(box)

        self.status = QLabel("Status: Ready")
        self.status.setStyleSheet("color:white; font-size:11px;")
        v.addStretch(1)
        v.addWidget(self.status)

        self.setStyleSheet("background-color:#222; border-radius:10px;")

        up.tele_toggled.connect(lambda s: self.btn_tele.setStyleSheet(self.style_button(s)))
        up.freeze_toggled.connect(lambda s: self.btn_freeze.setStyleSheet(self.style_button(s)))
        up.ghost_toggled.connect(lambda s: self.btn_ghost.setStyleSheet(self.style_button(s)))

    def style_button(self, active):
        if active:
            return """QPushButton{
                background:#00aa55;
                color:white;
                border-radius:8px;
            }"""
        return """QPushButton{
            background:#333;
            color:white;
            border-radius:8px;
        } QPushButton:hover{background:#444;}"""

    def set_hotkey(self, mode, key):
        getattr(self, f"in_{mode}").set_new_key(key)
        self.set_status(f"Hotkey for {mode.upper()} = {key}")

    def set_status(self, msg):
        self.status.setText(msg)

    # Drag window
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            self.old_pos = e.pos()

    def mouseMoveEvent(self,e):
        if self.old_pos:
            self.move(self.pos() + (e.pos()-self.old_pos))

    def mouseReleaseEvent(self,e):
        self.old_pos=None

# ==================================================================
#                     LOGIC: TOGGLE FUNCTIONS
# ==================================================================

def toggle_tele():
    global tele_mode
    with lock:
        tele_mode = not tele_mode
    up.tele_toggled.emit(tele_mode)
    play_beep(tele_mode)
    up.log_status.emit(f"Telekill: {'ON' if tele_mode else 'OFF'}")

def toggle_freeze():
    global freeze_mode
    freeze_mode = not freeze_mode
    up.freeze_toggled.emit(freeze_mode)
    play_beep(freeze_mode)
    up.log_status.emit(f"Freeze: {'ON' if freeze_mode else 'OFF'}")

def toggle_ghost():
    global ghost_mode
    ghost_mode = not ghost_mode
    up.ghost_toggled.emit(ghost_mode)
    play_beep(ghost_mode)
    up.log_status.emit(f"Ghost: {'ON' if ghost_mode else 'OFF'}")

# ==================================================================
#                         KEY LISTENERS
# ==================================================================
mouse_thread = None

def normalize(k):
    k = k.upper()
    if k=="LCONTROL": k="CTRL"
    return re.sub(r'KEY_|BUTTON\.','',k)

def kb_event(e):
    if e.event_type!="down": return
    key = normalize(e.name)

    # Setting mode
    if MainWindow.is_listening:
        MainWindow.is_listening=False
        up.hotkey_captured.emit(MainWindow.listen_mode, key)
        return

    # Toggle mode
    if key == hotkeys["tele"]:   toggle_tele()
    if key == hotkeys["ghost"]:  toggle_ghost()
    if key == hotkeys["freeze"]: toggle_freeze()

def mouse_event(x,y,btn,pressed):
    if not pressed: return
    name=str(btn).upper()

    if MainWindow.is_listening:
        MainWindow.is_listening=False
        up.hotkey_captured.emit(MainWindow.listen_mode, normalize(name))
        return

    key = normalize(name)
    if key == hotkeys["tele"]:   toggle_tele()
    if key == hotkeys["ghost"]:  toggle_ghost()
    if key == hotkeys["freeze"]: toggle_freeze()

def setup_hotkeys():
    keyboard.unhook_all()
    keyboard.hook(kb_event)

    global mouse_thread
    if mouse_thread:
        mouse_thread.stop()
    mouse_thread = MouseListener(on_click=mouse_event)
    mouse_thread.start()


# ==================================================================
#                         WIN Divert Worker
# ==================================================================
class DivertThread(QThread):
    def __init__(self, filt, mode):
        super().__init__()
        self.f = filt
        self.mode = mode

    def run(self):
        global tele_mode, freeze_mode, ghost_mode
        try:
            with pydivert.WinDivert(self.f) as w:
                for pkt in w:
                    if not running: break

                    state = (tele_mode if self.mode=="tele" else
                             freeze_mode if self.mode=="freeze" else
                             ghost_mode)

                    if state:
                        continue
                    w.send(pkt)
        except Exception as e:
            print("WinDivert error:", e)
            os._exit(0)

# ==================================================================
#                               MAIN
# ==================================================================

def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(None,"runas",sys.executable,__file__,None,1)
        return

    load_config()

    if not auth_login():
        return

    app = QApplication(sys.argv)

    setup_hotkeys()

    win = MainWindow()
    overlay = Overlay(win)

    # Start WinDivert
    threads = [
        DivertThread(FILTER_TELE,"tele"),
        DivertThread(FILTER_FREEZE,"freeze"),
        DivertThread(FILTER_GHOST,"ghost")
    ]
    for t in threads: t.start()

    win.show()
    overlay.show()

    sys.exit(app.exec())


if __name__=="__main__":
    main()
