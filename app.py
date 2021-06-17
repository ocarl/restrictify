import os
from flask import Flask, session, request, redirect, render_template
from flask_session import Session
import spotipy
import uuid
from urllib.parse import unquote
from collections import namedtuple
import dateutil.parser
import click
import requests
import json


app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(64)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './.flask_session/'
Session(app)

caches_folder = './.spotify_caches/'
if not os.path.exists(caches_folder):
    os.makedirs(caches_folder)


def session_cache_user_path(user):
    return caches_folder + user


def session_cache_uuid_path():
    return caches_folder + session.get('uuid')


@app.route('/')
def index():
    if not session.get('uuid'):
        # Step 1. Visitor is unknown. Try known and then give random ID
        session['uuid'] = str(uuid.uuid4())

    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_uuid_path())
    auth_manager = spotipy.oauth2.SpotifyOAuth(
        scope='user-read-currently-playing playlist-modify-private playlist-modify-public playlist-read-collaborative',
        cache_handler=cache_handler,
        show_dialog=True
    )

    if request.args.get("code"):
        # Step 3. Being redirected from Spotify auth page
        auth_manager.get_access_token(request.args.get("code"))
        return redirect('/')

    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        # Step 2. Display sign in link when no token
        auth_url = auth_manager.get_authorize_url()
        return f'<h2><a href="{auth_url}">Sign in</a></h2>'

    # Step 4. Signed in, save token and display data

    # upload to json storage with user as key
    bin_id = os.environ.get('BIN_ID')
    r = requests.patch(
        'https://json.extendsclass.com/bin/%s' % bin_id,
        json=json.dumps({current_user()['id']: cache_handler.get_cached_token()}),
        headers={'content-type': 'application/merge-patch+json'}
    )
    if r.status_code > 300:
        return {'error': r.text}

    spotify = spotipy.Spotify(auth_manager=auth_manager)
    return f'<h2>Hi {spotify.me()["display_name"]}, ' \
           f'<small><a href="/sign_out">[sign out]<a/></small></h2>' \
           f'<a href="/playlists">restrict playlists</a> | ' \
           f'<a href="/reset_playlists">reset playlists</a> | ' \
           f'<a href="/currently_playing">currently playing</a> | ' \
           f'<a href="/current_user">me</a>' \



@app.route('/sign_out')
def sign_out():
    try:
        # Remove the CACHE file (.cache-test) so that a new user can authorize.
        os.remove(session_cache_uuid_path())
        session.clear()
    except OSError as e:
        print("Error: %s - %s." % (e.filename, e.strerror))
    return redirect('/')


@app.route('/playlists', methods=['POST'])
def playlists_post():
    session['n'] = int(request.form['n'])
    return redirect('/playlists')


@app.route('/playlists')
def playlists():
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_uuid_path())
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_handler=cache_handler)

    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')

    if not session.get('n'):
        return render_template('input_max.html')

    spotify = spotipy.Spotify(auth_manager=auth_manager)
    user_playlists = []
    r = spotify.current_user_playlists(limit=50)
    user_playlists.extend(r['items'])
    offset = 50
    while r['next']:
        r = spotify.current_user_playlists(offset=offset, limit=50)
        user_playlists.extend(r['items'])
        offset += 50

    playlist_name_id = {unquote(x['name']): x['id'] for x in user_playlists}

    return render_template('list_elements.html', data=playlist_name_id.items(), n=session['n'])


@app.route('/playlist/restrict')
def remove_n_songs():
    playlist_id = request.args['playlist_id']
    n = int(request.args.get('n', 20))
    user = request.args.get('user')
    return remove_songs(n, playlist_id, user, session_cache_path=session_cache_uuid_path)


@app.cli.command("remove-songs")
@click.argument('n')
@click.argument('playlist_id')
@click.argument('user')
def song_remover(n, playlist_id, user):
    return remove_songs(n, playlist_id, user)


def remove_songs(n, playlist_id, user, session_cache_path=None):
    n = int(n)
    Song = namedtuple('Song', ['id', 'added_at', 'added_by'])

    if session_cache_path is None:
        cache_path = session_cache_user_path(user)

        # get user token from storage
        bin_id = os.environ['BIN_ID']
        r = requests.get(
            'https://json.extendsclass.com/bin/%s' % bin_id,
            )
        if r.status_code > 300:
            return {'error': 'Something went wrong.'}

        token = json.loads(r.json())[user]

        # write it to cache_path
        with open(cache_path, 'w') as f:
            f.write(json.dumps(token))
    else:
        cache_path = session_cache_path()

    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=cache_path)
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    songs = []
    sp = spotipy.Spotify(auth_manager=auth_manager)
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
    if len(songs) < n:
        return {'Nothing to remove'}
    songs_sorted = sorted(songs, key=lambda x: x.added_at)
    songs_to_delete = [x.id for x in songs_sorted[:-n]]
    results = sp.playlist_remove_all_occurrences_of_items(
        playlist_id, songs_to_delete)
    return {'deleted': songs_to_delete}


@app.route('/current_user')
def current_user():
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_uuid_path())
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    return spotify.current_user()


if __name__ == '__main__':
    app.run(
        threaded=True,
        port=int(os.environ.get("PORT",
                 os.environ.get("SPOTIPY_REDIRECT_URI", 8080).split(":")[-1])))
