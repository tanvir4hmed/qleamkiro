#!/usr/bin/env python3
"""Download and install ffmpeg static binary."""
import requests
import tarfile
import os
import shutil

# Download ffmpeg static build
url = 'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz'
print('Downloading ffmpeg...')
resp = requests.get(url, stream=True)
with open('/tmp/ffmpeg.tar.xz', 'wb') as f:
    for chunk in resp.iter_content(chunk_size=8192):
        f.write(chunk)
print('Download complete')

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