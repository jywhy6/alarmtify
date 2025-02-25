import spotipy
import datetime
import time
import json
import logging
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler
from typing import Dict, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

CONFIG_FILE = 'config.json'
TOKEN_CONFIG_KEYS = ['username', 'client_id', 'client_secret', 'redirect_uri']
SPOTIFY_SCOPE = 'user-read-playback-state user-modify-playback-state'


def load_config(config_file: str = CONFIG_FILE) -> Dict:
    """Load configuration from a JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Configuration file '%s' not found", config_file)
        raise
    except json.JSONDecodeError:
        logger.error("Invalid JSON format in '%s'", config_file)
        raise


def get_token_config(config: Dict) -> Dict:
    """Extract and validate token configuration from the config dictionary."""
    token_config = {k: config.get(k) for k in TOKEN_CONFIG_KEYS}
    missing_keys = [k for k in TOKEN_CONFIG_KEYS if not token_config[k]]
    if missing_keys:
        logger.error("Missing required config keys: %s",
                     ', '.join(missing_keys))
        raise ValueError("Incomplete token configuration")

    token_config['scope'] = SPOTIFY_SCOPE
    return token_config


def get_spotify_auth_manager(token_config: Dict) -> SpotifyOAuth:
    """Create and return a configured SpotifyOAuth instance."""
    cache_handler = CacheFileHandler(username=token_config['username'])
    return SpotifyOAuth(
        client_id=token_config['client_id'],
        client_secret=token_config['client_secret'],
        redirect_uri=token_config['redirect_uri'],
        scope=token_config['scope'],
        cache_handler=cache_handler
    )


def refresh_spotify_token(auth_manager: SpotifyOAuth) -> str:
    """Handle Spotify token retrieval and refresh logic."""
    token_info = auth_manager.get_cached_token()

    if not token_info:
        logger.info("No cached token found, requesting new token")
        access_token = auth_manager.get_access_token(as_dict=False)
        token_info = auth_manager.get_cached_token()
        if not token_info or 'access_token' not in token_info:
            logger.error("Failed to retrieve token info after request")
            raise ValueError("Token retrieval failed")
    elif auth_manager.is_token_expired(token_info):
        logger.info("Token expired, refreshing...")
        token_info = auth_manager.refresh_access_token(
            token_info['refresh_token'])

    return token_info['access_token']


def select_device(sp: spotipy.Spotify, config: Dict) -> Dict:
    """Select a Spotify device based on config or user input."""
    try:
        devices = sp.devices()['devices']
        if not devices:
            logger.error("No Spotify devices available")
            raise ValueError("No devices found")
    except spotipy.SpotifyException as e:
        logger.error("Failed to fetch devices: %s", e)
        raise

    if len(devices) == 1:
        return devices[0]

    device_id = config.get('device_id')
    device_name = config.get('device_name')
    if device_id:
        return next((d for d in devices if d['id'] == device_id), devices[0])
    if device_name:
        return next((d for d in devices if d['name'] == device_name), devices[0])

    logger.info("Multiple devices found. Available options:")
    for i, device in enumerate(devices, 1):
        print(f"{i}. {device['name']} (ID: {device['id']})")

    while True:
        try:
            choice = int(input("Enter the device index: ")) - 1
            if 0 <= choice < len(devices):
                return devices[choice]
            logger.warning("Invalid selection. Try again.")
        except ValueError:
            logger.warning("Please enter a valid number.")


def parse_target_time(time_str: str) -> datetime.time:
    """Parse a time string in HH:MM format into a datetime.time object."""
    try:
        hour, minute = map(int, time_str.split(':'))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("Time out of range")
        return datetime.time(hour, minute)
    except ValueError as e:
        logger.error("Invalid time format '%s': %s. Use HH:MM.", time_str, e)
        raise


def get_target_time(config: Dict) -> datetime.time:
    """Retrieve or prompt for the target playback time."""
    time_str = config.get('alarm_time') or input(
        "Enter playback time (HH:MM, 24-hour): ")
    return parse_target_time(time_str)


def wait_until_target_time(target_time: datetime.time) -> None:
    """Wait until the specified target time."""
    now = datetime.datetime.now()
    target_datetime = datetime.datetime.combine(now.date(), target_time)
    if target_datetime <= now:
        target_datetime += datetime.timedelta(days=1)

    wait_seconds = (target_datetime - now).total_seconds()
    if wait_seconds > 0:
        logger.info("Waiting until %s to start playback", target_datetime)
        time.sleep(wait_seconds)


def start_playback(sp: spotipy.Spotify, device_id: str, max_retries: int = 3) -> None:
    """Start playback on the specified device with retry logic."""
    for attempt in range(max_retries):
        try:
            sp.start_playback(device_id=device_id)
            logger.info("Playback started on device %s", device_id)
            return
        except spotipy.SpotifyException as e:
            logger.error("Playback attempt %d failed: %s", attempt + 1, e)
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise ValueError("Max retries reached, playback failed")


def main():
    """Main execution loop for Spotify playback scheduling."""
    while True:
        try:
            config = load_config()
            token_config = get_token_config(config)
            auth_manager = get_spotify_auth_manager(token_config)
            token = refresh_spotify_token(auth_manager)
            sp = spotipy.Spotify(auth=token)

            target_time = get_target_time(config)
            wait_until_target_time(target_time)

            # Refresh token if expired during wait
            if auth_manager.is_token_expired(auth_manager.get_cached_token()):
                logger.info("Token expired during wait, refreshing...")
                token = refresh_spotify_token(auth_manager)
                sp = spotipy.Spotify(auth=token)

            device = select_device(sp, config)
            start_playback(sp, device['id'])
            # Don't Exit loop on success
        except KeyboardInterrupt:
            logger.info("Program stopped by user")
            break
        except Exception as e:
            # Exit on error
            logger.error("Error occurred: %s. Retrying...", e)
            break


if __name__ == "__main__":
    main()
