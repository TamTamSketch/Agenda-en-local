#!/usr/bin/env python3
# Agenda local — aucun réseau, aucun cloud, aucune adresse e-mail.
# Python 3 + Tkinter (généralement inclus avec Python).
# Les données sont stockées dans agenda_local.json à côté du programme.
# Optionnel : définir AGENDA_PASSWORD pour chiffrer le fichier avec cryptography.
import json
import math
import os
import sys
import calendar
import atexit
import ctypes
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime, timedelta
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DATA_FILE = APP_DIR / "agenda_local.json"
WIDGET_PREFS = APP_DIR / "agenda_widget.json"
WIDGET_LOCK = APP_DIR / "agenda_widget.lock"
DATE_FMT = "%Y-%m-%d"

MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]
WEEKDAYS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
WEEKDAYS_LONG = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# Palette chaleureuse, sans dépendance externe.
C = {
    "bg": "#FFF4EB",
    "surface": "#FFFBF7",
    "ink": "#3B2A24",
    "muted": "#8A6E64",
    "line": "#F0D9C8",
    "accent": "#E07A5F",
    "accent_dark": "#C45C3E",
    "accent_soft": "#F8D4C4",
    "sage": "#6EA58A",
    "today": "#F6E0B8",
    "header1": "#E07A5F",
    "header2": "#F2A07A",
    "white": "#FFFFFF",
}


def format_date_fr(d):
    return f"{WEEKDAYS_LONG[d.weekday()]} {d.day} {MONTHS_FR[d.month - 1]} {d.year}"


def get_cipher():
    password = os.environ.get("AGENDA_PASSWORD")
    if not password:
        return None
    try:
        from cryptography.fernet import Fernet
        import base64, hashlib
        key = base64.urlsafe_b64encode(hashlib.sha256(password.encode("utf-8")).digest())
        return Fernet(key)
    except ImportError:
        messagebox.showerror(
            "Chiffrement indisponible",
            "AGENDA_PASSWORD est défini, mais le module 'cryptography' n'est pas installé.\n"
            "Installez-le hors ligne si possible, ou retirez AGENDA_PASSWORD."
        )
        return None


def load_events():
    if not DATA_FILE.exists():
        return []
    raw = DATA_FILE.read_bytes()
    cipher = get_cipher()
    try:
        if raw.startswith(b"ENC1:"):
            if cipher is None:
                raise ValueError("Le fichier est chiffré. Définissez AGENDA_PASSWORD avec le même mot de passe.")
            raw = cipher.decrypt(raw[5:])
        elif cipher is not None:
            pass
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        messagebox.showerror("Lecture impossible", f"Impossible de lire les données.\n{exc}")
        return []


def save_events(events):
    payload = json.dumps(events, ensure_ascii=False, indent=2).encode("utf-8")
    cipher = get_cipher()
    if cipher:
        payload = b"ENC1:" + cipher.encrypt(payload)
    temp = DATA_FILE.with_suffix(".tmp")
    temp.write_bytes(payload)
    os.replace(temp, DATA_FILE)


def ui_font(size=11, weight="normal"):
    family = "Segoe UI" if sys.platform.startswith("win") else "TkDefaultFont"
    return (family, size, weight)


class ClockPicker(tk.Frame):
    """Horloge analogique : on clique (ou on glisse) pour poser les aiguilles."""

    def __init__(self, parent, hour=9, minute=0, on_change=None):
        super().__init__(parent, bg=C["surface"])
        self.hour = hour % 24
        self.minute = minute % 60
        self.mode = "hour"
        self.on_change = on_change
        self.size = 268
        self.cx = self.cy = self.size // 2
        self.radius = 108

        top = tk.Frame(self, bg=C["surface"])
        top.pack(pady=(0, 8))
        self.hour_chip = tk.Label(
            top, text="09", font=ui_font(28, "bold"),
            bg=C["accent"], fg=C["white"], padx=14, pady=4, cursor="hand2"
        )
        self.colon = tk.Label(top, text=":", font=ui_font(28, "bold"), bg=C["surface"], fg=C["accent"])
        self.min_chip = tk.Label(
            top, text="00", font=ui_font(28, "bold"),
            bg=C["accent_soft"], fg=C["ink"], padx=14, pady=4, cursor="hand2"
        )
        self.hour_chip.pack(side="left")
        self.colon.pack(side="left", padx=4)
        self.min_chip.pack(side="left")
        self.hour_chip.bind("<Button-1>", lambda _e: self.set_mode("hour"))
        self.min_chip.bind("<Button-1>", lambda _e: self.set_mode("minute"))

        hint = tk.Label(
            self, text="Cliquez sur le cadran ou faites glisser les aiguilles",
            bg=C["surface"], fg=C["muted"], font=ui_font(8)
        )
        hint.pack()

        self.canvas = tk.Canvas(
            self, width=self.size, height=self.size,
            bg=C["surface"], highlightthickness=0, cursor="hand2"
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)

        modes = tk.Frame(self, bg=C["surface"])
        modes.pack(pady=(6, 0))
        self.btn_hour = tk.Button(
            modes, text="Heures", command=lambda: self.set_mode("hour"),
            font=ui_font(9, "bold"), relief="flat", padx=12, pady=4, cursor="hand2"
        )
        self.btn_min = tk.Button(
            modes, text="Minutes", command=lambda: self.set_mode("minute"),
            font=ui_font(9, "bold"), relief="flat", padx=12, pady=4, cursor="hand2"
        )
        self.btn_hour.pack(side="left", padx=4)
        self.btn_min.pack(side="left", padx=4)

        self._redraw()

    def time_str(self):
        return f"{self.hour:02d}:{self.minute:02d}"

    def set_mode(self, mode):
        self.mode = mode
        self._redraw()

    def _notify(self):
        if self.on_change:
            self.on_change(self.hour, self.minute)

    def _angle_from_event(self, event):
        dx = event.x - self.cx
        dy = event.y - self.cy
        dist = math.hypot(dx, dy)
        angle = math.atan2(dx, -dy)
        if angle < 0:
            angle += 2 * math.pi
        return dist, angle

    def _apply_from_event(self, event, switch_after_hour=False):
        dist, angle = self._angle_from_event(event)
        if dist < 18:
            return
        if self.mode == "hour":
            index = int(round(angle / (2 * math.pi) * 12)) % 12
            inner = dist < (self.radius * 0.72)
            self.hour = index if inner else index + 12
            if switch_after_hour:
                self.mode = "minute"
        else:
            self.minute = int(round(angle / (2 * math.pi) * 60)) % 60
        self._redraw()
        self._notify()

    def _on_press(self, event):
        was_hour = self.mode == "hour"
        self._apply_from_event(event, switch_after_hour=was_hour)

    def _on_drag(self, event):
        self._apply_from_event(event, switch_after_hour=False)

    def _point(self, angle, radius):
        x = self.cx + radius * math.sin(angle)
        y = self.cy - radius * math.cos(angle)
        return x, y

    def _redraw(self):
        cv = self.canvas
        cv.delete("all")
        cx, cy, r = self.cx, self.cy, self.radius

        cv.create_oval(cx - r - 14, cy - r - 14, cx + r + 14, cy + r + 14, fill="#F8E6DA", outline="")
        cv.create_oval(cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4, fill=C["white"], outline=C["line"], width=2)

        hour_angle = ((self.hour % 12) + self.minute / 60) / 12 * 2 * math.pi
        min_angle = self.minute / 60 * 2 * math.pi
        hx, hy = self._point(hour_angle, r * 0.52)
        mx, my = self._point(min_angle, r * 0.78)
        cv.create_line(cx, cy, hx, hy, fill="#C9A090", width=7, capstyle="round")
        cv.create_line(cx, cy, mx, my, fill=C["accent"], width=4, capstyle="round")

        if self.mode == "hour":
            for h in range(24):
                inner = h < 12
                ring = r * (0.52 if inner else 0.88)
                ang = (h % 12) / 12 * 2 * math.pi
                x, y = self._point(ang, ring)
                selected = h == self.hour
                fill = C["accent"] if selected else (C["accent_soft"] if inner else "#F4E0D4")
                fg = C["white"] if selected else C["ink"]
                rad = 16 if selected else 14
                cv.create_oval(x - rad, y - rad, x + rad, y + rad, fill=fill, outline="")
                cv.create_text(x, y, text=f"{h:02d}", fill=fg, font=ui_font(9, "bold"))
            sx, sy = self._point((self.hour % 12) / 12 * 2 * math.pi, r * (0.52 if self.hour < 12 else 0.88))
            cv.create_line(cx, cy, sx, sy, fill=C["accent"], width=3, capstyle="round")
        else:
            for m in range(0, 60, 5):
                ang = m / 60 * 2 * math.pi
                x, y = self._point(ang, r * 0.82)
                selected = self.minute == m
                fill = C["accent"] if selected else C["accent_soft"]
                fg = C["white"] if selected else C["ink"]
                cv.create_oval(x - 15, y - 15, x + 15, y + 15, fill=fill, outline="")
                cv.create_text(x, y, text=f"{m:02d}", fill=fg, font=ui_font(9, "bold"))
            if self.minute % 5 != 0:
                ang = self.minute / 60 * 2 * math.pi
                x, y = self._point(ang, r * 0.82)
                cv.create_oval(x - 10, y - 10, x + 10, y + 10, fill=C["accent_dark"], outline="")
                cv.create_text(x, y, text=f"{self.minute:02d}", fill=C["white"], font=ui_font(8, "bold"))
            sx, sy = self._point(self.minute / 60 * 2 * math.pi, r * 0.82)
            cv.create_line(cx, cy, sx, sy, fill=C["accent"], width=3, capstyle="round")

        cv.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill=C["accent_dark"], outline="")

        self.hour_chip.config(
            text=f"{self.hour:02d}",
            bg=C["accent"] if self.mode == "hour" else C["accent_soft"],
            fg=C["white"] if self.mode == "hour" else C["ink"],
        )
        self.min_chip.config(
            text=f"{self.minute:02d}",
            bg=C["accent"] if self.mode == "minute" else C["accent_soft"],
            fg=C["white"] if self.mode == "minute" else C["ink"],
        )
        self.btn_hour.config(
            bg=C["accent"] if self.mode == "hour" else C["accent_soft"],
            fg=C["white"] if self.mode == "hour" else C["ink"],
            activebackground=C["accent_dark"],
        )
        self.btn_min.config(
            bg=C["accent"] if self.mode == "minute" else C["accent_soft"],
            fg=C["white"] if self.mode == "minute" else C["ink"],
            activebackground=C["accent_dark"],
        )


class MiniCalendar(tk.Frame):
    def __init__(self, parent, selected, on_pick):
        super().__init__(parent, bg=C["surface"])
        self.view = selected.replace(day=1)
        self.selected = selected
        self.on_pick = on_pick
        nav = tk.Frame(self, bg=C["surface"])
        nav.pack(fill="x", pady=(0, 6))
        tk.Button(
            nav, text="‹", command=self._prev, relief="flat", bg=C["accent_soft"],
            fg=C["ink"], font=ui_font(12, "bold"), width=3, cursor="hand2"
        ).pack(side="left")
        self.title = tk.Label(nav, text="", bg=C["surface"], fg=C["ink"], font=ui_font(11, "bold"))
        self.title.pack(side="left", expand=True)
        tk.Button(
            nav, text="›", command=self._next, relief="flat", bg=C["accent_soft"],
            fg=C["ink"], font=ui_font(12, "bold"), width=3, cursor="hand2"
        ).pack(side="right")
        self.grid_frame = tk.Frame(self, bg=C["surface"])
        self.grid_frame.pack()
        self._redraw()

    def _prev(self):
        y, m = self.view.year, self.view.month
        self.view = date(y - (m == 1), 12 if m == 1 else m - 1, 1)
        self._redraw()

    def _next(self):
        y, m = self.view.year, self.view.month
        self.view = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
        self._redraw()

    def _pick(self, d):
        self.selected = d
        self.view = d.replace(day=1)
        self._redraw()
        self.on_pick(d)

    def _redraw(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.title.config(text=f"{MONTHS_FR[self.view.month - 1].capitalize()} {self.view.year}")
        for c, name in enumerate(WEEKDAYS_FR):
            tk.Label(
                self.grid_frame, text=name, bg=C["surface"], fg=C["muted"],
                font=ui_font(8, "bold"), width=4
            ).grid(row=0, column=c, pady=(0, 4))
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self.view.year, self.view.month)
        today = date.today()
        for r, week in enumerate(weeks, start=1):
            for c, day in enumerate(week):
                if day == 0:
                    tk.Label(self.grid_frame, text="", bg=C["surface"], width=4).grid(row=r, column=c, padx=2, pady=2)
                    continue
                d = date(self.view.year, self.view.month, day)
                selected = d == self.selected
                bg = C["accent"] if selected else (C["today"] if d == today else C["white"])
                fg = C["white"] if selected else C["ink"]
                btn = tk.Button(
                    self.grid_frame, text=str(day), width=4, relief="flat",
                    bg=bg, fg=fg, font=ui_font(9, "bold"),
                    activebackground=C["accent_dark"], activeforeground=C["white"],
                    cursor="hand2", command=lambda chosen=d: self._pick(chosen)
                )
                btn.grid(row=r, column=c, padx=2, pady=2)


def week_days(around=None):
    around = around or date.today()
    monday = around - timedelta(days=around.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def load_widget_prefs():
    defaults = {
        "x": 36,
        "y": 90,
        "collapsed": True,
        "always_on_top": True,
        "start_with_windows": False,
    }
    if not WIDGET_PREFS.exists():
        return defaults
    try:
        data = json.loads(WIDGET_PREFS.read_text(encoding="utf-8"))
        defaults.update(data)
        return defaults
    except Exception:
        return defaults


def save_widget_prefs(prefs):
    try:
        WIDGET_PREFS.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except OSError:
        pass


def pythonw_executable():
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def windows_folder(csidl):
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return Path(buf.value)


def create_windows_shortcut(lnk_path, extra_args="--widget"):
    target = pythonw_executable().replace("'", "''")
    script = str(APP_DIR / "agenda_local.py").replace("'", "''")
    work = str(APP_DIR).replace("'", "''")
    lnk = str(lnk_path).replace("'", "''")
    ps = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.Arguments = '\"{script}\" {extra_args}'; "
        f"$s.WorkingDirectory = '{work}'; "
        f"$s.Description = 'Agenda de la semaine'; "
        f"$s.WindowStyle = 7; "
        f"$s.Save()"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
        check=False,
        creationflags=flags,
    )


def desktop_shortcut_path():
    return windows_folder(0) / "Agenda semaine.lnk"


def startup_shortcut_path():
    return windows_folder(7) / "Agenda semaine.lnk"


def install_desktop_button():
    if not sys.platform.startswith("win"):
        return False
    try:
        create_windows_shortcut(desktop_shortcut_path())
        return True
    except Exception:
        return False


def set_windows_startup(enabled):
    if not sys.platform.startswith("win"):
        return
    path = startup_shortcut_path()
    if enabled:
        create_windows_shortcut(path)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def pid_is_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_widget_lock():
    if WIDGET_LOCK.exists():
        try:
            pid = int(WIDGET_LOCK.read_text(encoding="utf-8").strip())
            if pid != os.getpid() and pid_is_alive(pid):
                return False
        except ValueError:
            pass
    try:
        WIDGET_LOCK.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        return True
    return True


def release_widget_lock():
    try:
        if WIDGET_LOCK.exists() and WIDGET_LOCK.read_text(encoding="utf-8").strip() == str(os.getpid()):
            WIDGET_LOCK.unlink()
    except OSError:
        pass


class WeekWidget(tk.Toplevel):
    """Bouton de bureau : un clic affiche la semaine lue dans agenda_local.json."""

    def __init__(self, master):
        super().__init__(master)
        self.prefs = load_widget_prefs()
        self.week_anchor = date.today()
        self._today = date.today()
        self._mtime = None
        self._drag = None
        self._moved = False
        self._full_agenda = None
        atexit.register(release_widget_lock)

        self.overrideredirect(True)
        self.configure(bg=C["accent"])
        self.attributes("-topmost", bool(self.prefs.get("always_on_top", True)))
        try:
            self.attributes("-alpha", 0.98)
        except tk.TclError:
            pass

        self.shell = tk.Frame(self, bg=C["surface"], highlightbackground=C["accent"], highlightthickness=2)
        self.shell.pack(fill="both", expand=True)
        self.body = tk.Frame(self.shell, bg=C["surface"])
        self.body.pack(fill="both", expand=True)

        x, y = int(self.prefs.get("x", 36)), int(self.prefs.get("y", 90))
        self.geometry(f"+{x}+{y}")
        self._render()
        self._tick()
        self.protocol("WM_DELETE_WINDOW", self._collapse)

    def _save_pos(self):
        self.prefs["x"] = self.winfo_x()
        self.prefs["y"] = self.winfo_y()
        save_widget_prefs(self.prefs)

    def _press(self, event):
        self._moved = False
        self._drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _motion(self, event):
        if not self._drag:
            return
        dx, dy = event.x_root - self.winfo_x() - self._drag[0], event.y_root - self.winfo_y() - self._drag[1]
        if abs(dx) > 4 or abs(dy) > 4:
            self._moved = True
        self.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    def _release(self, event):
        self._drag = None
        self._save_pos()
        if not self._moved and self.prefs.get("collapsed"):
            self._expand()

    def _bind_drag(self, widget, also_click_expand=False):
        widget.bind("<ButtonPress-1>", self._press)
        widget.bind("<B1-Motion>", self._motion)
        widget.bind("<ButtonRelease-1>", self._release if also_click_expand else lambda _e: self._save_pos())

    def _collapse(self):
        self.prefs["collapsed"] = True
        self._save_pos()
        self._render()

    def _expand(self):
        self.prefs["collapsed"] = False
        self._save_pos()
        self._render()

    def _toggle_topmost(self):
        self.prefs["always_on_top"] = not self.prefs.get("always_on_top", True)
        self.attributes("-topmost", bool(self.prefs["always_on_top"]))
        save_widget_prefs(self.prefs)
        self._render()

    def _toggle_startup(self):
        self.prefs["start_with_windows"] = not self.prefs.get("start_with_windows", False)
        set_windows_startup(self.prefs["start_with_windows"])
        save_widget_prefs(self.prefs)
        self._render()

    def _close(self):
        self._save_pos()
        release_widget_lock()
        self.destroy()
        master = self.master
        if isinstance(master, tk.Tk) and not any(
            isinstance(w, tk.Toplevel) and w.winfo_exists() and w is not self
            for w in master.winfo_children()
        ) and not master.winfo_viewable():
            master.destroy()

    def _open_full(self):
        if self._full_agenda is not None and self._full_agenda.winfo_exists():
            self._full_agenda.deiconify()
            self._full_agenda.lift()
            return
        if isinstance(self.master, tk.Tk) and self.master.winfo_viewable():
            self.master.deiconify()
            self.master.lift()
            return
        win = tk.Toplevel(self.master)
        AgendaApp(win)
        self._full_agenda = win

    def _shift_week(self, delta):
        self.week_anchor = week_days(self.week_anchor)[0] + timedelta(days=7 * delta)
        self._render()

    def _this_week(self):
        self.week_anchor = date.today()
        self._render()

    def _events(self):
        return load_events()

    def _tick(self):
        if not self.winfo_exists():
            return
        try:
            mtime = DATA_FILE.stat().st_mtime if DATA_FILE.exists() else 0
        except OSError:
            mtime = 0
        today = date.today()
        if mtime != self._mtime:
            self._mtime = mtime
            self._render()
        elif self._today != today:
            self.week_anchor = today
            self._render()
        self._today = today
        self.after(1500, self._tick)

    def reload(self):
        self._render()

    def _render(self):
        self._today = date.today()
        for child in self.body.winfo_children():
            child.destroy()
        if self.prefs.get("collapsed"):
            self._render_button()
        else:
            self._render_week()

    def _render_button(self):
        events = self._events()
        today = date.today()
        todays = sorted(
            [e for e in events if e.get("date") == today.isoformat()],
            key=lambda e: e.get("time") or "",
        )
        now = datetime.now().strftime("%H:%M")
        nxt = next((e for e in todays if (e.get("time") or "") >= now), todays[0] if todays else None)
        preview = "Rien de prévu aujourd'hui"
        if nxt:
            preview = f"{nxt.get('time', '')}  {nxt.get('title', '(sans titre)')}".strip()
            if len(preview) > 28:
                preview = preview[:27] + "…"

        card = tk.Frame(self.body, bg=C["accent"], cursor="hand2")
        card.pack(fill="both", expand=True)
        title = tk.Label(card, text="Agenda  ·  semaine", bg=C["accent"], fg=C["white"], font=ui_font(11, "bold"), cursor="hand2")
        title.pack(anchor="w", padx=14, pady=(10, 0))
        sub = tk.Label(card, text=preview, bg=C["accent"], fg="#FFE8DC", font=ui_font(9), cursor="hand2")
        sub.pack(anchor="w", padx=14, pady=(2, 12))
        hint = tk.Label(card, text="Cliquez  ·  glissez pour déplacer", bg=C["accent"], fg="#F8D4C4", font=ui_font(7), cursor="hand2")
        hint.pack(anchor="w", padx=14, pady=(0, 8))
        for w in (card, title, sub, hint):
            self._bind_drag(w, also_click_expand=True)

    def _render_week(self):
        days = week_days(self.week_anchor)
        events = self._events()
        by_day = {}
        for event in events:
            by_day.setdefault(event.get("date"), []).append(event)

        header = tk.Frame(self.body, bg=C["accent"])
        header.pack(fill="x")
        grab = tk.Label(header, text="  ⋮⋮  Semaine", bg=C["accent"], fg=C["white"], font=ui_font(11, "bold"), cursor="fleur")
        grab.pack(side="left", pady=8)
        tk.Button(
            header, text="×", command=self._close, bg=C["accent"], fg=C["white"],
            relief="flat", font=ui_font(12, "bold"), cursor="hand2", bd=0, padx=8
        ).pack(side="right")
        tk.Button(
            header, text="−", command=self._collapse, bg=C["accent"], fg=C["white"],
            relief="flat", font=ui_font(12, "bold"), cursor="hand2", bd=0, padx=8
        ).pack(side="right")
        self._bind_drag(header)
        self._bind_drag(grab)

        nav = tk.Frame(self.body, bg=C["surface"])
        nav.pack(fill="x", padx=10, pady=(8, 4))
        tk.Button(
            nav, text="‹", command=lambda: self._shift_week(-1), relief="flat",
            bg=C["accent_soft"], fg=C["ink"], font=ui_font(10, "bold"), width=3, cursor="hand2"
        ).pack(side="left")
        label = f"{days[0].day} {MONTHS_FR[days[0].month - 1][:3]}.  →  {days[6].day} {MONTHS_FR[days[6].month - 1][:3]}. {days[6].year}"
        tk.Label(nav, text=label, bg=C["surface"], fg=C["ink"], font=ui_font(9, "bold")).pack(side="left", expand=True)
        tk.Button(
            nav, text="›", command=lambda: self._shift_week(1), relief="flat",
            bg=C["accent_soft"], fg=C["ink"], font=ui_font(10, "bold"), width=3, cursor="hand2"
        ).pack(side="right")

        today = date.today()
        for d in days:
            is_today = d == today
            bg = C["today"] if is_today else C["white"]
            row = tk.Frame(self.body, bg=bg, highlightbackground=C["line"], highlightthickness=1)
            row.pack(fill="x", padx=10, pady=3)
            head = f"{WEEKDAYS_FR[d.weekday()]}  {d.day}"
            if is_today:
                head += "  ·  aujourd'hui"
            tk.Label(row, text=head, bg=bg, fg=C["accent_dark"] if is_today else C["muted"], font=ui_font(8, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
            day_events = sorted(by_day.get(d.isoformat(), []), key=lambda e: e.get("time") or "")
            if not day_events:
                tk.Label(row, text="Libre", bg=bg, fg="#C4A99A", font=ui_font(8)).pack(anchor="w", padx=8, pady=(0, 6))
            else:
                for event in day_events:
                    text = f"{event.get('time', '')}   {event.get('title', '(sans titre)')}".strip()
                    tk.Label(row, text=text, bg=bg, fg=C["ink"], font=ui_font(9), anchor="w").pack(fill="x", padx=8, pady=1)
                tk.Frame(row, bg=bg, height=6).pack()

        actions = tk.Frame(self.body, bg=C["surface"])
        actions.pack(fill="x", padx=10, pady=8)
        tk.Button(
            actions, text="Ouvrir l'agenda", command=self._open_full,
            bg=C["accent"], fg=C["white"], relief="flat", font=ui_font(9, "bold"),
            padx=10, pady=6, cursor="hand2"
        ).pack(side="left")
        tk.Button(
            actions, text="Cette semaine", command=self._this_week,
            bg=C["white"], fg=C["ink"], relief="flat", font=ui_font(9, "bold"),
            padx=8, pady=6, cursor="hand2"
        ).pack(side="left", padx=6)

        extras = tk.Frame(self.body, bg=C["surface"])
        extras.pack(fill="x", padx=10, pady=(0, 10))
        pin = "Épinglé au-dessus" if self.prefs.get("always_on_top") else "Derrière les fenêtres"
        tk.Button(
            extras, text=pin, command=self._toggle_topmost,
            bg=C["accent_soft"], fg=C["ink"], relief="flat", font=ui_font(8),
            padx=8, pady=4, cursor="hand2"
        ).pack(side="left")
        if sys.platform.startswith("win"):
            boot = "Au démarrage : oui" if self.prefs.get("start_with_windows") else "Au démarrage : non"
            tk.Button(
                extras, text=boot, command=self._toggle_startup,
                bg=C["accent_soft"], fg=C["ink"], relief="flat", font=ui_font(8),
                padx=8, pady=4, cursor="hand2"
            ).pack(side="left", padx=6)
        tk.Label(
            self.body, text="Lit agenda_local.json  ·  même fichier que l'agenda",
            bg=C["surface"], fg=C["muted"], font=ui_font(7)
        ).pack(anchor="w", padx=12, pady=(0, 8))


def start_week_widget(master):
    if not acquire_widget_lock():
        return None
    widget = WeekWidget(master)
    master.week_widget = widget
    return widget


class AgendaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Agenda local")
        self.root.geometry("1120x740")
        self.root.minsize(900, 620)
        self.root.configure(bg=C["bg"])
        self.events = load_events()
        self.selected_date = date.today()
        self._style()
        self.build_ui()
        self.refresh()

    def _style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=C["bg"], foreground=C["ink"], font=ui_font(10))
        style.configure("TFrame", background=C["bg"])
        style.configure("Card.TFrame", background=C["surface"])
        style.configure("Treeview", background=C["white"], fieldbackground=C["white"],
                        foreground=C["ink"], rowheight=34, font=ui_font(10), borderwidth=0)
        style.configure("Treeview.Heading", background=C["accent"], foreground=C["white"],
                        font=ui_font(10, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", C["accent"])], foreground=[("selected", C["white"])])
        style.map("Treeview.Heading", background=[("active", C["accent_dark"])])
        style.configure("TPanedwindow", background=C["bg"])

    def _pill(self, parent, text, command, filled=False):
        bg = C["accent"] if filled else C["white"]
        fg = C["white"] if filled else C["ink"]
        btn = tk.Button(
            parent, text=text, command=command, font=ui_font(10, "bold"),
            bg=bg, fg=fg, relief="flat", padx=14, pady=8, cursor="hand2",
            activebackground=C["accent_dark"], activeforeground=C["white"],
            highlightthickness=0, bd=0
        )
        return btn

    def build_ui(self):
        header = tk.Canvas(self.root, height=86, bg=C["header1"], highlightthickness=0)
        header.pack(fill="x")
        header.bind("<Configure>", lambda e: self._paint_header(header, e.width))
        self._paint_header(header, 1120)

        nav = tk.Frame(self.root, bg=C["bg"])
        nav.pack(fill="x", padx=18, pady=(14, 8))
        self._pill(nav, "◀  Mois précédent", self.prev_month).pack(side="left")
        self.month_label = tk.Label(
            nav, text="", font=ui_font(16, "bold"), bg=C["bg"], fg=C["ink"], width=22
        )
        self.month_label.pack(side="left", padx=12)
        self._pill(nav, "Mois suivant  ▶", self.next_month).pack(side="left")
        self._pill(nav, "Aujourd'hui", self.go_today).pack(side="left", padx=10)
        self._pill(nav, "Semaine sur le bureau", self.pin_week_to_desktop).pack(side="right", padx=(0, 8))
        self._pill(nav, "+  Nouveau rendez-vous", self.add_event, filled=True).pack(side="right")

        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        body.columnconfigure(0, weight=5)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        left_card = tk.Frame(body, bg=C["surface"], highlightbackground=C["line"], highlightthickness=1)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.calendar_frame = tk.Frame(left_card, bg=C["surface"])
        self.calendar_frame.pack(fill="both", expand=True, padx=10, pady=10)

        right_card = tk.Frame(body, bg=C["surface"], highlightbackground=C["line"], highlightthickness=1)
        right_card.grid(row=0, column=1, sticky="nsew")
        tk.Label(
            right_card, text="Rendez-vous du jour", font=ui_font(14, "bold"),
            bg=C["surface"], fg=C["ink"]
        ).pack(anchor="w", padx=14, pady=(14, 0))
        self.day_label = tk.Label(
            right_card, text="", font=ui_font(10), bg=C["surface"], fg=C["muted"]
        )
        self.day_label.pack(anchor="w", padx=14, pady=(2, 8))
        cols = ("time", "title")
        self.tree = ttk.Treeview(right_card, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("time", text="Heure")
        self.tree.heading("title", text="Rendez-vous")
        self.tree.column("time", width=78, stretch=False)
        self.tree.column("title", width=250)
        self.tree.pack(fill="both", expand=True, padx=12)
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        actions = tk.Frame(right_card, bg=C["surface"])
        actions.pack(fill="x", padx=12, pady=12)
        self._pill(actions, "Ajouter", self.add_event, filled=True).pack(side="left")
        self._pill(actions, "Modifier", self.edit_selected).pack(side="left", padx=6)
        self._pill(actions, "Supprimer", self.delete_selected).pack(side="left")
        self._pill(actions, "Exporter JSON", self.export_json).pack(side="right")

        footer = tk.Label(
            self.root, text=f"Privé · stocké uniquement ici  ·  {DATA_FILE}",
            bg=C["bg"], fg=C["muted"], font=ui_font(8), anchor="w"
        )
        footer.pack(fill="x", padx=18, pady=(0, 10))

    def _paint_header(self, canvas, width):
        canvas.delete("all")
        width = max(width, 1)
        steps = 24
        for i in range(steps):
            t = i / steps
            r = int(224 + (242 - 224) * t)
            g = int(122 + (160 - 122) * t)
            b = int(95 + (122 - 95) * t)
            color = f"#{r:02x}{g:02x}{b:02x}"
            canvas.create_rectangle(int(width * i / steps), 0, int(width * (i + 1) / steps) + 1, 86, outline="", fill=color)
        canvas.create_text(28, 32, anchor="w", text="Agenda local", fill=C["white"], font=ui_font(22, "bold"))
        canvas.create_text(
            28, 58, anchor="w",
            text="Vos rendez-vous restent sur cet appareil  ·  aucun cloud",
            fill="#FFE8DC", font=ui_font(10)
        )

    def month_start(self):
        return self.selected_date.replace(day=1)

    def prev_month(self):
        y, m = self.selected_date.year, self.selected_date.month
        self.selected_date = date(y - (m == 1), 12 if m == 1 else m - 1, 1)
        self.refresh()

    def next_month(self):
        y, m = self.selected_date.year, self.selected_date.month
        self.selected_date = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
        self.refresh()

    def go_today(self):
        self.selected_date = date.today()
        self.refresh()

    def choose_day(self, d):
        self.selected_date = d
        self.refresh()

    def refresh(self):
        self.month_label.config(text=f"{MONTHS_FR[self.selected_date.month - 1].capitalize()} {self.selected_date.year}")
        for child in self.calendar_frame.winfo_children():
            child.destroy()

        for c, name in enumerate(WEEKDAYS_FR):
            tk.Label(
                self.calendar_frame, text=name, anchor="center",
                bg=C["surface"], fg=C["muted"], font=ui_font(9, "bold")
            ).grid(row=0, column=c, sticky="nsew", padx=2, pady=4)
            self.calendar_frame.columnconfigure(c, weight=1, uniform="daycol")

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdayscalendar(self.selected_date.year, self.selected_date.month)
        colors = ["#E07A5F", "#6EA58A", "#D4A373", "#C44569", "#7B8CDE", "#C08497"]
        month_events = {}
        for event in self.events:
            month_events.setdefault(event.get("date"), []).append(event)

        for r, week in enumerate(weeks, start=1):
            self.calendar_frame.rowconfigure(r, weight=1, minsize=86)
            for c, day in enumerate(week):
                if day == 0:
                    blank = tk.Frame(self.calendar_frame, bg="#F6EBE3")
                    blank.grid(row=r, column=c, sticky="nsew", padx=3, pady=3)
                    continue

                d = date(self.selected_date.year, self.selected_date.month, day)
                ds = d.isoformat()
                is_selected = d == self.selected_date
                is_today = d == date.today()
                bg = C["accent_soft"] if is_selected else (C["today"] if is_today else C["white"])
                border = C["accent"] if is_selected else C["line"]

                cell = tk.Frame(self.calendar_frame, bg=bg, highlightbackground=border, highlightthickness=2 if is_selected else 1)
                cell.grid(row=r, column=c, sticky="nsew", padx=3, pady=3)

                day_button = tk.Button(
                    cell, text=str(day), anchor="w", padx=6, pady=2,
                    font=ui_font(11, "bold"), bg=bg, fg=C["ink"],
                    activebackground=C["accent"], activeforeground=C["white"],
                    relief="flat", bd=0, cursor="hand2",
                    command=lambda chosen=d: self.choose_day(chosen)
                )
                day_button.pack(fill="x")

                events_for_day = sorted(month_events.get(ds, []), key=lambda e: e.get("time", ""))
                for idx, event in enumerate(events_for_day[:3]):
                    color = colors[idx % len(colors)]
                    title = event.get("title", "(sans titre)")
                    time_text = event.get("time", "")
                    bar_text = f"{time_text}  {title}".strip()
                    if len(bar_text) > 20:
                        bar_text = bar_text[:19] + "…"
                    bar = tk.Label(
                        cell, text=bar_text, bg=color, fg="white",
                        anchor="w", padx=5, pady=2, font=ui_font(8), cursor="hand2"
                    )
                    bar.pack(fill="x", padx=4, pady=1)
                    bar.bind("<Button-1>", lambda _e, chosen=d: self.choose_day(chosen))

                if len(events_for_day) > 3:
                    tk.Label(
                        cell, text=f"+ {len(events_for_day) - 3} autre(s)",
                        bg=bg, fg=C["muted"], anchor="w", font=ui_font(8)
                    ).pack(fill="x", padx=6)

        self.day_label.config(text=format_date_fr(self.selected_date).capitalize())
        for item in self.tree.get_children():
            self.tree.delete(item)
        todays = sorted(
            [(i, e) for i, e in enumerate(self.events) if e.get("date") == self.selected_date.isoformat()],
            key=lambda pair: pair[1].get("time", "")
        )
        for idx, e in todays:
            self.tree.insert("", "end", iid=str(idx), values=(e.get("time", ""), e.get("title", "(sans titre)")))

    def event_dialog(self, event=None):
        win = tk.Toplevel(self.root)
        win.title("Modifier le rendez-vous" if event else "Nouveau rendez-vous")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        initial = event or {
            "date": self.selected_date.isoformat(),
            "time": "09:00",
            "title": "",
            "notes": "",
        }
        try:
            chosen_date = date.fromisoformat(initial["date"])
        except ValueError:
            chosen_date = self.selected_date
        try:
            parsed = datetime.strptime(initial.get("time") or "09:00", "%H:%M")
            hour, minute = parsed.hour, parsed.minute
        except ValueError:
            hour, minute = 9, 0

        state = {"date": chosen_date, "hour": hour, "minute": minute}

        tk.Label(
            win, text="Nouveau rendez-vous" if event is None else "Modifier",
            bg=C["bg"], fg=C["ink"], font=ui_font(16, "bold")
        ).pack(anchor="w", padx=18, pady=(16, 4))

        card = tk.Frame(win, bg=C["surface"], highlightbackground=C["line"], highlightthickness=1)
        card.pack(fill="both", expand=True, padx=18, pady=8)

        tk.Label(card, text="Titre", bg=C["surface"], fg=C["muted"], font=ui_font(9, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        title_var = tk.StringVar(value=initial.get("title", ""))
        title_entry = tk.Entry(
            card, textvariable=title_var, font=ui_font(12), bg=C["white"], fg=C["ink"],
            relief="flat", highlightthickness=1, highlightbackground=C["line"], highlightcolor=C["accent"]
        )
        title_entry.pack(fill="x", padx=16, ipady=8)

        pickers = tk.Frame(card, bg=C["surface"])
        pickers.pack(fill="both", expand=True, padx=12, pady=12)

        date_box = tk.Frame(pickers, bg=C["surface"])
        date_box.pack(side="left", padx=(4, 16), anchor="n")
        tk.Label(date_box, text="Jour", bg=C["surface"], fg=C["muted"], font=ui_font(9, "bold")).pack(anchor="w")
        self._date_summary = tk.Label(
            date_box, text=format_date_fr(state["date"]).capitalize(),
            bg=C["surface"], fg=C["accent_dark"], font=ui_font(10, "bold")
        )
        self._date_summary.pack(anchor="w", pady=(0, 8))

        def on_pick_date(d):
            state["date"] = d
            self._date_summary.config(text=format_date_fr(d).capitalize())

        MiniCalendar(date_box, state["date"], on_pick_date).pack()

        clock_box = tk.Frame(pickers, bg=C["surface"])
        clock_box.pack(side="left", anchor="n")
        tk.Label(clock_box, text="Heure", bg=C["surface"], fg=C["muted"], font=ui_font(9, "bold")).pack(anchor="w")

        def on_clock(h, m):
            state["hour"], state["minute"] = h, m

        ClockPicker(clock_box, hour=hour, minute=minute, on_change=on_clock).pack()

        tk.Label(card, text="Notes", bg=C["surface"], fg=C["muted"], font=ui_font(9, "bold")).pack(anchor="w", padx=16)
        notes = tk.Text(
            card, width=34, height=4, wrap="word", font=ui_font(10),
            bg=C["white"], fg=C["ink"], relief="flat",
            highlightthickness=1, highlightbackground=C["line"], highlightcolor=C["accent"]
        )
        notes.pack(fill="x", padx=16, pady=(4, 14))
        notes.insert("1.0", initial.get("notes", ""))

        def save():
            title = title_var.get().strip()
            if not title:
                messagebox.showwarning("Titre manquant", "Saisissez un titre.", parent=win)
                return
            obj = {
                "title": title,
                "date": state["date"].isoformat(),
                "time": f"{state['hour']:02d}:{state['minute']:02d}",
                "notes": notes.get("1.0", "end-1c").strip(),
            }
            if event is None:
                self.events.append(obj)
            else:
                event.update(obj)
            save_events(self.events)
            self.selected_date = state["date"]
            win.destroy()
            self.refresh()

        buttons = tk.Frame(win, bg=C["bg"])
        buttons.pack(fill="x", padx=18, pady=(0, 16))
        tk.Button(
            buttons, text="Enregistrer", command=save, font=ui_font(10, "bold"),
            bg=C["accent"], fg=C["white"], relief="flat", padx=18, pady=9, cursor="hand2",
            activebackground=C["accent_dark"], activeforeground=C["white"]
        ).pack(side="right")
        tk.Button(
            buttons, text="Annuler", command=win.destroy, font=ui_font(10, "bold"),
            bg=C["white"], fg=C["ink"], relief="flat", padx=16, pady=9, cursor="hand2"
        ).pack(side="right", padx=(0, 8))
        title_entry.focus_set()
        win.bind("<Return>", lambda _e: save())

    def add_event(self):
        self.event_dialog()

    def pin_week_to_desktop(self):
        created = False
        if sys.platform.startswith("win"):
            created = install_desktop_button()
        root = self.root.winfo_toplevel()
        while root.master is not None:
            root = root.master
        widget = getattr(root, "week_widget", None)
        if widget is None or not widget.winfo_exists():
            widget = start_week_widget(root)
        if widget is not None:
            widget._expand()
            widget.lift()
        msg = "Un bouton « Agenda semaine » est sur votre bureau : un clic ouvre la semaine (toujours le fichier JSON local)."
        if created:
            messagebox.showinfo("Semaine sur le bureau", msg)
        elif widget is None:
            messagebox.showinfo(
                "Semaine sur le bureau",
                "Le bouton de la semaine est déjà ouvert (il lit agenda_local.json)."
            )
        else:
            messagebox.showinfo("Semaine sur le bureau", "La semaine est affichée en bouton, au-dessus des autres fenêtres.")

    def selected_index(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def edit_selected(self):
        idx = self.selected_index()
        if idx is None:
            messagebox.showinfo("Sélection", "Sélectionnez un rendez-vous dans la liste.")
            return
        self.event_dialog(self.events[idx])

    def delete_selected(self):
        idx = self.selected_index()
        if idx is None:
            messagebox.showinfo("Sélection", "Sélectionnez un rendez-vous dans la liste.")
            return
        if messagebox.askyesno("Confirmer", f"Supprimer « {self.events[idx].get('title', '')} » ?"):
            del self.events[idx]
            save_events(self.events)
            self.refresh()

    def export_json(self):
        from tkinter.filedialog import asksaveasfilename
        path = asksaveasfilename(
            title="Exporter une copie", defaultextension=".json",
            filetypes=[("Fichier JSON", "*.json")], initialfile="copie_agenda.json"
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self.events, ensure_ascii=False, indent=2), encoding="utf-8")
            messagebox.showinfo("Export terminé", f"Copie enregistrée dans :\n{path}")
        except OSError as exc:
            messagebox.showerror("Erreur d'export", str(exc))


if __name__ == "__main__":
    widget_only = "--widget" in sys.argv
    root = tk.Tk()
    if widget_only:
        root.withdraw()
        if start_week_widget(root) is None:
            root.destroy()
        else:
            if sys.platform.startswith("win") and not desktop_shortcut_path().exists():
                install_desktop_button()
            root.mainloop()
    else:
        app = AgendaApp(root)
        start_week_widget(root)
        if sys.platform.startswith("win") and not desktop_shortcut_path().exists():
            install_desktop_button()
        root.mainloop()
        release_widget_lock()
