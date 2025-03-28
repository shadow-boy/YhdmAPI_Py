# YHDM API

A Python API wrapper for YHDM (樱花动漫), providing easy access to anime streaming content from the platform.

##  app参考:

`https://github.com/xioneko/neko-anime`

## Features

- Search for anime content on YHDM
- Retrieve detailed information about anime series and episodes
- Extract video URLs for streaming
- Decode protected video links
- Simple and easy-to-use interface

## Requirements

- Python 3.6+
- Dependencies:
  - `requests`: For making HTTP requests
  - `beautifulsoup4` (bs4): For HTML parsing
  - `pycryptodome` (Crypto): For decryption functionality

You can install the required dependencies using pip:

```bash
pip install requests beautifulsoup4 pycryptodome
```

## Usage Examples

### Basic Import

```python
from yhdm_api import YHDMAPI

# Initialize the API
api = YHDMAPI()
```

### Searching for Anime

```python
# Search for anime by name
results = api.search("鬼灭之刃")
for anime in results:
    print(f"Title: {anime.title}")
    print(f"URL: {anime.url}")
```

### Getting Episode Information

```python
# Get episodes from an anime URL
episodes = api.get_episodes("https://www.yhdm.org/show/12345.html")
for episode in episodes:
    print(f"Episode: {episode.title}")
    print(f"URL: {episode.url}")
```

### Retrieving Video URL

```python
# Get playable video URL
video_url = api.get_video_url("https://www.yhdm.org/v/12345-1.html")
print(f"Video URL: {video_url}")
```

## Project Structure

- **yhdm_api.py**: Main API implementation
  - Contains the `YHDMAPI` class and the `Suggest` dataclass
  - Provides methods for searching and retrieving content
  
- **get_video_url_common.py**: Video URL handling
  - Implements functionality for retrieving and decoding video URLs
  - Handles various video sources and their decryption
  
- **config.py**: Configuration settings
  - Contains base URLs, user agents, and other configuration parameters
  - Centralized place for managing API endpoints and settings

## License

[Add license information here]

## Disclaimer

This project is for educational purposes only. Please respect the terms of service of the YHDM platform.

