import json
import os
from collections import namedtuple

import dateutil.parser
import requests
import spotipy
from flask import session
from constants import MAX_RESTRICT_JOBS


caches_folder = './.spotify_caches/'
if not os.path.exists(caches_folder):
    os.makedirs(caches_folder)


def session_cache_user_path(user):
    return caches_folder + user


def session_cache_uuid_path():
    return caches_folder + session.get('uuid')


def add_remove_job(n, playlist_id, user):
    bin_id = os.environ.get('BIN_ID')
    job_string = f'{n} {playlist_id} {user}'
    r = requests.get(
        'https://json.extendsclass.com/bin/%s' % bin_id,
        )
    if r.status_code > 300:
        return {'error': 'Something went wrong.'}
    jobs = json.loads(r.json()).get(MAX_RESTRICT_JOBS)
    if jobs:
        jobs_copy = jobs.copy()
        for job in jobs_copy:
            if playlist_id in job:
                jobs.remove(job)
        jobs.append(job_string)
    else:
        jobs = [job_string]
    r = requests.get('https://json.extendsclass.com/bin/%s' % bin_id)
    data = json.loads(r.json())
    data[MAX_RESTRICT_JOBS] = jobs
    r = requests.put(
        'https://json.extendsclass.com/bin/%s' % bin_id,
        json=json.dumps(data),
    )
    if r.status_code > 300:
        return {'error': 'something went wrong.'}


def remove_songs(n, playlist_id, user, session_cache_path=None, user_token=None):
    n = int(n)
    bin_id = os.environ['BIN_ID']
    Song = namedtuple('Song', ['id', 'added_at', 'added_by'])

    if session_cache_path is None and user_token is None:
        cache_path = session_cache_user_path(user)

        # get user token from storage
        r = requests.get(
            'https://json.extendsclass.com/bin/%s' % bin_id,
            )
        if r.status_code > 300:
            return {'error': 'Something went wrong.'}

        token = json.loads(r.json())[user]

        # write it to cache_path
        with open(cache_path, 'w') as f:
            f.write(json.dumps(token))
    elif user_token:
        cache_path = session_cache_user_path(user)
        # write it to cache_path
        with open(cache_path, 'w') as f:
            f.write(json.dumps(user_token))
    else:
        cache_path = session_cache_path()

    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=cache_path)
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    sp = spotipy.Spotify(auth_manager=auth_manager)
    songs = []
    # todo: when below is fixed
    #offset = 0
    #response = sp.playlist_items(playlist_id,
    #                             offset=offset,
    #                             limit=50,
    #                             fields='items.added_at,items.track.id,items.added_by',
    #                             additional_types=['track'],
    #                             )
    response = sp.playlist_items(playlist_id,
                                 offset=0,
                                 fields='items.added_at,items.track.id,items.added_by',
                                 additional_types=['track'],
                                 )
    for item in response['items']:
        songs.append(Song(
            id=item['track']['id'],
            added_at=dateutil.parser.parse(item['added_at']),
            added_by=item['added_by']
        ))
    # todo: get below working
    #while not response['items'] == []:
    #    response = sp.playlist_items(playlist_id,
    #                                 offset=offset,
    #                                 limit=50,
    #                                 fields='items.added_at,items.track.id,items.added_by',
    #                                 additional_types=['track'],
    #                                 )
    #    for item in response['items']:
    #        songs.append(Song(
    #            id=item['track']['id'],
    #            added_at=dateutil.parser.parse(item['added_at']),
    #            added_by=item['added_by']
    #        ))
    #    offset += 50

    if len(songs) < n:
        return {'Nothing to remove'}
    songs_sorted = sorted(songs, key=lambda x: x.added_at)
    songs_to_delete = [x.id for x in songs_sorted[:-n]]
    results = sp.playlist_remove_all_occurrences_of_items(
        playlist_id, songs_to_delete)
    return {'deleted': songs_to_delete}