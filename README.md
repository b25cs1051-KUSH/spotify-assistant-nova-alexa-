# Alexa/Nova: Automated Spotify Voice Assistant & Bluetooth Controller

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Spotify Web API](https://img.shields.io/badge/Spotify-API-1ED760?logo=spotify)](https://developer.spotify.com/)
[![OS: Windows](https://img.shields.io/badge/OS-Windows-0078D4?logo=windows)](https://www.microsoft.com/windows)

Alexa/Nova is a hands-free, background voice-controlled assistant for Spotify Connect(for laptop ONLY for now). It features two core components:
1. **The Voice Daemon (`main.py`):** A speech-recognition daemon utilizing Google's Web Speech API with dual wake-word support (`Alexa` or `Nova`).
2. **The OS-Level Watcher (`spotify_watcher.py`):** An automation script that monitors Windows processes, manages the voice daemon's lifecycle, and interacts directly with Windows hardware to enable Bluetooth and connect to your speaker upon launching Spotify.

---

## 🛠️ System Architecture & Workflow

```mermaid
graph TD
    A[User Opens Spotify Desktop] --> B[spotify_watcher.py]
    B -->|Check OS Process List| C{Is Spotify Active?}
    C -->|Yes| D[WinRT Radio Manager]
    D -->|Toggles Laptop Bluetooth ON| E[WinRT Bluetooth Connector]
    E -->|Triggers connection to "your bluetooth speaker"| F[Spawn Console]
    F -->|Opens log terminal running main.py| G[main.py Voice Assistant]
    G -->|Continuous Microphone Polling| H[Google Speech Recognition]
    H -->|en-IN Accent Matching| I[Command Parser]
    I -->|Fuzzy Match & Queue Rotation| J[Spotify Connect API]
    C -->|No| K[Terminate Voice Console]
    K -->|Kills main.py Process Cleanly| L[System Idle]
```

---

## ✨ Features

### 🎛️ Windows Hardware & Bluetooth Automation
* **Automatic Bluetooth Radio Control:** Using native Windows Runtime (WinRT) APIs, the watcher checks your laptop's Bluetooth adapter. If Bluetooth is disabled, it **programmatically turns it ON**—fully natively, requiring **no administrator privileges**.
* **Direct Speaker Connection:** The watcher automatically scans your paired devices and triggers the Windows Bluetooth stack to connect to your configured speaker (e.g., `"Kush's JBL Go 4"`).
* **Developer Customization:** To connect your own speaker, open [spotify_watcher.py](file:///E:/spotify_asistant/spotify_watcher.py#L117) and replace the value of `bluetooth_device` on line 117:
  ```python
  # Line 117 in spotify_watcher.py
  bluetooth_device = "Your Bluetooth Speaker Name"
  ```
  *(The connection script uses a case-insensitive wildcard search, so if your speaker's name is "My Speaker A1", configuring "Speaker A1" will match and connect successfully).*

### 🎙️ Advanced Speech & Playback Logic
* **Double Wake Word Trigger:** Wakes up to either **"Alexa"** or **"Nova"** (along with phonetic variants like *"Alexis"*, *"Innova"*, etc.). 
  * *Acoustic note:* `"Alexa"` has a higher signal-to-noise ratio due to the sharp plosive click of the `K` sound in `X`, making it highly responsive in noisy rooms.
* **Continuous Liked Songs Queue Slicing:** Caches up to 300 Liked Songs in memory on startup. When you ask to play a song, it rotates the list so your song sits at index `0`, loading the next 99 liked songs into your active playback queue. This natively enables `play next` and `play previous` skipping!
* **Dynamic Autoplay Queue Injector:** If you play a song outside your Liked list, the assistant pulls a random sample of 10 tracks from your local Liked Songs cache in memory and appends them to the queue. This bypasses Spotify's deprecated recommendations API (avoiding 404/403 errors), operates with zero network latency, and automatically populates your queue with your favorites so skips and song ends work smoothly.
* **Automatic Ducking:** Temporarily pauses active music playback when the wake-word is triggered, creating a silent listening window for the microphone, and automatically resumes playback once the command finishes.

### 🧪 Developer Mock Mode (No Premium Required)
If you do not have Spotify Premium, are offline, or want to explore/prototype the code safely:
* Set `SPOTIFY_MOCK_MODE=True` in your `.env` file.
* This swaps the real Spotify controller for the state-managed `MockSpotifyController` which simulates all playback events, volume levels, and queue logs in memory, allowing 100% of the voice engine to run without hitting Spotify servers.

---

## 📦 Core Dependencies & Python Version Compatibility
This project is fully compatible with **Python 3.12 and 3.13** (resolving standard library deprecations under PEP 594 and PEP 632):
* `spotipy`: Handles Spotify OAuth 2.0 and Web API endpoints.
* `SpeechRecognition`: Audio capturing and Google Web Speech engine interface.
* `winrt-Windows.Devices.Bluetooth`, `winrt-Windows.Devices.Enumeration`, `winrt-Windows.Devices.Radios`: Modular C++ extension packages providing native Windows Runtime access to system hardware.
* `standard-aifc` & `setuptools` (shims): Restores compatibility for removed legacy libraries in modern Python runtimes.

---

## 📂 Git & Project Structure

The project employs a clean repository structure. The following directories are explicitly excluded via `.gitignore` to maintain security and project integrity:
* `venv/`: Local python virtual environment.
* `.env` & `.cache`: Local secret credentials and active Spotify access tokens (to prevent accidental leaks).
* `scratch/`: **Developer Sandboxes.** These files (e.g. `check_playability.py`, `test_radio.py`) were used during development to write isolated tests for API endpoints and WinRT features. They are kept ignored to maintain a clean codebase.

---

## 🚀 Setup & Installation

### 1. Spotify Developer Registration
1. Log in to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Click **Create App**:
   - **Redirect URI:** `http://127.0.0.1:8080/callback` (Required for authentication handshake).
3. Copy your **Client ID** and **Client Secret**.

### 2. Repository Setup
```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 3. Local Configuration
Create a `.env` file in the root folder of the project:
```ini
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8080/callback
SPOTIFY_MOCK_MODE=False
```

### 4. First-Time Authorization
Run the authentication script once to authenticate scopes:
```powershell
python auth.py
```
*A browser tab will open automatically. Click **Agree** to authorize your client. This generates a local `.cache` file containing your access and refresh tokens.*

---

## 🎮 How to Use

Launch the background watcher:
```powershell
python spotify_watcher.py
```
* **Spotify Startup:** Opening Spotify triggers the watcher to turn on your laptop's Bluetooth, connect to your speaker, and pop open a visible command prompt window showing the voice logs.
* **Spotify Close:** Closing Spotify terminates the console window and voice daemon automatically.

### Commands
Wake the assistant by saying **"Alexa"** or **"Nova"**. Once the microphone prompts you, say:
- `"play [song name]"` (e.g., *"play Softly by Karan Aujla"*)
- `"[song name]"` (Direct playback fallback)
- `"play album [album name]"`
- `"play artist [artist name]"`
- `"play playlist [playlist name]"`
- `"pause"` / `"resume"`
- `"play next"` / `"play previous"`
- `"volume [0-100]"`
- `"what's playing"`

---

## ⚙️ Laptop Startup Automation
To run the watcher automatically on system boot:
1. Press `Win + R`, type `shell:startup`, and hit Enter to open your Windows Startup folder.
2. Right-click, select **New > Shortcut**.
3. Set the location path (adjust to match your directory):
   ```cmd
   E:\spotify_asistant\venv\Scripts\pythonw.exe E:\spotify_asistant\spotify_watcher.py
   ```
4. Click **Finish**. The watcher will now run silently in the background from boot.
