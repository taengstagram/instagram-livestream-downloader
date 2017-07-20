import time
import json
import codecs
from socket import timeout, error as SocketError
from ssl import SSLError
try:
    # py2
    from urllib2 import URLError
    from httplib import HTTPException
except ImportError:
    # py3
    from urllib.error import URLError
    from http.client import HTTPException

from instagram_private_api import ClientError


class CommentsDownloader(object):

    def __init__(self, api, broadcast, destination_file, user_config, logger):
        self.api = api
        self.broadcast = broadcast
        self.destination_file = destination_file
        self.user_config = user_config
        self.logger = logger
        self.comments = []
        self.aborted = False

    def get_live(self, first_comment_created_at=0):
        comments_collected = self.comments
        commenter_ids = self.user_config.commenters or []

        before_count = len(comments_collected)
        try:
            comments_res = self.api.broadcast_comments(
                self.broadcast['id'], last_comment_ts=first_comment_created_at)
            comments = comments_res.get('comments', [])
            first_comment_created_at = (
                comments[0]['created_at_utc'] if comments else int(time.time() - 5))
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
                broadcast = self.broadcast.copy()
                broadcast.pop('segments', None)     # save space
                broadcast['comments'] = comments_collected
                with open(self.destination_file, 'w') as outfile:
                    json.dump(broadcast, outfile, indent=2)
            self.comments = comments_collected

        except (SSLError, timeout, URLError, HTTPException, SocketError) as e:
            # Probably transient network error, ignore and continue
            self.logger.warning('Comment collection error: %s' % e)
        except ClientError as e:
            if e.code == 500:
                self.logger.warning('Comment collection ClientError: %d %s' % (e.code, e.error_response))
            elif e.code == 400 and not e.msg:   # 400 error fail but no error message
                self.logger.warning('Comment collection ClientError: %d %s' % (e.code, e.error_response))
            else:
                raise e
        finally:
            time.sleep(4)
        return first_comment_created_at

    def get_replay(self):
        comments_collected = []
        starting_offset = 0
        encoding_tag = self.broadcast['encoding_tag']
        commenter_ids = self.user_config.commenters or []
        while True:
            comments_res = self.api.replay_broadcast_comments(
                self.broadcast['id'], starting_offset=starting_offset, encoding_tag=encoding_tag)
            starting_offset = comments_res.get('ending_offset', 0)
            comments = comments_res.get('comments', [])
            comments_collected.extend(
                list(filter(
                    lambda x: (str(x['comment']['user']['pk']) in commenter_ids or
                               x['comment']['user']['username'] in commenter_ids or
                               x['comment']['user']['is_verified']),
                    comments)))
            if self.broadcast['duration'] and starting_offset and self.broadcast['duration'] < starting_offset:
                # offset is past video duration
                break
            elif not comments_res.get('comments') or not starting_offset:
                break
            time.sleep(4)

        self.logger.info('%d comments collected' % len(comments_collected))
        if comments_collected:
            self.broadcast['comments'] = comments_collected
            self.broadcast['initial_buffered_duration'] = 0
            with open(self.destination_file, 'w') as outfile:
                json.dump(self.broadcast, outfile, indent=2)
        self.comments = comments_collected

    def save(self):
        broadcast = self.broadcast.copy()
        broadcast.pop('segments', None)     # save space
        broadcast['comments'] = self.comments
        with open(self.destination_file, 'w') as outfile:
            json.dump(broadcast, outfile, indent=2)

    @staticmethod
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
            if 'offset' in c:   # Is a post live comment
                # Patch comment attributes in
                for k in c['comment'].keys():
                    c[k] = c['comment'][k]
                # Should we use offset or use c['comment']['created_at']? Discrepancy in values
                c['created_at_utc'] = download_start_time + c['offset']
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
