#!/usr/bin/env python

import os
import shutil
import argparse
import re
import logging
import glob
import subprocess
import json

from .utils import Formatter, generate_safe_path
from .comments import CommentsDownloader
from moviepy.video.io.VideoFileClip import VideoFileClip


def _get_file_index(filename):
    """ Extract the numbered index in filename for sorting """
    mobj = re.match(r'.+\-(?P<idx>[0-9]+)\.[a-z]+', filename)
    if mobj:
        return int(mobj.group('idx'))
    return -1


logger = logging.getLogger(__file__)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = Formatter()
ch.setFormatter(formatter)
logger.addHandler(ch)


def main():

    parser = argparse.ArgumentParser(description='Manually assemble video from download folder.')
    parser.add_argument('broadcast_json_file')
    parser.add_argument('-o', dest='output_dir', required=True,
                        help='Folder containing the downloaded segments.')
    parser.add_argument('-f', dest='output_filename', required=True,
                        help='File path for the generated video.')
    parser.add_argument('-c', dest='comments_json_file',
                        help='File path to the comments json file.')
    parser.add_argument('--repair', '-r', dest='repair', action='store_true',
                        help='Try to repair download segments')
    parser.add_argument('-cleanup', action='store_true', help='Clean up output_dir and temp files')
    parser.add_argument('-v', dest='verbose', action='store_true', help='Turn on verbose debug')
    parser.add_argument('-log', dest='log_file_path', help='Log to file specified.')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if args.log_file_path:
        file_handler = logging.FileHandler(args.log_file_path)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if not os.path.exists(args.output_dir):
        raise ValueError('Output dir does not exist: %s' % args.output_dir)
    if not os.path.isfile(args.broadcast_json_file):
        raise ValueError('broadcast json file does not exist: %s' % args.broadcast_json_file)

    with open(args.broadcast_json_file) as info_file:
        broadcast_info = json.load(info_file)

    if broadcast_info.get('broadcast_status', '') == 'post_live':
        logger.error('Cannot assemble a broadcast with status: %s' % broadcast_info['broadcast_status'])
        exit(9)

    stream_id = str(broadcast_info['id'])
    download_start_time = broadcast_info['published_time'] + (
        broadcast_info['delay'] if broadcast_info['delay'] > 0 else 0)

    post_v034 = False
    segment_meta = broadcast_info.get('segments', {})
    if segment_meta:
        post_v034 = True
        all_segments = [
            os.path.join(args.output_dir, k)
            for k in broadcast_info['segments'].keys()]
    else:
        all_segments = list(filter(
            os.path.isfile,
            glob.glob(os.path.join(args.output_dir, '%s-*.m4v' % stream_id))))

    all_segments = sorted(all_segments, key=lambda x: _get_file_index(x))
    prev_res = ''
    sources = []
    audio_stream_format = 'assembled_source_{0}_{1}_mp4.tmp'
    video_stream_format = 'assembled_source_{0}_{1}_m4a.tmp'
    video_stream = ''
    audio_stream = ''

    pre_v034 = os.path.isfile(os.path.join(args.output_dir, '%s-init.m4v' % stream_id))

    for segment in all_segments:

        if not os.path.isfile(segment.replace('.m4v', '.m4a')):
            logger.warning('Audio segment not found: {0!s}'.format(segment.replace('.m4v', '.m4a')))
            continue

        if segment.endswith('-init.m4v') and args.repair:
            logger.info('Replacing %s' % segment)
            segment = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), 'repair', 'init.m4v')

        if segment.endswith('-0.m4v') and args.repair and not pre_v034:
            # From >= v0.3.4 onwards, the init segment is prepended to the m4v
            # so instead of patching the init bytes, we just skip the -0.m4v
            # since it's most likely the faulty one
            logger.info('Dropped %s' % segment)
            continue

        video_stream = os.path.join(
            args.output_dir, video_stream_format.format(stream_id, len(sources)))
        audio_stream = os.path.join(
            args.output_dir, audio_stream_format.format(stream_id, len(sources)))

        try:
            if pre_v034:
                # Don't try to probe with moviepy
                # Just do appending
                file_mode = 'ab'
            else:
                if not post_v034:
                    # no segments meta info
                    vidclip = VideoFileClip(segment)
                    vid_width, vid_height = vidclip.size
                    curr_res = '%sx%s' % (vid_width, vid_height)
                    if prev_res and prev_res != curr_res:
                        sources.append({'video': video_stream, 'audio': audio_stream})
                        video_stream = os.path.join(
                            args.output_dir, video_stream_format.format(stream_id, len(sources)))
                        audio_stream = os.path.join(
                            args.output_dir, audio_stream_format.format(stream_id, len(sources)))

                    # Fresh init segment
                    file_mode = 'wb'
                    prev_res = curr_res
                else:
                    # Use segments meta info
                    if prev_res and prev_res != segment_meta[os.path.basename(segment)]:
                        # resolution changed detected
                        sources.append({'video': video_stream, 'audio': audio_stream})
                        video_stream = os.path.join(
                            args.output_dir, video_stream_format.format(stream_id, len(sources)))
                        audio_stream = os.path.join(
                            args.output_dir, audio_stream_format.format(stream_id, len(sources)))
                        file_mode = 'wb'
                    else:
                        file_mode = 'ab'

                    prev_res = segment_meta[os.path.basename(segment)]

        except IOError:
            # Not a fresh init segment
            file_mode = 'ab'

        with open(video_stream, file_mode) as outfile,\
                open(segment, 'rb') as readfile:
            shutil.copyfileobj(readfile, outfile)
            logger.debug(
                'Assembling video stream {0!s} => {1!s}'.format(
                    os.path.basename(segment), os.path.basename(video_stream)))

        with open(audio_stream, file_mode) as outfile,\
                open(segment.replace('.m4v', '.m4a'), 'rb') as readfile:
            shutil.copyfileobj(readfile, outfile)
            logger.debug(
                'Assembling audio stream {0!s} => {1!s}'.format(
                    os.path.basename(segment), os.path.basename(audio_stream)))

    if audio_stream and video_stream:
        sources.append({'video': video_stream, 'audio': audio_stream})

    for n, source in enumerate(sources):
        dir_name = os.path.dirname(args.output_filename)
        file_name = os.path.basename(args.output_filename)
        output_filename = generate_safe_path(file_name, dir_name, is_file=True)
        ffmpeg_binary = os.getenv('FFMPEG_BINARY', 'ffmpeg')
        cmd = [
            ffmpeg_binary, '-loglevel', 'warning', '-y',
            '-i', source['audio'],
            '-i', source['video'],
            '-c:v', 'copy', '-c:a', 'copy', output_filename]
        logger.info('Executing: "%s"' % ' '.join(cmd))
        exit_code = subprocess.call(cmd)

        assert not exit_code, 'ffmpeg exited with the code: %s' % exit_code
        assert os.path.isfile(output_filename), '%s not generated.' % output_filename

        if args.cleanup and not exit_code:
            logger.debug('Cleaning up files... \n%s\n%s' % (source['audio'], source['video']))
            os.remove(source['audio'])
            os.remove(source['video'])

        logger.info('---------------------------------------------')
        logger.info('Generated file: %s' % output_filename)
        logger.info('---------------------------------------------')

    if args.comments_json_file:
        # convert json to srt
        if not os.path.isfile(args.comments_json_file):
            raise ValueError('Cannot load comments json files: %s' % args.comments_json_file)
        filename_segments = args.output_filename.split('.')
        filename_segments[-1] = 'srt'
        srt_file = '.'.join(filename_segments)

        with open(args.comments_json_file) as cj:
            comments_info = json.load(cj)

        comments = comments_info.get('comments', [])
        CommentsDownloader.generate_srt(
            comments, download_start_time, srt_file,
            comments_delay=comments_info.get('initial_buffered_duration', 10.0))

        assert os.path.isfile(srt_file), '%s not generated.' % srt_file
        logger.info('Comments written to: %s' % srt_file)


if __name__ == '__main__':
    main()
