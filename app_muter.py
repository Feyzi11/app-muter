"""
App Muter
---------
Mutes the apps you pick whenever their window is NOT the focused one,
and unmutes them the moment you tab back in.

Example: tick VALORANT-Win64-Shipping.exe -> Valorant goes silent when you
alt-tab out, and comes back when you tab in. Leave chrome.exe unticked and
YouTube keeps playing no matter what.

How it works (the 3 key pieces):
  1. get_focused_process_name()  -> asks Windows which window is in front,
                                     then which program (.exe) owns it.
  2. AudioUtilities.GetAllSessions() (pycaw) -> the same list you see in the
                                     Windows Volume Mixer: one "audio session"
                                     per app that is making sound.
  3. Muter._tick()                 -> runs 4x per second: for every ticked app,
                                     mute it if it's not focused, unmute it if
                                     it is.
"""

import ctypes
import json
import os
import threading
import tkinter as tk
from tkinter import ttk

import psutil
from comtypes import CoInitialize, CoUninitialize
from pycaw.pycaw import AudioUtilities

APP_NAME = "AppMuter"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
POLL_SECONDS = 0.25  # how often we check focus (4 times a second)

user32 = ctypes.windll.user32


# ---------------------------------------------------------------- config file

def load_config():
    """Returns the set of .exe names (lowercase) to mute when unfocused."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {name.lower() for name in data.get("mute_when_unfocused", [])}
    except (OSError, ValueError):
        return set()  # first run, or the file is broken -> start empty


def save_config(names):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"mute_when_unfocused": sorted(names)}, f, indent=2)


# ----------------------------------------------------------- windows helpers

def get_focused_process_name():
    """Name of the .exe that owns the window you're currently looking at."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).name().lower()
    except (psutil.Error, ValueError):
        return None


def session_name(session):
    """The .exe name behind an audio session, or None (e.g. system sounds)."""
    try:
        return session.Process.name().lower() if session.Process else None
    except psutil.Error:
        return None  # the app closed while we were looking at it


def get_audio_app_names():
    """All apps that currently have an audio session (what the Volume Mixer shows)."""
    names = set()
    for session in AudioUtilities.GetAllSessions():
        name = session_name(session)
        if name:
            names.add(name)
    return names


# ------------------------------------------------------------ the muting loop

class Muter(threading.Thread):
    """Background thread that does the actual muting so the window never freezes."""

    def __init__(self, targets):
        super().__init__(daemon=True)
        self.targets = set(targets)   # apps to mute when unfocused
        self.enabled = True           # master on/off switch
        self._stop_event = threading.Event()
        self._muted_by_us = set()     # only ever unmute what WE muted

    def stop(self):
        self._stop_event.set()

    def run(self):
        CoInitialize()  # Windows audio APIs (COM) must be set up per thread
        try:
            while not self._stop_event.is_set():
                try:
                    self._tick()
                except Exception as e:  # never let one bad tick kill the loop
                    print("tick error:", e)
                self._stop_event.wait(POLL_SECONDS)
            self._unmute_everything_we_muted()
        finally:
            CoUninitialize()

    def _tick(self):
        focused = get_focused_process_name()
        targets = self.targets if self.enabled else set()
        unmuted = set()

        # One app can own several sessions (browsers do), so we loop them all.
        for session in AudioUtilities.GetAllSessions():
            name = session_name(session)
            if not name:
                continue
            volume = session.SimpleAudioVolume

            if name in targets and name != focused:
                # Respect a mute you set yourself in the Volume Mixer:
                # if it's already muted, we leave it alone and don't claim it.
                if not volume.GetMute():
                    volume.SetMute(1, None)
                    self._muted_by_us.add(name)
            elif name in self._muted_by_us:
                volume.SetMute(0, None)
                unmuted.add(name)

        self._muted_by_us -= unmuted

    def _unmute_everything_we_muted(self):
        """On exit, never leave a game stuck on mute."""
        for session in AudioUtilities.GetAllSessions():
            if session_name(session) in self._muted_by_us:
                session.SimpleAudioVolume.SetMute(0, None)
        self._muted_by_us.clear()


# ----------------------------------------------------------------------- GUI

class App:
    def __init__(self, root):
        self.root = root
        self.targets = load_config()
        self.muter = Muter(self.targets)
        self.muter.start()

        root.title("App Muter")
        root.minsize(380, 300)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        top = ttk.Frame(root, padding=10)
        top.pack(fill="x")
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Enabled", variable=self.enabled_var,
                        command=self.on_toggle_enabled).pack(side="left")
        ttk.Button(top, text="Refresh list", command=self.build_list).pack(side="right")

        ttk.Label(root, padding=(10, 0),
                  text="Tick the apps to mute when you tab out of them.\n"
                       "Only apps that are playing sound (or were ticked before) show up."
                  ).pack(anchor="w")

        self.list_frame = ttk.Frame(root, padding=10)
        self.list_frame.pack(fill="both", expand=True)

        self.focus_label = ttk.Label(root, padding=10, foreground="gray")
        self.focus_label.pack(anchor="w")

        self.build_list()
        self.update_focus_label()

    def build_list(self):
        """(Re)draw one checkbox per app that has audio, plus any saved ones."""
        for child in self.list_frame.winfo_children():
            child.destroy()
        self.vars = {}
        for name in sorted(get_audio_app_names() | self.targets):
            var = tk.BooleanVar(value=name in self.targets)
            ttk.Checkbutton(self.list_frame, text=name, variable=var,
                            command=lambda n=name, v=var: self.on_toggle_app(n, v)
                            ).pack(anchor="w")
            self.vars[name] = var

    def on_toggle_app(self, name, var):
        if var.get():
            self.targets.add(name)
        else:
            self.targets.discard(name)
        # Give the thread a fresh copy so it never sees a half-edited set.
        self.muter.targets = set(self.targets)
        save_config(self.targets)

    def on_toggle_enabled(self):
        self.muter.enabled = self.enabled_var.get()

    def update_focus_label(self):
        # Handy for finding the real .exe name of a game: tab into it, tab back, read this.
        self.focus_label.config(text=f"Last focused app: {self.last_focused()}")
        self.root.after(500, self.update_focus_label)

    def last_focused(self):
        name = get_focused_process_name()
        if name and name not in ("python.exe", "pythonw.exe", "appmuter.exe"):
            self._last = name
        return getattr(self, "_last", "-")

    def on_close(self):
        self.muter.stop()
        self.muter.join(timeout=2)  # lets it unmute everything first
        self.root.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on high-DPI screens
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
