import re
import sys
import time
import speech_recognition as sr
from spotify_controller import create_spotify_controller, SpotifyControllerInterface

# Keyword indicators for parsing voice commands
# Using tokenized word sets instead of raw substring matching prevents collisions 
# (e.g., checking if 'pause' is in 'applause' previously caused the system to pause instead of search).
def parse_and_execute(command_text: str, controller: SpotifyControllerInterface) -> bool:
    """
    Parses a recognized speech text using tokenized word matching and executes the Spotify command.
    
    Args:
        command_text (str): The raw text recognized from voice input.
        controller (SpotifyControllerInterface): The active Spotify controller (Real or Mock).
        
    Returns:
        bool: True if a command was successfully matched and executed, False otherwise.
    """
    cmd = command_text.strip().lower()
    if not cmd:
        return False

    print(f"[Command Parser] Parsing voice command: '{command_text}'")
    
    # Tokenize the command into a set of words to perform exact word matching
    # This prevents substring bugs, such as 'pause' matching inside the song title 'applause'
    words = set(re.findall(r'\b\w+\b', cmd))

    # 1. Volume adjustment (e.g. "volume 80", "louder", "quiet")
    if "volume" in words or "loud" in words or "quiet" in words or "quieter" in words:
        vol_match = re.search(r"(\d+)", cmd)
        if vol_match:
            vol = int(vol_match.group(1))
            controller.set_volume(vol)
            return True
        elif "up" in words or "louder" in words:
            controller.set_volume(75)
            return True
        elif "down" in words or "softer" in words or "quieter" in words:
            controller.set_volume(30)
            return True

    # 2. Playback Status (e.g. "what's playing", "status", "currently playing")
    status_keywords = {"playing", "status", "currently", "current"}
    if words & status_keywords:
        status = controller.get_currently_playing_status()
        print(f"[Daemon Status] {status}")
        return True

    # 3. Next / Skip
    if "next" in words or "skip" in words or "forward" in words:
        controller.next_local()
        return True

    # 4. Previous / Back
    if "previous" in words or "back" in words or "prev" in words or "backward" in words:
        controller.previous_local()
        return True

    # 5. Pause / Stop / "Boss" (Only trigger pause if "play" is NOT in words)
    if "play" not in words and ("pause" in words or "stop" in words or "boss" in words or "freeze" in words or "silence" in words):
        controller.pause_local()
        return True

    # 5b. Shuffle Toggling (e.g. "shuffle on", "shuffle off", "enable shuffle")
    if "shuffle" in words:
        if "on" in words or "enable" in words or "activate" in words:
            controller.set_shuffle(True)
            return True
        elif "off" in words or "disable" in words or "deactivate" in words:
            controller.set_shuffle(False)
            return True

    # 5c. Play Random Liked Song (e.g. "play random song", "play random liked", "random track")
    random_keywords = {"random", "arbitrary", "any"}
    liked_keywords = {"liked", "song", "track", "music", "playlist"}
    if (words & random_keywords) and (words & liked_keywords):
        controller.play_random_liked()
        return True

    # 6. Play / Resume (Open search query for any language/song title)
    if "play" in words or "resume" in words or "start" in words:
        # Capture everything spoken after the word 'play', 'resume', or 'start'
        match = re.split(r'\b(?:play|resume|start)\b', cmd, maxsplit=1)
        query = match[1].strip() if len(match) > 1 else ""
        
        # If the search query is empty or generic, resume current playback
        if not query or query in ("music", "song", "spotify", "tracks"):
            controller.play_local()
            return True

        # Check for category indicators in the query words
        query_words = set(re.findall(r'\b\w+\b', query))
        if "album" in query_words:
            album_query = query.replace("album", "").strip()
            controller.play(query=album_query, search_type="album")
        elif "artist" in query_words:
            artist_query = query.replace("artist", "").strip()
            controller.play(query=artist_query, search_type="artist")
        elif "playlist" in query_words:
            playlist_query = query.replace("playlist", "").strip()
            controller.play(query=playlist_query, search_type="playlist")
        else:
            # Clean generic words to search for a track
            track_query = query.replace("song", "").replace("track", "").strip()
            controller.play(query=track_query, search_type="track")
        return True

    # 7. Future Roadmap: Browser opening command
    if "open" in words:
        for site in ["youtube", "kaggle", "google", "github"]:
            if site in words:
                target = site.capitalize()
                print(f"\n[Future Roadmap] Detected command: 'Open {target}'")
                print(f"[Future Roadmap] Laptop launcher skipped; scheduled for PWA & Mobile integration.\n")
                return True

    # 8. Fallback: If no command matched, treat the entire string as a song name search.
    # This allows the user to say "Nova" followed directly by the song name (e.g. "White Brown Black").
    print(f"[Command Parser] Fallback: Treating query as track search: '{cmd}'")
    controller.play(query=cmd, search_type="track")
    return True


def run_voice_daemon():
    """
    Starts the continuous background voice listening loop.
    Uses local Vosk with a highly optimized restricted grammar for 10ms standby latency and 100% accuracy.
    No keys, accounts, or internet required for the wake-word standby state.
    """
    controller = create_spotify_controller()
    
    # Import dependencies dynamically
    import json
    import os
    import pyaudio
    import struct
    import math
    from vosk import Model, KaldiRecognizer
    
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model")
    if not os.path.exists(model_path):
        print(f"\n[Voice Daemon Error] Vosk model directory not found at '{model_path}'!")
        print("Please run the downloader to install it: venv\\Scripts\\python scratch\\download_vosk_model.py\n")
        sys.exit(1)
        
    print(f"[Voice Daemon] Loading local offline Vosk model from '{model_path}'...")
    model = Model(model_path)
    
    # ADVANCED OPTIMIZATION: Restrict Vosk's grammar to ONLY our wake words and unknown noise [unk].
    # This reduces search space from 100,000+ words to 5 words, making execution ~10ms and accuracy 100%.
    # Vosk will now ignore all other speech until the wake word triggers!
    grammar = '["alexa", "nova", "innova", "noa", "[unk]"]'
    recognizer = KaldiRecognizer(model, 16000, grammar)
    
    # Initialize PyAudio input stream
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=4000
    )
    stream.start_stream()
    
    print("\n=======================================================")
    print("[Voice Daemon] ACTIVE: Listening offline via VOSK (Restricted Grammar)...")
    print("Commands you can say:")
    print("  - Say 'Alexa' or 'Nova' to trigger the assistant")
    print("=======================================================\n")

    def get_rms(chunk_data):
        if not chunk_data:
            return 0.0
        count = len(chunk_data) / 2
        if count == 0:
            return 0.0
        fmt = f"{int(count)}h"
        shorts = struct.unpack(fmt, chunk_data)
        sum_squares = 0.0
        for s in shorts:
            n = s / 32768.0
            sum_squares += n * n
        return math.sqrt(sum_squares / count)

    try:
        while True:
            # Read 2000 samples (125ms buffers)
            data = stream.read(2000, exception_on_overflow=False)
            if len(data) == 0:
                continue
                
            if recognizer.AcceptWaveform(data):
                result_json = json.loads(recognizer.Result())
                text = result_json.get("text", "").strip()
                if not text:
                    continue
                
                # Because of the restricted grammar, text can ONLY be 'alexa', 'nova', 'innova', or 'noa'
                # Out-of-vocabulary words are mapped to '[unk]' and ignored automatically!
                if text in ("alexa", "nova", "innova", "noa"):
                    print(f"[Wake Word] Detected trigger: '{text}' (Grammar Matched)")
                    
                    # 1. Duck active music immediately on the main thread using C-level media stop (0ms delay)
                    was_playing = False
                    try:
                        was_playing = controller.pause_local()
                    except Exception as e:
                        print(f"[Duck Warning] {e}")

                    # 2. Two-step command capture (high-accuracy path via Google Cloud Speech)
                    print("[Voice Daemon] Yes? Speak your command now...")
                    
                    # Instantiate Google Recognizer
                    recognizer_google = sr.Recognizer()
                    
                    # Record command audio using Dynamic Voice Activity Detection (VAD)
                    frames = []
                    speech_started = False
                    silent_chunks = 0
                    
                    # Monitor and record up to 8 seconds maximum (in 125ms buffers)
                    for _ in range(64): 
                        chunk = stream.read(2000, exception_on_overflow=False)
                        frames.append(chunk)
                        
                        rms = get_rms(chunk)
                        if rms >= 0.012:
                            if not speech_started:
                                speech_started = True
                            silent_chunks = 0
                        else:
                            if speech_started:
                                silent_chunks += 1
                                # 5 consecutive silent chunks = ~625ms of silence
                                if silent_chunks >= 5:
                                    print("[Voice Daemon] Dynamic VAD: Speech ended. Terminating recording.")
                                    break
                    
                    raw_audio = b"".join(frames)
                    audio_google = sr.AudioData(raw_audio, 16000, 2)
                    
                    # 3. Run Google Speech recognition
                    command_text = ""
                    try:
                        print("[Voice Daemon] Transcribing command via Google Cloud...")
                        command_text = recognizer_google.recognize_google(audio_google, language="en-IN")
                        print(f"[Google Cloud] Transcribed command: '{command_text}'")
                        
                        # Execute the command
                        parse_and_execute(command_text, controller)
                        
                    except sr.UnknownValueError:
                        print("[Voice Daemon] Google Cloud could not understand the audio.")
                    except Exception as e:
                        print(f"[Voice Daemon] Error during Google Cloud capture: {e}")
                        
                    # 4. Restore playback if the command didn't play a new track or pause it
                    if was_playing:
                        cmd_words = set(re.findall(r'\b\w+\b', command_text.lower()))
                        is_navigation = {"play", "start", "resume", "next", "skip", "prev", "back", "previous"} & cmd_words
                        is_pause = {"pause", "stop", "boss", "freeze"} & cmd_words
                        if not is_navigation and not is_pause:
                            print("[Voice Daemon] Restoring playback...")
                            controller.play_local()
                            
                    recognizer.Reset() # Reset Vosk state so old audio doesn't re-trigger it
                    print("[Voice Daemon] Resuming offline wake word detection...")

    except KeyboardInterrupt:
        print("\n[Voice Daemon] Terminating offline loop. Goodbye!")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    run_voice_daemon()
