#!/usr/bin/env python

import logging
import sys
import os
import time
import datetime
import argparse
import getpass
import json
import threading
import webbrowser
import shutil
import subprocess
from socket import timeout, error as SocketError
from ssl import SSLError
from string import Formatter as StringFormatter
import glob
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

from instagram_private_api import (
    Client, ClientError, ClientCookieExpiredError, ClientLoginRequiredError
)
from instagram_private_api_extensions.live import (
    Downloader, logger as dash_logger
)
from instagram_private_api_extensions.replay import (
    Downloader as ReplayDownloader, logger as replay_dash_logger
)

from .utils import (
    Formatter, UserConfig, check_for_updates,
    to_json, from_json, generate_safe_path
)
from .comments import CommentsDownloader


__version__ = '0.3.8'

USERNAME_ENV_KEY = 'IG_LOGIN_USERNAME'
PASSWORD_ENV_KEY = 'IG_LOGIN_PASSWORD'


logger = logging.getLogger(__file__)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = Formatter()
ch.setFormatter(formatter)
logger.addHandler(ch)
dash_logger.addHandler(ch)
replay_dash_logger.addHandler(ch)

api_logger = logging.getLogger('instagram_private_api')
api_logger.addHandler(ch)

rule_line = '-' * 80


def onlogin_callback(api, new_settings_file):
    # saved auth cookies on login
    cache_settings = api.settings
    with open(new_settings_file, 'w') as outfile:
        json.dump(cache_settings, outfile, indent=2, default=to_json)
        logger.debug('Saved settings: %s' % new_settings_file)


def check_ffmpeg(binary_path):
    ffmpeg_binary = binary_path or os.getenv('FFMPEG_BINARY', 'ffmpeg')
    cmd = [
        ffmpeg_binary, '-version']
    logger.debug('Executing: "%s"' % ' '.join(cmd))
    exit_code = subprocess.call(cmd)
    logger.debug('Exit code: %s' % exit_code)


def is_replay(broadcast):
    return broadcast['broadcast_status'] == 'post_live' or 'dash_playback_url' not in broadcast


def generate_filename_prefix(broadcast, userconfig):
    if is_replay(broadcast):
        broadcast_start = datetime.datetime.fromtimestamp(broadcast['published_time'])
        broadcast_type = 'replay'
    else:
        broadcast_start = datetime.datetime.now()
        broadcast_type = 'live'
    format_args = {
        'year': broadcast_start.strftime('%Y'),
        'month': broadcast_start.strftime('%m'),
        'day': broadcast_start.strftime('%d'),
        'hour': broadcast_start.strftime('%H'),
        'minute': broadcast_start.strftime('%M'),
        'username': broadcast['broadcast_owner']['username'],
        'broadcastid': broadcast['id'],
        'broadcasttype': broadcast_type,
    }
    user_format_keys = StringFormatter().parse(userconfig.filenameformat)
    invalid_user_format_keys = [
        i[1] for i in user_format_keys if i[1] not in format_args.keys()]
    if invalid_user_format_keys:
        logger.error(
            'Invalid filename format parameters: %s'
            % ', '.join(invalid_user_format_keys))
        exit(10)
    filename_prefix = userconfig.filenameformat.format(**format_args)
    return filename_prefix


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
                        help='Login user name. Required if %s env var not set.'
                             % USERNAME_ENV_KEY)
    parser.add_argument('-password', '-p', dest='password', type=str, required=False,
                        help='Login password. Can be set via %s env var.'
                             % PASSWORD_ENV_KEY)
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
                        help='Set timeout interval in seconds for mpd download. Default %d.'
                             % Downloader.MPD_DOWNLOAD_TIMEOUT)
    parser.add_argument('-downloadtimeout', dest='downloadtimeout', type=int,
                        help='Set timeout interval in seconds for segments download. Default %d.'
                             % Downloader.DOWNLOAD_TIMEOUT)
    parser.add_argument('-ffmpegbinary', dest='ffmpegbinary', type=str,
                        help='Custom path to ffmpeg binary.')
    parser.add_argument('-skipffmpeg', dest='skipffmpeg', action='store_true',
                        help='Don\'t assemble file with ffmpeg.')
    parser.add_argument('-verbose', dest='verbose', action='store_true',
                        help='Enable verbose debug messages.')
    parser.add_argument('-log', dest='log',
                        help='Log to file specified.')
    parser.add_argument('-filenameformat', dest='filenameformat', type=str,
                        help='Custom filename format.')
    parser.add_argument('-noreplay', dest='noreplay', action='store_true',
                        help='Do not download replay streams.')
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
        'filenameformat': '{year}{month}{day}_{username}_{broadcastid}_{broadcasttype}',
    }
    userconfig = UserConfig(
        config_section, defaults=default_config,
        argparser=argparser, configparser=cfgparser)

    if userconfig.verbose:
        logger.setLevel(logging.DEBUG)
        api_logger.setLevel(logging.DEBUG)
        dash_logger.setLevel(logging.DEBUG)
        replay_dash_logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
        dash_logger.setLevel(logging.INFO)
        replay_dash_logger.setLevel(logging.INFO)

    if userconfig.log:
        file_handler = logging.FileHandler(userconfig.log)
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(file_handler)
        dash_logger.addHandler(file_handler)
        replay_dash_logger.addHandler(file_handler)
        api_logger.addHandler(file_handler)

    logger.info(description)

    if userconfig.verbose:
        check_ffmpeg(userconfig.ffmpegbinary)

    if argparser.version_check:
        message = check_for_updates(__version__)
        if message:
            logger.warning(message)
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
                     getpass.getpass(
                         prompt='Type in the password for %s and press "Enter" '
                                '\n(Your password will not show on screen): '
                                % user_username))
    settings_file_path = userconfig.settings or ('%s.json' % user_username)

    # don't use default device profile
    custom_device = {
        'phone_manufacturer': 'samsung',
        'phone_model': 'hero2lte',
        'phone_device': 'SM-G935F',
        'android_release': '6.0.1',
        'android_version': 23,
        'phone_dpi': '640dpi',
        'phone_resolution': '1440x2560',
        'phone_chipset': 'samsungexynos8890'
    }

    api = None
    try:
        if not os.path.isfile(settings_file_path):
            # login afresh
            api = Client(
                user_username, user_password,
                on_login=lambda x: onlogin_callback(x, settings_file_path),
                **custom_device)
        else:
            # reuse cached auth
            with open(settings_file_path) as file_data:
                cached_settings = json.load(file_data, object_hook=from_json)

            # always use latest app ver, sig key, etc from lib
            for key in ('app_version', 'signature_key', 'key_version', 'ig_capabilities'):
                cached_settings.pop(key, None)
            api = Client(
                user_username, user_password,
                settings=cached_settings,
                **custom_device)

    except (ClientCookieExpiredError, ClientLoginRequiredError) as e:
        logger.warning('ClientCookieExpiredError/ClientLoginRequiredError: %s' % e)
        api = Client(
            user_username, user_password,
            on_login=lambda x: onlogin_callback(x, settings_file_path),
            **custom_device)

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
        logger.warning(
            'Authenticated username mismatch: %s vs %s'
            % (user_username, api.authenticated_user_name))

    retry_attempts = 2
    res = {}
    ig_user_id = ''
    for i in range(1, 1 + retry_attempts):
        try:
            # Alow user to save an api call if they directly specify the IG numeric user ID
            if argparser.instagram_user.isdigit():
                # is a numeric IG user ID
                ig_user_id = argparser.instagram_user
            else:
                # regular ig user name
                user_res = api.username_info(argparser.instagram_user)
                ig_user_id = user_res['user']['pk']

            res = api.user_story_feed(ig_user_id)
            break

        except ClientLoginRequiredError as e:
            if i < retry_attempts:
                # Probably because user has changed password somewhere else
                logger.warning('ClientLoginRequiredError. Logging in again...')
                api = Client(
                    user_username, user_password,
                    on_login=lambda x: onlogin_callback(x, settings_file_path),
                    **custom_device)
            else:
                raise e

        except (SSLError, timeout, URLError, HTTPException, SocketError) as e:
            if i < retry_attempts:
                logger.warning(str(e))
                time.sleep(userconfig.downloadtimeout)
            else:
                logger.error(str(e))
                exit(99)

    if not res.get('broadcast') and (
            userconfig.noreplay or
            not res.get('post_live_item', {}).get('broadcasts')):
        logger.info('No broadcast from %s' % ig_user_id)
        exit(0)

    if res.get('broadcast'):
        broadcasts = [res['broadcast']]
    else:
        broadcasts = res['post_live_item']['broadcasts']

    for broadcast in broadcasts:
        if broadcast['broadcast_status'] not in ['active', 'post_live']:
            # Usually because it's interrupted
            logger.warning('Broadcast status is currently: %s' % broadcast['broadcast_status'])

        # check if output dir exists, create if otherwise
        if not os.path.exists(userconfig.outputdir):
            os.makedirs(userconfig.outputdir)

        is_replay_broadcast = is_replay(broadcast)

        download_start_time = int(time.time())
        filename_prefix = generate_filename_prefix(broadcast, userconfig)

        # dash_abr_playback_url has the higher def stream
        mpd_url = (broadcast.get('dash_manifest')
                   or broadcast.get('dash_abr_playback_url')
                   or broadcast['dash_playback_url'])

        # Print broadcast info to console
        logger.info(rule_line)
        started_mins, started_secs = divmod((int(time.time()) - broadcast['published_time']), 60)
        logger.info('Broadcast by: %s \t(%s)\tType: %s' % (
            broadcast['broadcast_owner']['username'],
            broadcast['id'],
            'Live' if not is_replay_broadcast else 'Replay')
        )
        if not is_replay_broadcast:
            started_label = '%dm' % started_mins
            if started_secs:
                started_label += ' %ds' % started_secs
            logger.info(
                'Viewers: %d \t\tStarted: %s ago' % (
                    broadcast.get('viewer_count', 0),
                    started_label)
            )
            logger.info('Dash URL: %s' % mpd_url)
            logger.info(rule_line)

        # Record the delay = duration of the stream that has been missed
        broadcast['delay'] = ((download_start_time - broadcast['published_time'])
                              if not is_replay_broadcast else 0)

        # folder path for downloaded segments
        mpd_output_dir = generate_safe_path(
            '%s_downloads' % filename_prefix, userconfig.outputdir, is_file=False)

        # file path to save the stream's info
        meta_json_file = generate_safe_path('%s.json' % filename_prefix, userconfig.outputdir)

        # file path to save collected comments
        comments_json_file = generate_safe_path('%s_comments.json' % filename_prefix, userconfig.outputdir)

        if is_replay_broadcast:
            # ------------- REPLAY broadcast -------------
            dl = ReplayDownloader(mpd=mpd_url, output_dir=mpd_output_dir, user_agent=api.user_agent)
            duration = dl.duration
            broadcast['duration'] = duration
            if duration:
                duration_mins, duration_secs = divmod(duration, 60)
                if started_mins < 60:
                    started_label = '%dm %ds' % (started_mins, started_secs)
                else:
                    started_label = '%dh %dm' % divmod(started_mins, 60)
                logger.info(
                    'Duration: %dm %ds \t\tStarted: %s ago' % (
                        duration_mins, duration_secs, started_label)
                )
                logger.info(rule_line)

            # Detect if this replay has already been downloaded
            if glob.glob(os.path.join(userconfig.outputdir, '%s.*' % filename_prefix)):
                # Already downloaded, so skip
                logger.warning('This broadcast is already downloaded.')
                # Remove created empty folder
                if os.path.isdir(mpd_output_dir):
                    os.rmdir(mpd_output_dir)
                continue

            # Good to go
            logger.info('Downloading into %s ...' % mpd_output_dir)
            logger.info('[i] To interrupt the download, press CTRL+C')

            final_output = generate_safe_path('%s.mp4' % filename_prefix, userconfig.outputdir)
            try:
                generated_files = dl.download(
                    final_output, skipffmpeg=userconfig.skipffmpeg,
                    cleartempfiles=(not userconfig.nocleanup))

                # Save meta file later after a successful download
                # so that we don't trip up the downloaded check
                with open(meta_json_file, 'w') as outfile:
                    json.dump(broadcast, outfile, indent=2)
                logger.info(rule_line)

                if not userconfig.skipffmpeg:
                    logger.info('Generated file(s): \n%s' % '\n'.join(generated_files))
                else:
                    logger.info('Skipped generating file.')
                logger.info(rule_line)

                if userconfig.commenters or userconfig.collectcomments:
                    logger.info('Collecting comments...')
                    cdl = CommentsDownloader(
                        api=api, broadcast=broadcast, destination_file=comments_json_file,
                        user_config=userconfig, logger=logger)
                    cdl.get_replay()

                    # Generate srt from comments collected
                    if cdl.comments:
                        logger.info('Generating comments file...')
                        srt_filename = final_output.replace('.mp4', '.srt')
                        CommentsDownloader.generate_srt(
                            cdl.comments, broadcast['published_time'], srt_filename,
                            comments_delay=0)
                        logger.info('Comments written to: %s' % srt_filename)
                        logger.info(rule_line)

            except KeyboardInterrupt:
                logger.info('Download interrupted')
            except Exception as e:
                logger.error('Unexpected Error: %s' % str(e))

            continue    # Done with all replay processing

        # ------------- LIVE broadcast -------------
        with open(meta_json_file, 'w') as outfile:
            json.dump(broadcast, outfile, indent=2)

        job_aborted = False

        # Callback func used by downloaded to check if broadcast is still alive
        def check_status():
            heartbeat_info = api.broadcast_heartbeat_and_viewercount(broadcast['id'])
            logger.info('Broadcast Status Check: %s' % heartbeat_info['broadcast_status'])
            return heartbeat_info['broadcast_status'] not in ['active', 'interrupted']

        dl = Downloader(
            mpd=mpd_url,
            output_dir=mpd_output_dir,
            callback_check=check_status,
            user_agent=api.user_agent,
            mpd_download_timeout=userconfig.mpdtimeout,
            download_timeout=userconfig.downloadtimeout,
            duplicate_etag_retry=60,
            ffmpegbinary=userconfig.ffmpegbinary)

        # Generate the final output filename so that we can
        final_output = generate_safe_path('%s.mp4' % filename_prefix, userconfig.outputdir)

        # Call the api to collect comments for the stream
        def get_comments():
            logger.info('Collecting comments...')
            cdl = CommentsDownloader(
                api=api, broadcast=broadcast, destination_file=comments_json_file,
                user_config=userconfig, logger=logger)
            first_comment_created_at = 0
            try:
                while not job_aborted:
                    # Set initial_buffered_duration as soon as it's available
                    if 'initial_buffered_duration' not in broadcast and dl.initial_buffered_duration:
                        broadcast['initial_buffered_duration'] = dl.initial_buffered_duration
                        cdl.broadcast = broadcast
                    first_comment_created_at = cdl.get_live(first_comment_created_at)

            except ClientError as e:
                if 'media has been deleted' in e.error_response:
                    logger.info('Stream end detected.')
                else:
                    logger.error('Comment collection ClientError: %d %s' % (e.code, e.error_response))

            logger.info('%d comments collected' % len(cdl.comments))

            # do final save just in case
            if cdl.comments:
                cdl.save()
                # Generate srt from comments collected
                srt_filename = final_output.replace('.mp4', '.srt')
                CommentsDownloader.generate_srt(
                    cdl.comments, download_start_time, srt_filename,
                    comments_delay=dl.initial_buffered_duration)
                logger.info('Comments written to: %s' % srt_filename)

        # Put comments collection into its own thread to run concurrently
        comment_thread_worker = None
        if userconfig.commenters or userconfig.collectcomments:
            comment_thread_worker = threading.Thread(target=get_comments)
            comment_thread_worker.start()

        logger.info('Downloading into %s ...' % mpd_output_dir)
        logger.info('[i] To interrupt the download, press CTRL+C')
        try:
            dl.run()
        except KeyboardInterrupt:
            logger.warning('Download interrupted.')
            # Wait for download threads to complete
            if not dl.is_aborted:
                dl.stop()

        finally:
            job_aborted = True

            # Record the initial_buffered_duration
            broadcast['initial_buffered_duration'] = dl.initial_buffered_duration
            broadcast['segments'] = dl.segment_meta
            with open(meta_json_file, 'w') as outfile:
                json.dump(broadcast, outfile, indent=2)

            missing = broadcast['delay'] - int(dl.initial_buffered_duration)
            logger.info('Recorded stream is missing %d seconds' % missing)

            # Wait for comments thread to complete
            if comment_thread_worker and comment_thread_worker.is_alive():
                logger.info('Stopping comments download...')
                comment_thread_worker.join()

            logger.info('Assembling files....')

            generated_files = dl.stitch(
                final_output, skipffmpeg=userconfig.skipffmpeg,
                cleartempfiles=(not userconfig.nocleanup))

            logger.info(rule_line)
            if not userconfig.skipffmpeg:
                logger.info('Generated file(s): \n%s' % '\n'.join(generated_files))
            else:
                logger.info('Skipped generating file.')
            logger.info(rule_line)

            if not userconfig.skipffmpeg and not userconfig.nocleanup:
                shutil.rmtree(mpd_output_dir, ignore_errors=True)

            if userconfig.openwhendone and os.path.exists(final_output):
                webbrowser.open_new_tab('file://' + os.path.abspath(final_output))
