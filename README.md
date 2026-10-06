# App Muter

Mutes the apps you pick when you tab out of them, and unmutes them when you tab back in.
Unticked apps (like your browser with YouTube) are never touched.

## 1. Run it (first time)

1. Install Python from python.org. **Tick "Add python.exe to PATH"** in the installer.
2. Put this `app-muter` folder somewhere on your PC and open it in VS Code.
3. Open the terminal in VS Code (Ctrl + `) and run:
   ```
   pip install -r requirements.txt
   python app_muter.py
   ```
4. Start Valorant (or anything with sound), click **Refresh list**, tick `valorant-win64-shipping.exe`.
5. Alt-tab out: Valorant goes silent. Tab back in: sound returns.

Your ticks are saved to `%APPDATA%\AppMuter\config.json`, so they're remembered next time.

## 2. Turn it into an .exe

Double-click `build.bat`. When it finishes, your app is `dist\AppMuter.exe`.
You can send that one file to a friend; they don't need Python.

If the .exe opens and instantly closes, build without `--noconsole` (edit `build.bat`)
so you can see the error message, and paste it to Claude.

## 3. How the code works

Think of it like a bouncer checking who's on stage 4 times a second:

- **`get_focused_process_name()`** asks Windows "which window is in front?" and turns it into an .exe name.
- **`AudioUtilities.GetAllSessions()`** (from the `pycaw` library) is the same list you see in the
  Windows Volume Mixer. Each app making sound has a "session" with its own mute button.
- **`Muter._tick()`** loops over those sessions: ticked app + not focused = mute; it's focused again = unmute.
- The loop runs in a **background thread** so the window never freezes.
- It only unmutes apps **it** muted, so if you muted something yourself in the Volume Mixer, it stays muted.
- When you close App Muter, it unmutes everything it muted, so a game never gets stuck silent.

## Limits worth knowing

- **Browsers are one app, not per tab.** Windows sees all of Chrome as `chrome.exe`, so you can mute or not mute
  the whole browser, not just one YouTube tab. That's a Windows limitation, not a bug.
- **The app with the window must be the app with the sound.** True for Valorant, Discord, Spotify and most games.
  If a game's window and audio come from two different .exe names, it'll stay muted. Use the
  "Last focused app" line at the bottom to check the window's .exe name.
- **Valorant / anti-cheat:** this only flips the same mute switch as the Windows Volume Mixer. It doesn't
  touch the game's files or memory. (That's how it works; I haven't tested it against Vanguard myself.)
- Closing the window quits the app. Minimize it to keep it running.

## Ideas for v2

- System tray icon so it hides out of the taskbar (`pystray` library).
- Start with Windows (put a shortcut to the .exe in `shell:startup`).
- Lower volume to 20% instead of fully muting.
