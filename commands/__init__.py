import json
import os
import requests

from utils import remove_songs
from constants import MAX_RESTRICT_JOBS


def register(app):
    @app.cli.command("run-jobs")
    def run_jobs():
        bin_id = os.environ['BIN_ID']
        r = requests.get(
            'https://json.extendsclass.com/bin/%s' % bin_id,
            )
        if r.status_code > 300:
            return {'error': 'Something went wrong.'}
        r_json = json.loads(r.json())
        jobs = r_json[MAX_RESTRICT_JOBS]
        if r.status_code > 300:
            return {'error': 'Something went wrong.'}
        for job in jobs:
            n, playlist_id, user = job.split()
            user_token = r_json[user]
            remove_songs(n, playlist_id, user, user_token=user_token)