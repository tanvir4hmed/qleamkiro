#!/usr/bin/env python3
"""Download and install ffmpeg static binary."""
import requests
import tarfile
import os
import shutil
import time

# Download ffmpeg static build with retry logic
url = 'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz'
max_retries = 3
timeout = 60  # seconds

print('Downloading ffmpeg...')
for attempt in range(max_retries):
    try:
        print(f'Attempt {attempt + 1}/{max_retries}...')
        resp = requests.get(url, stream=True, timeout=timeout)
        resp.raise_for_status()
        with open('/tmp/ffmpeg.tar.xz', 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print('Download complete')
        break
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        print(f'Attempt {attempt + 1} failed: {e}')
        if attempt < max_retries - 1:
            wait_time = 5 * (attempt + 1)
            print(f'Retrying in {wait_time} seconds...')
            time.sleep(wait_time)
        else:
            print('All download attempts failed. Trying alternative URL...')
            # Try GitHub mirror as fallback
            alt_url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz'
            try:
                resp = requests.get(alt_url, stream=True, timeout=timeout)
                resp.raise_for_status()
                with open('/tmp/ffmpeg.tar.xz', 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                print('Download complete from alternative URL')
            except Exception as alt_e:
                print(f'Alternative URL also failed: {alt_e}')
                raise

# Extract
print('Extracting...')
with tarfile.open('/tmp/ffmpeg.tar.xz', 'r:xz') as tar:
    tar.extractall('/tmp')

# Find and copy binaries
for name in os.listdir('/tmp'):
    if name.startswith('ffmpeg-') and os.path.isdir(os.path.join('/tmp', name)):
        shutil.copy(os.path.join('/tmp', name, 'ffmpeg'), '/usr/local/bin/ffmpeg')
        shutil.copy(os.path.join('/tmp', name, 'ffprobe'), '/usr/local/bin/ffprobe')
        break

os.chmod('/usr/local/bin/ffmpeg', 0o755)
os.chmod('/usr/local/bin/ffprobe', 0o755)
print('ffmpeg installed successfully')