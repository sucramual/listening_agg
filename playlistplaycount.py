#!/usr/bin/env python3

import argparse
import json
import re
import sys
import time

import colorama
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from termcolor import colored

colorama.init(autoreset=True)

parser = argparse.ArgumentParser()
parser.add_argument('playlist', help='Spotify ID or URL of the playlist')
parser.add_argument('-c', '--country', default="HK", help='country code to retrieve results from')
parser.add_argument('--slow', action='store_true', help='add delay between printing lines')
parser.add_argument('-l', '--limit', type=int, help='limit the number of songs to fetch')
args = parser.parse_args()

session = requests.Session()
adapter = HTTPAdapter(max_retries=Retry(total=5, backoff_factor=1, status_forcelist=[500]))
session.mount('http://', adapter)
session.mount('https://', adapter)

def log(*func_args, **kwargs):
    print(colored(*func_args, **kwargs), file=sys.stderr)
    if args.slow:
        time.sleep(0.2)

def get_access_token():
    with open('auth/config.json') as fd:
        config = json.load(fd)
        
    r = session.post('https://accounts.spotify.com/api/token',
                     data={'grant_type': 'client_credentials'},
                     auth=(config['client_id'], config['client_secret']))
    r.raise_for_status()
    
    data = r.json()
    data['expires_time'] = time.time() + data['expires_in']
    session.headers['Authorization'] = f'Bearer {data["access_token"]}'
    
    with open('auth/auth.json', 'w') as fd:
        json.dump(data, fd)

def get_playlist_tracks(playlist_id, offset=0, tracks=[]):
    log(f'Getting playlist tracks ({offset}-{offset + 50})...')
    
    r = session.get(f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks',
                    params={
                        'limit': 50,
                        'offset': offset,
                        'fields': 'items(track(id,name,artists,album(id))),next'
                    })
    
    if r.status_code == 401:
        log(colored('Access token expired, refreshing', 'yellow'))
        get_access_token()
        return get_playlist_tracks(playlist_id, offset, tracks)
        
    r.raise_for_status()
    data = r.json()
    
    for item in data['items']:
        if item['track']:  # Some tracks might be None if they're unavailable
            tracks.append(item['track'])
    
    if 'next' in data and data['next']:
        return get_playlist_tracks(playlist_id, offset + 50, tracks)
        
    return tracks

# Initialize auth
try:
    with open('auth/auth.json') as fd:
        auth_data = json.load(fd)
        session.headers['Authorization'] = f'Bearer {auth_data["access_token"]}'
except (FileNotFoundError, json.JSONDecodeError):
    log('Getting access token')
    get_access_token()
else:
    if auth_data['expires_time'] <= time.time():
        log(colored('Access token expired, refreshing', 'yellow'))
        get_access_token()
    else:
        log('Using saved access token')

# Extract playlist ID from URL or ID
playlist_id = args.playlist
m = re.match(r'(?i)(?:https?://open\.spotify\.com/playlist/|spotify:playlist:)?([a-zA-Z0-9]{22})', playlist_id)
if m:
    playlist_id = m.group(1)
else:
    log(f'Invalid Spotify playlist ID or URL: {playlist_id!r}', 'red')
    sys.exit(1)

# Get tracks from playlist
tracks = get_playlist_tracks(playlist_id)

# Apply limit if specified
if args.limit:
    tracks = tracks[:args.limit]
    log(f'Limiting to {args.limit} tracks')

total_playcount = 0
log('')
log(f'Processing {len(tracks)} tracks from playlist', 'cyan')
log('')

# Get playcount for each track
with open('auth/config.json') as fd:
    config = json.load(fd)

for track in tracks:
    album_id = track['album']['id']
    track_id = track['id']
    track_name = track['name']
    artists = ', '.join(artist['name'] for artist in track['artists'])
    
    log(f'Getting playcount for {colored(track_name, "cyan")} by {artists}...', attrs=['bold'])
    
    r = session.get(config['playcount_api_url'], params={'albumid': album_id})
    r.raise_for_status()
    data = r.json()
    
    for param, value in data.items():
        print(f"Param: {param} \n")
        print(f"Value: {value} \n")
    
    # Find the track in the album data
    track_playcount = None
    for disc in data['data']['discs']:
        for album_track in disc['tracks']:
            if album_track['uri'].split(':')[-1] == track_id:
                track_playcount = album_track['playcount']
                break
        if track_playcount is not None:
            break
    
    if track_playcount is not None:
        fmt_playcount = '{:,d}'.format(track_playcount)
        color_playcount = colored(fmt_playcount, 'yellow', attrs=['bold'])
        log(f'Playcount: {color_playcount}')
        total_playcount += track_playcount
    else:
        log('Could not find playcount', 'red')
    
    log('')

fmt_total = '{:,d}'.format(total_playcount)
color_total = colored(fmt_total, 'green', attrs=['bold'])
log(f'Total playlist playcount: {color_total}')