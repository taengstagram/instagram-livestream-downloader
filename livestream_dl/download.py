#!/usr/bin/env python

import logging
import sys
import os
import time
import datetime
import argparse
import getpass
import re
import json
import threading
import webbrowser
import codecs
import shutil
import subprocess
from socket import timeout, error as SocketError
from ssl import SSLError
try:
    # py2
    from urllib2 import URLError
    from httplib import HTTPException
    from ConfigParser import SafeConfigParser
except ImportError:
    # py3
    from urllib.error import URLError
    from http.client import HTTPException
    from configparser import SafeConfigParser

from .utils import (
    Formatter, UserConfig, check_for_updates,
    to_json, from_json, generate_safe_path
)

from instagram_private_api import (
    Client, ClientError, ClientCookieExpiredError, ClientLoginRequiredError
)
from instagram_private_api_extensions.live import (
    Downloader, logger as dash_logger
)


__version__ = '0.2.8'

USERNAME_ENV_KEY = 'IG_LOGIN_USERNAME'
PASSWORD_ENV_KEY = 'IG_LOGIN_PASSWORD'


logger = logging.getLogger(__file__)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = Formatter()
ch.setFormatter(formatter)
logger.addHandler(ch)
dash_logger.addHandler(ch)

api_logger = logging.getLogger('instagram_private_api')
api_logger.addHandler(ch)

rule_line = '-' * 80


def onlogin_callback(api, new_settings_file):
    # saved auth cookies on login
    cache_settings = api.settings
    with open(new_settings_file, 'w') as outfile:
        json.dump(cache_settings, outfile, indent=2, default=to_json)
        logger.debug('Saved settings: %s' % new_settings_file)


def generate_srt(comments, download_start_time, srt_file, comments_delay=10.0):
    """
    Generate a valid srt file from the list of comments.

    comments_delay is to compensate for the 10s video buffer available when
    we first begin downloading (segment timeline has 10 segments). This buffer
    is variable because the duration of the segment varies, so 10s is just
    an average.
    """
    subtitles_timeline = {}
    for i, c in enumerate(comments):
        # grouped closely timed comments into 2s blocks so that we can give it enough onscreen time
        created_at_utc = str(2 * (c['created_at_utc'] // 2))
        comment_list = subtitles_timeline.get(created_at_utc) or []
        comment_list.append(c)
        subtitles_timeline[created_at_utc] = comment_list

    if subtitles_timeline:
        timestamps = sorted(subtitles_timeline.keys())
        mememe = False
        subs = []
        for i, tc in enumerate(timestamps):
            t = subtitles_timeline[tc]
            clip_start = int(tc) - download_start_time + int(comments_delay)
            if clip_start < 0:
                clip_start = 0
            clip_end = clip_start + 2

            if i == 0 and clip_start > 0:
                # Generate a caveat message if there is a gap available
                mememe = True
                mememe_start = 0
                mememe_end = min(3, clip_start - 1)
                srt = '%(index)d\n%(start)s --> %(end)s\n%(text)s\n\n' % {
                    'index': 1,
                    'start': time.strftime('%H:%M:%S,001', time.gmtime(mememe_start)),
                    'end': time.strftime('%H:%M:%S,000', time.gmtime(mememe_end)),
                    'text': 'Comment stream timing is slightly modified for easier viewing'
                }
                subs.append(srt)

            srt = '%(index)d\n%(start)s --> %(end)s\n%(text)s\n\n' % {
                'index': i + (1 if not mememe else 2),
                'start': time.strftime('%H:%M:%S,001', time.gmtime(clip_start)),
                'end': time.strftime('%H:%M:%S,000', time.gmtime(clip_end)),
                'text': '\n'.join(['%s: %s' % (c['user']['username'], c['text']) for c in t])
            }
            subs.append(srt)

        with codecs.open(srt_file, 'w', 'utf-8-sig') as srt_outfile:
            srt_outfile.write(''.join(subs))


def check_ffmpeg(binary_path):
    ffmpeg_binary = binary_path or os.getenv('FFMPEG_BINARY', 'ffmpeg')
    cmd = [
        ffmpeg_binary, '-version']
    logger.debug('Executing: "%s"' % ' '.join(cmd))
    exit_code = subprocess.call(cmd)
    logger.debug('Exit code: %s' % exit_code)


def run():

    description = ('INSTAGRAM LIVESTREAM DOWNLOADER (v%s) [python=%s.%s.%s,%s]'
                   % (__version__,
                      sys.version_info.major, sys.version_info.minor, sys.version_info.micro,
                      sys.platform))

    config_section = 'livestream_dl'
    cfgparser = None
    if os.path.exists('livestream_dl.cfg'):
        # read config path
        cfgparser = SafeConfigParser()
        cfgparser.read('livestream_dl.cfg')

    parser = argparse.ArgumentParser(
        description=description,
        epilog='Release: v%s / %s / %s' % (__version__, sys.platform, sys.version))
    parser.add_argument('instagram_user', nargs='?')
    parser.add_argument('-settings', dest='settings', type=str,
                        help='File path to save settings.json')
    parser.add_argument('-username', '-u', dest='username', type=str,
                        help='Login user name. Required if %s env var not set.' % USERNAME_ENV_KEY)
    parser.add_argument('-password', '-p', dest='password', type=str, required=False,
                        help='Login password. Can be set via %s env var.' % PASSWORD_ENV_KEY)
    parser.add_argument('-outputdir', '-o', dest='outputdir',
                        help='Output folder path.')
    parser.add_argument('-commenters', metavar='COMMENTER_ID', dest='commenters', nargs='*',
                        help='List of numeric IG user IDs to collect comments from.')
    parser.add_argument('-collectcomments', action='store_true',
                        help='Collect comments from verified users.')
    parser.add_argument('-nocleanup', action='store_true',
                        help='Do not clean up temporary downloaded/generated files.')
    parser.add_argument('-openwhendone', action='store_true',
                        help='Automatically open movie file when completed.')
    parser.add_argument('-mpdtimeout', dest='mpdtimeout', type=int,
                        help='Set timeout interval for mpd download. Default %d.' % Downloader.MPD_DOWNLOAD_TIMEOUT)
    parser.add_argument('-downloadtimeout', dest='downloadtimeout', type=int,
                        help='Set timeout interval for segments download. Default %d.' % Downloader.DOWNLOAD_TIMEOUT)
    parser.add_argument('-ffmpegbinary', dest='ffmpegbinary', type=str,
                        help='Custom path to ffmpeg binary.')
    parser.add_argument('-skipffmpeg', dest='skipffmpeg', action='store_true',
                        help='Don\'t assemble file with ffmpeg.')
    parser.add_argument('-verbose', dest='verbose', action='store_true',
                        help='Enable verbose debug messages.')
    parser.add_argument('-log', dest='log',
                        help='Log to file specified.')
    parser.add_argument('-ignoreconfig', dest='ignoreconfig', action='store_true',
                        help='Ignore the livestream_dl.cfg file.')
    parser.add_argument('-version', dest='version_check', action='store_true',
                        help='Show current version and check for new updates.')
    argparser = parser.parse_args()

    # if not a version check or downloading for a selected user
    if not (argparser.instagram_user or argparser.version_check):
        parser.parse_args(['-h'])
        exit()

    if argparser.ignoreconfig:
        cfgparser = None
        logger.debug('Ignoring config file.')

    default_config = {
        'outputdir': 'downloaded',
        'commenters': [],
        'collectcomments': False,
        'nocleanup': False,
        'openwhendone': False,
        'mpdtimeout': Downloader.MPD_DOWNLOAD_TIMEOUT,
        'downloadtimeout': Downloader.DOWNLOAD_TIMEOUT,
        'verbose': False,
        'skipffmpeg': False,
        'ffmpegbinary': None,
    }
    userconfig = UserConfig(
        config_section, defaults=default_config,
        argparser=argparser, configparser=cfgparser)

    if userconfig.verbose:
        logger.setLevel(logging.DEBUG)
        api_logger.setLevel(logging.DEBUG)
        dash_logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
        dash_logger.setLevel(logging.INFO)

    if userconfig.log:
        file_handler = logging.FileHandler(userconfig.log)
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(file_handler)
        dash_logger.addHandler(file_handler)
        api_logger.addHandler(file_handler)

    logger.info(description)

    if userconfig.verbose:
        check_ffmpeg(userconfig.ffmpegbinary)

    if argparser.version_check:
        message = check_for_updates(__version__)
        if message:
            logger.warn(message)
        else:
            logger.info('[i] No new version found.')

    logger.info('=-' * 40)

    if not argparser.instagram_user:
        exit()

    user_username = userconfig.username or os.getenv(USERNAME_ENV_KEY)
    if not user_username:
        logger.error('No login username specified.')
        exit(9)

    user_password = (userconfig.password or os.getenv(PASSWORD_ENV_KEY) or
                     getpass.getpass(prompt='Password for %s: ' % user_username))
    settings_file_path = userconfig.settings or ('%s.json' % user_username)
    api = None
    try:
        if not os.path.isfile(settings_file_path):
            # login afresh

            # don't use default device profile
            custom_device = {
                'manufacturer': 'Samsung',
                'model': 'hero2lte',
                'device': 'SM-G935F',
                'android_release': '6.0.1',
                'android_version': 23,
                'dpi': '640dpi',
                'resolution': '1440x2560',
                'chipset': 'samsungexynos8890'
            }
            api = Client(
                user_username, user_password,
                android_release=custom_device['android_release'],
                android_version=custom_device['android_version'],
                phone_manufacturer=custom_device['manufacturer'],
                phone_device=custom_device['device'],
                phone_model=custom_device['model'],
                phone_dpi=custom_device['dpi'],
                phone_resolution=custom_device['resolution'],
                phone_chipset=custom_device['chipset'],
                on_login=lambda x: onlogin_callback(x, settings_file_path))
        else:
            # reuse cached auth
            with open(settings_file_path) as file_data:
                cached_settings = json.load(file_data, object_hook=from_json)

            # always use latest app ver, sig key, etc from lib
            for key in ('app_version', 'signature_key', 'key_version', 'ig_capabilities'):
                cached_settings.pop(key, None)
            api = Client(
                user_username, user_password,
                settings=cached_settings)

    except (ClientCookieExpiredError, ClientLoginRequiredError) as e:
        logger.warn('ClientCookieExpiredError/ClientLoginRequiredError: %s' % e)
        api = Client(
            user_username, user_password,
            on_login=lambda x: onlogin_callback(x, settings_file_path))

    except ClientError as e:
        logger.error('ClientError %s (Code: %d, Response: %s)' % (e.msg, e.code, e.error_response))
        exit(9)

    except Exception as e:
        logger.error('Unexpected Exception: %s' % e)
        exit(99)

    if not api:
        logger.error('Unable to init api client')
        exit(99)

    if user_username != api.authenticated_user_name:
        logger.warn(
            'Authenticated username mismatch: %s vs %s'
            % (user_username, api.authenticated_user_name))

    # Alow user to save an api call if they directly specify the IG numeric user ID
    if re.match('^\d+$', argparser.instagram_user):
        # is a numeric IG user ID
        ig_user_id = argparser.instagram_user
    else:
        # regular ig user name
        res = api.username_info(argparser.instagram_user)
        ig_user_id = res['user']['pk']

    res = api.user_story_feed(ig_user_id)

    if not res.get('broadcast'):
        logger.info('No broadcast from %s' % ig_user_id)
        exit(0)

    broadcast = res['broadcast']

    if broadcast['broadcast_status'] not in ['active']:
        # Usually because it's interrupted
        logger.warn('Broadcast status is currently: %s' % broadcast['broadcast_status'])

    # check if output dir exists, create if otherwise
    if not os.path.exists(userconfig.outputdir):
        os.makedirs(userconfig.outputdir)

    download_start_time = int(time.time())
    filename_prefix = '%s_%s_%s' % (
        datetime.datetime.now().strftime('%Y%m%d'),
        broadcast['broadcast_owner']['username'].replace('.', ''),
        broadcast['id'])

    # dash_abr_playback_url has the higher def stream
    mpd_url = broadcast.get('dash_abr_playback_url') or broadcast['dash_playback_url']
    mpd_output_dir = generate_safe_path('%s_downloads' % filename_prefix, userconfig.outputdir)

    # Print broadcast info to console
    mins, secs = divmod((int(time.time()) - broadcast['published_time']), 60)
    logger.info(rule_line)
    logger.info('Broadcast by: %s \t(%s)' % (broadcast['broadcast_owner']['username'], broadcast['id']))
    logger.info('Viewers: %d \t\tStarted: %s ago' % (
        broadcast['viewer_count'],
        ('%dm' % mins) + ((' %ds' % secs) if secs else '')
    ))
    logger.info('Dash URL: %s' % mpd_url)
    logger.info(rule_line)

    # Record the delay = duration of the stream that has been missed
    broadcast['delay'] = download_start_time - broadcast['published_time']

    # file path to save the stream's info
    meta_json_file = generate_safe_path('%s.json' % filename_prefix, userconfig.outputdir)

    # file path to save collected comments
    comments_json_file = generate_safe_path('%s_comments.json' % filename_prefix, userconfig.outputdir)

    with open(meta_json_file, 'w') as outfile:
        json.dump(broadcast, outfile, indent=2)

    job_aborted = False

    # Callback func used by downloaded to check if broadcast is still alive
    def check_status():
        broadcast_info = api.broadcast_info(broadcast['id'])
        logger.info('Broadcast Status Check: %s' % broadcast_info['broadcast_status'])
        return broadcast_info['broadcast_status'] not in ['active', 'interrupted']

    dl = Downloader(
        mpd=mpd_url,
        output_dir=mpd_output_dir,
        callback_check=check_status,
        user_agent=api.user_agent,
        mpd_download_timeout=userconfig.mpdtimeout,
        download_timeout=userconfig.downloadtimeout,
        duplicate_etag_retry=60,
        ffmpegbinary=userconfig.ffmpegbinary)

    # Call the api to collect comments for the stream
    def get_comments(*commenter_ids):
        comments_collected = []
        logger.info('Collecting comments...')
        info = {
            'id': broadcast['id'],
            'broadcast_owner': broadcast['broadcast_owner'],
            'published_time': broadcast['published_time'],
            'delay': broadcast['delay'],
            'comments': comments_collected
        }
        first_comment_created_at = 0
        try:
            while not job_aborted:
                before_count = len(comments_collected)
                try:
                    comments_res = api.broadcast_comments(
                        broadcast['id'], last_comment_ts=first_comment_created_at)
                    comments = comments_res.get('comments', [])
                    first_comment_created_at = comments[0]['created_at_utc'] if comments else int(time.time() - 5)
                except (SSLError, timeout, URLError, HTTPException, SocketError) as e:
                    # Probably transient network error, ignore and continue
                    logger.warn('Comment collection error: %s' % e)
                    continue
                except ClientError as e:
                    if e.code == 500:
                        logger.warn('Comment collection ClientError: %d %s' % (e.code, e.error_response))
                        continue
                    elif e.code == 400 and not e.msg:   # 400 error fail but no error message
                        logger.warn('Comment collection ClientError: %d %s' % (e.code, e.error_response))
                        continue
                    raise e

                # save comment if it's in list of commenter IDs or if user is verified
                comments_collected.extend(
                    list(filter(
                        lambda x: (str(x['user_id']) in commenter_ids or
                                   x['user']['username'] in commenter_ids or
                                   x['user']['is_verified']),
                        comments)))
                after_count = len(comments_collected)
                if after_count > before_count:
                    # save intermediately to avoid losing comments due to unexpected errors
                    info['comments'] = comments_collected
                    info['initial_buffered_duration'] = dl.initial_buffered_duration
                    with open(comments_json_file, 'w') as outfile:
                        json.dump(info, outfile, indent=2)
                time.sleep(4)

        except ClientError as e:
            if 'media has been deleted' in e.error_response:
                logger.info('Stream end detected.')
            else:
                logger.error('Comment collection ClientError: %d %s' % (e.code, e.error_response))

        logger.info('%d comments collected' % len(comments_collected))
        if not comments_collected:
            return

        # do final save just in case
        info['comments'] = comments_collected
        info['initial_buffered_duration'] = dl.initial_buffered_duration
        with open(comments_json_file, 'w') as outfile:
            json.dump(info, outfile, indent=2)

    # Put comments collection into its own thread to run concurrently
    comment_thread_worker = None
    if userconfig.commenters or userconfig.collectcomments:
        comment_thread_worker = threading.Thread(target=get_comments, args=userconfig.commenters or [])
        comment_thread_worker.start()

    logger.info('Downloading into %s ...' % mpd_output_dir)
    logger.info('[i] To interrupt the download, press CTRL+C')
    try:
        dl.run()
    except KeyboardInterrupt:
        logger.warn('Download interrupted.')
        # Wait for download threads to complete
        if not dl.is_aborted:
            dl.stop()

    finally:
        job_aborted = True

        # Record the initial_buffered_duration
        broadcast['initial_buffered_duration'] = dl.initial_buffered_duration
        with open(meta_json_file, 'w') as outfile:
            json.dump(broadcast, outfile, indent=2)

        missing = broadcast['delay'] - int(dl.initial_buffered_duration)
        logger.info('Recorded stream is missing %d seconds' % missing)

        # Wait for comments thread to complete
        if comment_thread_worker and comment_thread_worker.is_alive():
            logger.info('Stopping comments download...')
            comment_thread_worker.join()

        logger.info('Assembling files....')
        final_output = generate_safe_path('%s.mp4' % filename_prefix, userconfig.outputdir)

        dl.stitch(final_output, skipffmpeg=userconfig.skipffmpeg, cleartempfiles=(not userconfig.nocleanup))

        logger.info(rule_line)
        if not userconfig.skipffmpeg:
            logger.info('Generated file: %s' % final_output)
        else:
            logger.info('Skipped generating file.')
        logger.info(rule_line)

        if not userconfig.skipffmpeg and not userconfig.nocleanup:
            shutil.rmtree(mpd_output_dir, ignore_errors=True)

        try:
            # Generate srt from comments collected
            if os.path.isfile(comments_json_file):
                logger.info('Generating comments file...')
                with open(comments_json_file) as cj:
                    comments_info = json.load(cj)
                comments = comments_info.get('comments', [])
                srt_filename = final_output.replace('.mp4', '.srt')
                generate_srt(
                    comments, download_start_time, srt_filename,
                    comments_delay=dl.initial_buffered_duration)
                logger.info('Comments written to: %s' % srt_filename)
                logger.info(rule_line)

            if userconfig.openwhendone and os.path.exists(final_output):
                webbrowser.open_new_tab('file://' + os.path.abspath(final_output))

        except KeyboardInterrupt:
            logger.warn('Assembling interrupted.')
