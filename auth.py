import os
import sys
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Load environment variables from .env file
load_dotenv()

# Define the scopes required for our voice control features.
# - user-modify-playback-state: Allows us to play, pause, skip, and change volume.
# - user-read-playback-state: Allows us to check which device is active and see what is currently playing.
# - user-read-private: Required when using market="from_token" in searches to filter by country.
# - user-library-read: Required to fetch and cache user's Liked Songs for local fuzzy matching.
SCOPES = "user-modify-playback-state user-read-playback-state user-read-private user-library-read"

def get_spotify_client() -> spotipy.Spotify:
    """
    Initializes and returns an authenticated Spotify client using Spotipy's OAuth 2.0.
    
    This function:
    1. Loads credentials from environment variables.
    2. Validates that the Client ID, Client Secret, and Redirect URI are set.
    3. Handles OAuth flow, generating a local '.cache' file containing the access token.
    4. Auto-refreshes the access token if it is expired.
    
    Returns:
        spotipy.Spotify: An authenticated client instance.
        
    Raises:
        ValueError: If environment variables are missing.
    """
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
    
    if not client_id or client_id == "your_spotify_client_id_here":
        raise ValueError("SPOTIFY_CLIENT_ID is not configured in the .env file. Please check your setup.")
    if not client_secret or client_secret == "your_spotify_client_secret_here":
        raise ValueError("SPOTIFY_CLIENT_SECRET is not configured in the .env file. Please check your setup.")
    if not redirect_uri:
        raise ValueError("SPOTIFY_REDIRECT_URI is not configured in the .env file.")
        
    # SpotifyOAuth handles token caching, validation, and auto-refresh behind the scenes.
    # It creates a file named '.cache' in the current working directory to store the access and refresh tokens.
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPES,
        open_browser=True  # Automatically opens a browser tab for user authorization on first run
    )
    
    return spotipy.Spotify(auth_manager=auth_manager)

if __name__ == "__main__":
    print("Testing Spotify Authentication module...")
    try:
        sp = get_spotify_client()
        # Call a simple read API to verify the token is valid and connection works
        user_info = sp.current_user()
        print(f"Authentication Successful! Connected as user: {user_info.get('display_name')} ({user_info.get('id')})")
    except Exception as e:
        print(f"Authentication Failed: {e}", file=sys.stderr)
        print("Please check your .env credentials and ensure you've registered the redirect URI in the Spotify Dashboard.", file=sys.stderr)
        sys.exit(1)
