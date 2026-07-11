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
        controller.next()
        return True

    # 4. Previous / Back
    if "previous" in words or "back" in words or "prev" in words or "backward" in words:
        controller.previous()
        return True

    # 5. Pause / Stop / "Boss" (Only trigger pause if "play" is NOT in words)
    if "play" not in words and ("pause" in words or "stop" in words or "boss" in words or "freeze" in words or "silence" in words):
        controller.pause()
        return True

    # 6. Play / Resume (Open search query for any language/song title)
    if "play" in words or "resume" in words or "start" in words:
        # Capture everything spoken after the word 'play', 'resume', or 'start'
        match = re.split(r'\b(?:play|resume|start)\b', cmd, maxsplit=1)
        query = match[1].strip() if len(match) > 1 else ""
        
        # If the search query is empty or generic, resume current playback
        if not query or query in ("music", "song", "spotify", "tracks"):
            controller.play()
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
    
    This function:
    1. Initializes the Spotify Controller (Mock/Real based on env).
    2. Calibrates the microphone for ambient noise.
    3. Listens for the wake word "Nova" in a loop.
    4. Upon hearing "Nova", temporarily silences music (if playing) and listens for instructions.
    5. Automatically recovers from network connection issues or silence timeouts.
    """
    controller = create_spotify_controller()
    
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()

    # Interview Prep Tip: Adjusting for ambient noise helps calculate the energy threshold.
    # The speech recognition library uses this threshold to differentiate speech from background static.
    print("[Voice Daemon] Calibrating microphone for background noise. Please stand by...")
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=2)
        # Set dynamic energy threshold parameters to be more responsive
        recognizer.dynamic_energy_threshold = True
        
    print("\n=======================================================")
    print("[Voice Daemon] ACTIVE and listening for wake word 'ALEXA' or 'NOVA'...")
    print("Commands you can say:")
    print("  - 'Alexa' / 'Nova' (waits for your command)")
    print("  - 'Alexa play Starboy'")
    print("  - 'Alexa pause' / 'Alexa resume'")
    print("  - 'Alexa volume 80'")
    print("  - 'Alexa what's playing'")
    print("=======================================================\n")

    while True:
        try:
            with microphone as source:
                # Continuous listening for the wake word
                audio = recognizer.listen(source, timeout=7, phrase_time_limit=4)
                
            # Perform speech-to-text using Google Web Speech API.
            # Switching language to en-IN (Indian English) significantly increases accuracy 
            # for Indian accents and Hindi song titles (e.g. "Tum Hi Ho", "Jab We Met").
            text = recognizer.recognize_google(audio, language="en-IN")
            
            # Check if user mentioned the wake word or phonetic variations (Nova or Alexa)
            wake_word_variations = [
                "nova", "innova", "noa", "know a", "knows a", "novaa",
                "alexa", "alexis", "alexa's", "eleanor", "elixir"
            ]
            text_lower = text.lower()
            matched_wake_word = None
            
            for variation in wake_word_variations:
                if variation in text_lower:
                    matched_wake_word = variation
                    break
            
            if matched_wake_word:
                print(f"[Wake Word] Detected trigger phrase: '{text}' (matched: '{matched_wake_word}')")
                
                # Split by the matched wake word to extract the command
                parts = re.split(rf"\b{re.escape(matched_wake_word)}\b", text_lower, flags=re.IGNORECASE)
                command_part = parts[-1].strip() if len(parts) > 1 else ""
                
                # If command_part contains wake word again (e.g. "nova nova"), clean it
                for variation in wake_word_variations:
                    command_part = command_part.replace(variation, "").strip()
                
                if command_part:
                    # Execute direct command immediately (e.g. "Nova play Starboy")
                    parse_and_execute(command_part, controller)
                else:
                    # Multi-turn interaction (e.g. user just said "Nova")
                    was_playing = controller.is_currently_playing()
                    if was_playing:
                        print("[Wake Word] Silencing current playback for listening environment...")
                        controller.pause()
                        
                    print("[Voice Daemon] Yes? Listening for command...")
                    
                    # Listen for the follow-up command with a tighter window
                    try:
                        with microphone as source:
                            command_audio = recognizer.listen(source, timeout=4, phrase_time_limit=5)
                        command_text = recognizer.recognize_google(command_audio, language="en-IN")
                        print(f"[Voice Daemon] Heard: '{command_text}'")
                        
                        # Execute command
                        parse_and_execute(command_text, controller)
                        
                        # Resume playback if the command did not already start, resume, or stop the player.
                        # This prevents "403 Restriction Violated" errors when calling play() on an already playing track.
                        cmd_words = set(re.findall(r'\b\w+\b', command_text.lower()))
                        if was_playing and not ({"pause", "stop", "boss", "play", "resume", "start"} & cmd_words):
                            print("[Voice Daemon] Restoring playback...")
                            controller.play()
                            
                    except sr.WaitTimeoutError:
                        print("[Voice Daemon] Listening timed out. No command heard.")
                        if was_playing:
                            print("[Voice Daemon] Restoring playback...")
                            controller.play()
                    except sr.UnknownValueError:
                        print("[Voice Daemon] Could not understand the command.")
                        if was_playing:
                            print("[Voice Daemon] Restoring playback...")
                            controller.play()
                    except Exception as e:
                        print(f"[Voice Daemon] Error capturing command: {e}")
                        if was_playing:
                            controller.play()
                            
        except sr.WaitTimeoutError:
            # Silence timeout is expected when nobody is speaking. Loop again.
            continue
        except sr.UnknownValueError:
            # Noise was detected but no speech recognized. Loop again.
            continue
        except sr.RequestError as e:
            print(f"[System Error] Speech recognition request failed; check network: {e}", file=sys.stderr)
            time.sleep(2)
        except KeyboardInterrupt:
            print("\n[Voice Daemon] Terminating daemon. Goodbye!")
            sys.exit(0)
        except Exception as e:
            print(f"[System Error] Unexpected error in listening loop: {e}", file=sys.stderr)
            time.sleep(1)


if __name__ == "__main__":
    run_voice_daemon()
