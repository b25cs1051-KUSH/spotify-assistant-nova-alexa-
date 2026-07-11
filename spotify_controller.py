import time
from typing import Optional, Dict, Any, List
import spotipy
from spotipy.exceptions import SpotifyException

class SpotifyControllerInterface:
    """
    Abstract Interface for Spotify control.
    This defines the contract that both Real and Mock controllers must implement.
    In software engineering, this is known as the Dependency Inversion Principle 
    (the 'D' in SOLID principles), allowing the client code to be decoupled from 
    the actual API implementation.
    """
    def get_devices(self) -> List[Dict[str, Any]]:
        raise NotImplementedError
        
    def get_active_device(self) -> Optional[Dict[str, Any]]:
        raise NotImplementedError
        
    def ensure_active_device(self) -> bool:
        raise NotImplementedError
        
    def play(self, query: Optional[str] = None, search_type: str = "track") -> bool:
        raise NotImplementedError
        
    def pause(self) -> bool:
        raise NotImplementedError
        
    def next(self) -> bool:
        raise NotImplementedError
        
    def previous(self) -> bool:
        raise NotImplementedError
        
    def set_volume(self, volume_percent: int) -> bool:
        raise NotImplementedError
        
    def get_currently_playing_status(self) -> str:
        raise NotImplementedError

    def is_currently_playing(self) -> bool:
        """Helper to check if music is actively playing."""
        raise NotImplementedError

    def set_shuffle(self, state: bool) -> bool:
        """Enables or disables playback shuffle."""
        raise NotImplementedError

    def play_random_liked(self) -> bool:
        """Plays a random song from liked songs cache and rotates the queue around it."""
        raise NotImplementedError

    def play_local(self) -> bool:
        """Simulates native keyboard Media Play/Pause to resume playback instantly."""
        raise NotImplementedError

    def pause_local(self) -> bool:
        """Simulates native keyboard Media Stop to pause playback instantly."""
        raise NotImplementedError

    def next_local(self) -> bool:
        """Simulates native keyboard Media Next to skip tracks instantly."""
        raise NotImplementedError

    def previous_local(self) -> bool:
        """Simulates native keyboard Media Previous to go back instantly."""
        raise NotImplementedError


import re

def clean_spotify_query(query: str, search_type: str = "track") -> str:
    """
    Cleans and optimizes a voice search query for Spotify's search API.
    - If search_type is 'track' and the query contains 'by' or 'of' (e.g. 'starboy by weekend'),
      it reformats the query using Spotify API filters (e.g. 'track:"starboy" artist:"the weeknd"').
    - Maps common phonetic/spelling misspellings (e.g. 'weekend' -> 'the weeknd') to ensure high accuracy.
    """
    q = query.strip().lower()
    
    # Common phonetic or short-form mappings for popular artists
    artist_mappings = {
        "weekend": "the weeknd",
        "taylor": "taylor swift",
        "ariana": "ariana grande",
        "cold play": "coldplay"
    }

    # Only apply "track by artist" query formatting if we are searching for a track
    if search_type == "track":
        for connector in [" by ", " of "]:
            if connector in q:
                parts = q.split(connector, 1)
                track_name = parts[0].strip()
                artist_name = parts[1].strip()
                
                if artist_name in artist_mappings:
                    artist_name = artist_mappings[artist_name]
                    
                return f"track:\"{track_name}\" artist:\"{artist_name}\""

    # Clean generic filler words for all search types
    words = q.split()
    cleaned_words = [w for w in words if w not in ["song", "track", "music", "spotify"]]
    cleaned = " ".join(cleaned_words)
    
    # Apply phonetic mappings for artists
    for key, val in artist_mappings.items():
        if key in cleaned:
            cleaned = re.sub(rf"\b{re.escape(key)}\b", val, cleaned)
            
    return cleaned


class RealSpotifyController(SpotifyControllerInterface):
    """
    Concrete implementation of SpotifyController interfacing with the real Spotify Web API.
    """
    def __init__(self, spotify_client: spotipy.Spotify):
        self.sp = spotify_client
        self.liked_tracks_cache = {}
        self.liked_track_names = []
        self.liked_track_uris = []
        self._cache_liked_songs()

    def _cache_liked_songs(self):
        """
        Queries the user's Spotify library on startup to cache their liked tracks (up to 300 songs).
        Allows instant local fuzzy matching and context queue reconstruction.
        """
        try:
            offset = 0
            limit = 50
            while len(self.liked_track_names) < 300:
                results = self.sp.current_user_saved_tracks(limit=limit, offset=offset)
                items = results.get("items", [])
                if not items:
                    break
                for item in items:
                    track = item.get("track", {})
                    if not track:
                        continue
                    name = track.get("name", "").strip().lower()
                    uri = track.get("uri")
                    if name and uri:
                        if name not in self.liked_tracks_cache:
                            self.liked_tracks_cache[name] = uri
                            self.liked_track_names.append(name)
                            self.liked_track_uris.append(uri)
                offset += limit
            print(f"[Real Spotify] Cached {len(self.liked_track_names)} liked songs for local fuzzy matching and queue slicing.")
        except Exception as e:
            print(f"[Real Spotify] Warning: Could not cache liked songs ({e}). Proceeding without cache.")

    def get_devices(self) -> List[Dict[str, Any]]:
        try:
            results = self.sp.devices()
            return results.get("devices", [])
        except SpotifyException as e:
            print(f"[Real Spotify] Error fetching devices: {e}")
            return []

    def get_active_device(self) -> Optional[Dict[str, Any]]:
        devices = self.get_devices()
        for device in devices:
            if device.get("is_active"):
                return device
        return None

    def ensure_active_device(self) -> bool:
        active_device = self.get_active_device()
        if active_device:
            return True
            
        devices = self.get_devices()
        if not devices:
            print("[Real Spotify] No Spotify devices found. Please open Spotify on a device.")
            return False
            
        target_device = devices[0]
        device_id = target_device.get("id")
        print(f"[Real Spotify] Activating device: {target_device.get('name')}...")
        try:
            self.sp.transfer_playback(device_id=device_id, force_play=False)
            time.sleep(0.8)
            return True
        except SpotifyException as e:
            print(f"[Real Spotify] Failed to transfer playback: {e}")
            return False

    def play(self, query: Optional[str] = None, search_type: str = "track") -> bool:
        def _execute_play():
            if not query:
                try:
                    self.sp.start_playback()
                    print("[Real Spotify] Playback resumed.")
                except SpotifyException as e:
                    if e.http_status == 403 and "Restriction violated" in str(e):
                        print("[Real Spotify] Playback is already active.")
                    else:
                        raise e
                return True

            try:
                self.sp.shuffle(state=False)
            except Exception:
                pass

            if search_type == "track" and self.liked_track_names:
                import difflib
                q_lower = query.strip().lower()
                track_part = q_lower
                for connector in [" by ", " of "]:
                    if connector in q_lower:
                        track_part = q_lower.split(connector, 1)[0].strip()
                        break
                
                matches = difflib.get_close_matches(track_part, self.liked_track_names, n=1, cutoff=0.8)
                if matches:
                    matched_name = matches[0]
                    matched_index = self.liked_track_names.index(matched_name)
                    ordered_uris = self.liked_track_uris[matched_index:] + self.liked_track_uris[:matched_index]
                    sliced_uris = ordered_uris[:100]
                    
                    print(f"[Real Spotify] Fuzzy Match Found in Liked Songs: '{matched_name}' -> playing cached sequence of {len(sliced_uris)} tracks.")
                    self.sp.start_playback(uris=sliced_uris)
                    return True
                
            cleaned_query = clean_spotify_query(query, search_type)
            print(f"[Real Spotify] Searching for {search_type}: '{cleaned_query}' (original: '{query}')...")
            results = self.sp.search(q=cleaned_query, limit=1, type=search_type, market="from_token")
            type_key = search_type + "s"
            items = results.get(type_key, {}).get("items", [])
            
            if not items:
                print(f"[Real Spotify] No {search_type} found for: '{query}'")
                return False
                
            item = items[0]
            item_uri = item.get("uri")
            item_name = item.get("name")
            
            if search_type == "track":
                artist_name = item.get("artists", [{}])[0].get("name", "Unknown Artist")
                print(f"[Real Spotify] Playing Track: '{item_name}' by {artist_name}")
                autoplay_uris = []
                if self.liked_track_uris:
                    import random
                    autoplay_uris = random.sample(self.liked_track_uris, min(10, len(self.liked_track_uris)))
                    print(f"[Real Spotify] Autoplay: Loaded {len(autoplay_uris)} liked tracks into the queue.")
                self.sp.start_playback(uris=[item_uri] + autoplay_uris)
            else:
                print(f"[Real Spotify] Playing {search_type.capitalize()}: '{item_name}'")
                self.sp.start_playback(context_uri=item_uri)
            return True

        try:
            return _execute_play()
        except SpotifyException as e:
            if e.http_status == 404:
                print("[Real Spotify] No active device. Attempting to activate...")
                if self.ensure_active_device():
                    try:
                        return _execute_play()
                    except Exception as retry_err:
                        print(f"[Real Spotify] Retry play failed: {retry_err}")
            print(f"[Real Spotify] Playback error: {e}")
            return False

    def pause(self) -> bool:
        def _execute():
            self.sp.pause_playback()
            print("[Real Spotify] Playback paused.")
            return True
        try:
            return _execute()
        except SpotifyException as e:
            if e.http_status == 404:
                print("[Real Spotify] No active device. Attempting to activate...")
                if self.ensure_active_device():
                    try:
                        return _execute()
                    except Exception:
                        pass
            if e.http_status == 403 and "Restriction violated" in str(e):
                print("[Real Spotify] Playback is already paused.")
                return False
            print(f"[Real Spotify] Error pausing: {e}")
            return False

    def next(self) -> bool:
        def _execute():
            self.sp.next_track()
            print("[Real Spotify] Skipped to next track.")
            return True
        try:
            return _execute()
        except SpotifyException as e:
            if e.http_status == 404:
                print("[Real Spotify] No active device. Attempting to activate...")
                if self.ensure_active_device():
                    try:
                        return _execute()
                    except Exception:
                        pass
            print(f"[Real Spotify] Error skipping: {e}")
            return False

    def previous(self) -> bool:
        def _execute():
            self.sp.previous_track()
            print("[Real Spotify] Returned to previous track.")
            return True
        try:
            return _execute()
        except SpotifyException as e:
            if e.http_status == 404:
                print("[Real Spotify] No active device. Attempting to activate...")
                if self.ensure_active_device():
                    try:
                        return _execute()
                    except Exception:
                        pass
            if e.http_status == 403 and "Restriction violated" in str(e):
                print("[Real Spotify] Cannot go back: No previous track in this context.")
                return True
            print(f"[Real Spotify] Error going back: {e}")
            return False

    def set_volume(self, volume_percent: int) -> bool:
        level = max(0, min(100, volume_percent))
        def _execute():
            self.sp.volume(volume_percent=level)
            print(f"[Real Spotify] Volume set to {level}%.")
            return True
        try:
            return _execute()
        except SpotifyException as e:
            if e.http_status == 404:
                print("[Real Spotify] No active device. Attempting to activate...")
                if self.ensure_active_device():
                    try:
                        return _execute()
                    except Exception:
                        pass
            print(f"[Real Spotify] Error setting volume: {e}")
            return False

    def get_currently_playing_status(self) -> str:
        try:
            playback = self.sp.current_playback()
            if not playback:
                return "Nothing is currently playing (Spotify is idle)."
            item = playback.get("item")
            if not item:
                return "Nothing is currently playing (Spotify is idle)."
            track_name = item.get("name")
            artists = ", ".join([artist.get("name", "") for artist in item.get("artists", [])])
            is_playing = playback.get("is_playing", False)
            state_str = "Currently playing" if is_playing else "Currently paused"
            return f"{state_str}: '{track_name}' by {artists}."
        except SpotifyException as e:
            return f"[Real Spotify] Error reading playback: {e}"

    def is_currently_playing(self) -> bool:
        try:
            playback = self.sp.current_playback()
            return playback is not None and playback.get("is_playing", False)
        except Exception:
            return False

    def set_shuffle(self, state: bool) -> bool:
        def _execute():
            self.sp.shuffle(state=state)
            state_str = "ON" if state else "OFF"
            print(f"[Real Spotify] Shuffle set to {state_str}.")
            return True
        try:
            return _execute()
        except SpotifyException as e:
            if e.http_status == 404:
                print("[Real Spotify] No active device. Attempting to activate...")
                if self.ensure_active_device():
                    try:
                        return _execute()
                    except Exception:
                        pass
            print(f"[Real Spotify] Error toggling shuffle: {e}")
            return False

    def play_random_liked(self) -> bool:
        if not self.liked_track_uris:
            print("[Real Spotify] Liked songs cache is empty. Attempting to refresh...")
            self._cache_liked_songs()
            if not self.liked_track_uris:
                print("[Real Spotify] No liked songs available.")
                return False
        
        import random
        rand_idx = random.randint(0, len(self.liked_track_uris) - 1)
        rand_uri = self.liked_track_uris[rand_idx]
        rand_name = self.liked_track_names[rand_idx]
        sliced_uris = [
            rand_uri,
            *self.liked_track_uris[rand_idx + 1:],
            *self.liked_track_uris[:rand_idx]
        ][:100]

        def _execute():
            try:
                self.sp.shuffle(state=False)
            except Exception:
                pass
            self.sp.start_playback(uris=sliced_uris)
            print(f"[Real Spotify] Playing Random Liked Track: '{rand_name}' (rotating queue around it).")
            return True

        try:
            return _execute()
        except SpotifyException as e:
            if e.http_status == 404:
                print("[Real Spotify] No active device. Attempting to activate...")
                if self.ensure_active_device():
                    try:
                        return _execute()
                    except Exception:
                        pass
            print(f"[Real Spotify] Error playing random liked track: {e}")
            return False

    def play_local(self) -> bool:
        import ctypes
        VK_MEDIA_PLAY_PAUSE = 0xB3
        try:
            ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 2, 0)
            print("[Local OS] Resuming playback via media keys shortcut (0ms delay).")
            return True
        except Exception as e:
            print(f"[Local OS] Failed to send play shortcut: {e}")
            return False

    def pause_local(self) -> bool:
        import ctypes
        VK_MEDIA_STOP = 0xB2
        try:
            ctypes.windll.user32.keybd_event(VK_MEDIA_STOP, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MEDIA_STOP, 0, 2, 0)
            print("[Local OS] Pausing playback via media stop shortcut (0ms delay).")
            return True
        except Exception as e:
            print(f"[Local OS] Failed to send pause shortcut: {e}")
            return False

    def next_local(self) -> bool:
        import ctypes
        VK_MEDIA_NEXT = 0xB0
        try:
            ctypes.windll.user32.keybd_event(VK_MEDIA_NEXT, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MEDIA_NEXT, 0, 2, 0)
            print("[Local OS] Skipping to next track via media shortcut (0ms delay).")
            return True
        except Exception as e:
            print(f"[Local OS] Failed to send next shortcut: {e}")
            return False

    def previous_local(self) -> bool:
        import ctypes
        VK_MEDIA_PREV = 0xB1
        try:
            ctypes.windll.user32.keybd_event(VK_MEDIA_PREV, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MEDIA_PREV, 0, 2, 0)
            print("[Local OS] Returning to previous track via media shortcut (0ms delay).")
            return True
        except Exception as e:
            print(f"[Local OS] Failed to send previous shortcut: {e}")
            return False


class MockSpotifyController(SpotifyControllerInterface):
    """
    Mock implementation of SpotifyController.
    Maintains a simulated state in memory to allow full testing without Spotify Premium
    or an internet connection. Extremely useful for offline prototyping and mobile development testing.
    """
    def __init__(self):
        self._is_playing = False
        self._current_track = "Simulated Track"
        self._current_artist = "Mock Artist"
        self._volume = 50
        self._search_history: List[str] = []
        print("[Mock Spotify] Initialized in Mock Mode. No Spotify account connection required.")

    def get_devices(self) -> List[Dict[str, Any]]:
        return [{"id": "mock_device_1", "name": "Mock Laptop Speaker", "type": "Computer", "is_active": True}]

    def get_active_device(self) -> Optional[Dict[str, Any]]:
        return self.get_devices()[0]

    def ensure_active_device(self) -> bool:
        return True  # Mock device is always active

    def play(self, query: Optional[str] = None, search_type: str = "track") -> bool:
        if not query:
            self._is_playing = True
            print(f"[Mock Spotify] Resumed playback: '{self._current_track}' by {self._current_artist}.")
            return True
            
        # Simulate search and selection
        self._search_history.append(query)
        self._current_track = query.title()
        self._is_playing = True
        
        if search_type == "track":
            self._current_artist = "Mock Artist"
            print(f"[Mock Spotify] Playing Track: '{self._current_track}' by {self._current_artist}.")
        elif search_type == "album":
            self._current_artist = "Mock Artist"
            print(f"[Mock Spotify] Playing Album: '{self._current_track}' by {self._current_artist}.")
        elif search_type == "artist":
            self._current_artist = query.title()
            self._current_track = "Top Hit Song"
            print(f"[Mock Spotify] Playing Artist Radio: {self._current_artist}.")
        elif search_type == "playlist":
            self._current_artist = "Various Artists"
            print(f"[Mock Spotify] Playing Playlist: '{self._current_track}'.")
            
        return True

    def pause(self) -> bool:
        self._is_playing = False
        print("[Mock Spotify] Playback paused.")
        return True

    def next(self) -> bool:
        self._current_track = "Next Mock Song"
        self._current_artist = "Next Mock Artist"
        self._is_playing = True
        print(f"[Mock Spotify] Skipped to next track: '{self._current_track}' by {self._current_artist}.")
        return True

    def previous(self) -> bool:
        self._current_track = "Previous Mock Song"
        self._current_artist = "Previous Mock Artist"
        self._is_playing = True
        print(f"[Mock Spotify] Returned to previous track: '{self._current_track}' by {self._current_artist}.")
        return True

    def set_volume(self, volume_percent: int) -> bool:
        self._volume = max(0, min(100, volume_percent))
        print(f"[Mock Spotify] Volume updated to {self._volume}%.")
        return True

    def get_currently_playing_status(self) -> str:
        if not self._is_playing:
            return "Nothing is currently playing (Mock Spotify is paused)."
        return f"Currently playing (MOCK): '{self._current_track}' by {self._current_artist}."

    def is_currently_playing(self) -> bool:
        return self._is_playing

    def set_shuffle(self, state: bool) -> bool:
        state_str = "ON" if state else "OFF"
        print(f"[Mock Spotify] Shuffle toggled to {state_str}.")
        return True

    def play_random_liked(self) -> bool:
        self._current_track = "Random Liked Song"
        self._current_artist = "Random Artist"
        print(f"[Mock Spotify] Playing Random Liked Track: '{self._current_track}' by {self._current_artist}.")
        return True

    def play_local(self) -> bool:
        self._is_playing = True
        print("[Mock Spotify] Play/Pause simulated locally.")
        return True

    def pause_local(self) -> bool:
        self._is_playing = False
        print("[Mock Spotify] Pause simulated locally.")
        return True

    def next_local(self) -> bool:
        self._current_track = "Next Mock Song"
        print("[Mock Spotify] Next track simulated locally.")
        return True

    def previous_local(self) -> bool:
        self._current_track = "Prev Mock Song"
        print("[Mock Spotify] Prev track simulated locally.")
        return True


def create_spotify_controller() -> SpotifyControllerInterface:
    """
    Factory function to initialize either the real or mock Spotify controller
    based on the SPOTIFY_MOCK_MODE flag set in the environment variables.
    
    Returns:
        SpotifyControllerInterface: An instance of either RealSpotifyController or MockSpotifyController.
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    # We default to Mock Mode if the env flag is set, or if credentials are missing
    mock_mode = os.getenv("SPOTIFY_MOCK_MODE", "False").lower() in ("true", "1", "yes")
    
    if mock_mode:
        return MockSpotifyController()
        
    try:
        from auth import get_spotify_client
        client = get_spotify_client()
        return RealSpotifyController(client)
    except Exception as e:
        print(f"\n[Factory Warning] Failed to initialize Real Spotify client ({e}).")
        print("[Factory Warning] Falling back to Mock Spotify Controller for offline simulation.")
        return MockSpotifyController()


if __name__ == "__main__":
    print("Testing Spotify Controller Factory...")
    # Explicitly test mock mode first
    controller = MockSpotifyController()
    print(controller.get_currently_playing_status())
    controller.play("Blinding Lights", "track")
    print(controller.get_currently_playing_status())
    controller.set_volume(75)
    controller.pause()
    print(controller.get_currently_playing_status())
