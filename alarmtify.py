import spotipy
import datetime
import time
import os
import json
import logging

# 配置日志记录
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_config():
    """加载配置文件并返回配置字典"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Missing config.json")
        raise
    except json.JSONDecodeError:
        logger.error("Invalid config.json format")
        raise


def get_token_config(config):
    """从配置文件中提取 token 配置"""
    TOKEN_CONFIG_KEYS = ['username', 'client_id',
                         'client_secret', 'redirect_uri']
    token_config = {k: config[k] for k in TOKEN_CONFIG_KEYS if k in config}

    missing_keys = [k for k in TOKEN_CONFIG_KEYS if k not in token_config]
    if missing_keys:
        logger.error("Missing config keys: %s", ', '.join(missing_keys))
        raise ValueError("Incomplete token configuration")

    token_config['scope'] = 'user-read-playback-state user-modify-playback-state'
    return token_config


def get_spotify_token(token_config):
    """获取 Spotify API 的 token"""
    token = spotipy.util.prompt_for_user_token(**token_config)
    if not token:
        logger.error("Can't get token for %s", token_config['username'])
        raise ValueError("Token retrieval failed")
    return token


def select_device(sp, config):
    """选择目标设备"""
    devices = sp.devices()['devices']
    if not devices:
        logger.error("No device found")
        raise ValueError("No devices available")

    if len(devices) == 1:
        return devices[0]

    # 优先尝试使用设备 ID 或设备名
    if 'device_id' in config:
        for d in devices:
            if d['id'] == config['device_id']:
                return d
    elif 'device_name' in config:
        for d in devices:
            if d['name'] == config['device_name']:
                return d

    # 如果没有在配置文件中指定设备，让用户选择
    logger.info("Multiple devices found. Please select one:")
    for i, device in enumerate(devices):
        print(f"{i+1}. {device['name']} (ID: {device['id']})")

    while True:
        choice = input("Enter the index of the device you want to use: ")
        try:
            choice_index = int(choice) - 1
            if 0 <= choice_index < len(devices):
                return devices[choice_index]
            logger.warning("Invalid selection. Please try again.")
        except ValueError:
            logger.warning("Please enter a valid index.")


def get_target_time(config):
    """获取目标播放时间"""
    if 'alarm_time' in config:
        time_str = config['alarm_time']
    else:
        time_str = input(
            'Enter the time to start playback in HH:MM format (24-hour): ')

    try:
        hour, minute = map(int, time_str.split(':'))
        return datetime.time(hour, minute)
    except ValueError:
        logger.error("Invalid time format. Please use HH:MM.")
        raise


def wait_until_target_time(target_time):
    """等待直到目标时间"""
    now = datetime.datetime.now()
    target_datetime = datetime.datetime.combine(now.date(), target_time)
    if target_datetime < now:
        target_datetime += datetime.timedelta(days=1)

    time_to_wait = (target_datetime - now).total_seconds()
    logger.info("Waiting until %s to start playback", target_datetime)
    time.sleep(time_to_wait)


def start_playback(sp, device_id):
    """在指定设备上开始播放"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            sp.start_playback(device_id=device_id)
            logger.info("Playback started on the computer's Spotify player")
            return
        except spotipy.SpotifyException as e:
            logger.error("Error starting playback: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5)  # 等待 5 秒后重试
            else:
                logger.error("Max retries reached. Unable to start playback")
                raise


def main():
    """主函数"""
    while True:
        try:
            config = load_config()
            token_config = get_token_config(config)
            token = get_spotify_token(token_config)
            sp = spotipy.Spotify(token)
            target_device = select_device(sp, config)
            target_time = get_target_time(config)
            wait_until_target_time(target_time)
            start_playback(sp, target_device['id'])
        except Exception as e:
            logger.error("Program terminated due to an error: %s", e)
            exit()


if __name__ == "__main__":
    main()
