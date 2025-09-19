#!/usr/bin/env python3
"""
Quick script to remove emoji characters from adsb_receiver.py
"""

import re

# Read the file
with open('adsb_receiver.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove emoji characters
emoji_pattern = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed characters
    "]+", flags=re.UNICODE)

# Replace emojis with empty string
content = emoji_pattern.sub('', content)

# Write back to file
with open('adsb_receiver.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Emoji characters removed from adsb_receiver.py")
