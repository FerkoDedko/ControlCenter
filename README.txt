COMMAND CENTER - MODERN BUILD

WHAT'S INCLUDED
- Dashboard: live CPU, RAM, disk and download cards with sparklines, device info,
  network activity and a list of recent alerts
- Processes: live process list (search, sort, End task)
- Storage: every drive with usage bars, plus category cards (Games, Photos,
  Videos, Music, Documents, Archives, Apps, System, Other). Press Scan, then click
  a card to see its biggest files. Scanning a whole drive can take a few minutes;
  "My user folder" is much faster. Files under Steam/Epic/etc. count as Games and
  files under Program Files count as Apps, whatever their type.
- Network: live download/upload graphs, totals, open connections, per-interface table
- Hardware: NVIDIA graphics card usage/temperature/VRAM, CPU temperature, battery,
  and a table of temperature sensors (see "Hardware notes" below)
- Cleanup: scans temp files, browser caches, crash reports and the Recycle Bin,
  shows how much you'd free, and removes only what you tick after you confirm
- App Launcher: pin your own apps and open them in one click, plus Windows tools
- Startup Manager: switch programs on or off at Windows sign-in (Windows only)
- Voice Control: say a phrase and Command Center runs steps you set up
- Settings: theme (dark / light / system), accent colour, animations, alerts,
  thresholds, refresh rate, system tray, shortcuts. Everything saves automatically.

INSTALLATION
1. Extract the ZIP over your existing project folder (say yes to replace files).
2. Open the folder in VS Code and open a terminal in it.
3. Create and activate a virtual environment (first time only):

   py -m venv .venv
   .\.venv\Scripts\Activate.ps1

   If activation is blocked:
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

4. Install packages:

   py -m pip install -r requirements.txt

   Optional extras (tray icon + voice control):

   py -m pip install -r requirements-optional.txt

5. Run:

   py main.py

SYSTEM TRAY, SHORTCUTS AND START WITH WINDOWS (Settings)
- Tray icon: needs pystray + Pillow. Left-click the icon to show/hide the window;
  right-click for Quit.
- "Closing the window keeps it running in the tray": alerts and voice commands keep
  working while the window is hidden.
- Start with Windows: adds Command Center to your sign-in programs (current user only).
  "Start hidden in the tray" makes it start without opening the window.
- Global shortcuts work anywhere in Windows:
    Show / hide  (default ctrl+alt+c)
    Voice        (default ctrl+alt+v)   starts listening for one voice command
  Write them like  ctrl+alt+c  or  win+shift+f5. If another program already uses a
  shortcut you'll get a message.

VOICE CONTROL
- Needs:  py -m pip install SpeechRecognition sounddevice
- Turn on "Allow voice recognition". Short recordings of what you say are sent to
  Google's free speech service to turn them into text. Nothing is sent while it's off.
- Push to talk (default): click the mic button or press the voice shortcut, say your
  phrase. "Always listening" keeps the microphone on; use a wake word with it.
- A command is a phrase plus steps (one per line):
    open <program, file, website or link>
    wait <seconds>
    media play_pause | next | previous | stop | volume_up | volume_down | mute
    toast <message>
  Put {word} in the phrase to catch what you say there, e.g.
    phrase:  play {song} on spotify
    steps:   open spotify:search:{song}
  Close matches count ("open spotifi" still opens Spotify).
- Spotify can't be told to play a song by name from outside. The search link above
  opens Spotify's search for what you said. To play one specific song, copy its link
  in Spotify (Share -> Copy Song Link) and use:  open <link>,  wait 4,  media play_pause.
- Windows must allow desktop apps to use the microphone (Settings -> Privacy -> Microphone).
- Your commands are stored in voice.json next to the program.

HARDWARE NOTES
- NVIDIA graphics cards are read through nvidia-smi, which comes with the NVIDIA driver.
- Windows doesn't share CPU temperatures with normal programs. For CPU temperatures
  (and other graphics cards), run the free LibreHardwareMonitor, open
  Options -> Remote Web Server -> Run, and leave it running. Command Center reads it
  automatically.
- Battery is shown on laptops.

CLEANUP NOTES
- Nothing is removed until you press "Clean selected" and confirm.
- Temp folders keep files changed in the last 24 hours. Files that are in use are
  skipped. Only the folders listed on the page are touched.
- Browser caches: close your browsers first. You stay signed in.
- Emptying the Recycle Bin is permanent.

ALERTS
- A warning only fires when a metric stays over its limit for the "Alert delay"
  (default 5 seconds), so short spikes are ignored.
- After a warning, it won't repeat until the metric has dropped a few points
  below the limit, so a value hovering around the limit can't spam you.
- "Send test alert" in Settings shows what a warning looks like.
- Delivery can be in-app, Windows notification, or both.

FILES THE APP CREATES
- config.json    your settings
- launcher.json  the apps you pinned in App Launcher
- voice.json     your voice commands

DISCORD DMs (Voice Control page, Windows only, 100% local: no bot, no API, no token)
- Install:  py -m pip install -r requirements-optional.txt
- Windows: Settings -> Privacy & security -> Notifications -> allow notification access
  for the app that runs Command Center (Python / your terminal / VS Code).
- Discord: User Settings -> Notifications -> Enable Desktop Notifications must be on.
- Switch on "Listen for new Discord DMs". New steps for your voice commands:
  "Discord: read the latest DM out loud" and "Discord: reply to the latest DM".
- Auto-Busy answers a DM for you (once per person every 5 minutes) when you count as busy.
  You choose what busy means: you're on a Discord call, a game or video is fullscreen,
  any program you add is open (or in front), or you switched "busy" on by hand.
- Replies work by pressing keys in the Discord app (Ctrl+K, name, Enter, message, Enter),
  so don't type for ~3 seconds while one is sent.

ANIMATIONS (Settings -> Appearance)
- One master switch plus a switch for each kind: page transitions, sidebar motion,
  moving side-panel pictures, bars and numbers, notifications, hover/pulse effects.
- The picture strip on the right of each page (globe, radar, gears...) hides itself
  when the window is narrower than about 1040 px.

NOTES
- Windows notifications depend on Windows notification settings. If Plyer cannot
  show one, the in-app alert still works.
- Disk monitoring looks for C: and falls back to another mounted drive.
- Startup Manager lists the "Run" registry entries and Startup folders. It switches
  items on/off the same way Task Manager does and never deletes anything.
  Machine-wide items may need the app to run as administrator.
- Ending some system processes needs administrator rights.
- The Processes list reads everything in one Windows call, so it opens instantly.

Python 3.10+ recommended.

Preset voice commands
---------------------
Voice Control -> "Add preset pack" adds: what time is it, what's the date, what's the
weather, how's my pc (CPU/memory/disk), battery, volume up/down, mute, next/previous song,
lock my pc, take a screenshot, open settings, open task manager.
In your own commands, the step "Say something out loud" can use {time} {date} {weekday}
{weather} {cpu} {memory} {disk} {battery}. The weather comes from wttr.in over the internet
and guesses your city from your IP address.

News
----
Say "what's the news" (preset pack) for the top BBC headlines, or switch on
Settings -> "When Command Center opens" -> "Read me the news" / "Tell me the weather".
For a no-fuss first run on Windows, double-click start.bat (it sets up Python packages itself).

First run
---------
A short setup asks what you want (voice, Discord, weather and news, tray) and shows a
tick or a fix for each. Terms and privacy: see TERMS_AND_PRIVACY.txt (fill in your name).
