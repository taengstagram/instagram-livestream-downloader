#!/usr/bin/env python

"""
A utility script to assemble downloaded segments into a valid video file.

Usage Example:
python assemble.py 'downloaded/johndoe_17849164549199999_1486300000.json' \
-o 'downloaded/downloads_johndoe_17849164549199999_1486300000/' \
-c 'downloaded/johndoe_17849164549199999_1486300000_comments.json' \
-f 'downloaded/johndoe_17849164549199999_1486300000.mp4'

"""

import os
import shutil
import argparse
import re
import logging
import glob
import subprocess
import json
from .utils import Formatter
from .download import generate_srt


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
    parser.add_argument('-cleanup', action='store_true', help='Clean up output_dir and temp files')
    parser.add_argument('-openwhendone', action='store_true', help='Open final generated file')
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

    stream_id = str(broadcast_info['id'])
    download_start_time = broadcast_info['published_time'] + (
        broadcast_info['delay'] if broadcast_info['delay'] > 0 else 0)

    audio_stream = os.path.join(args.output_dir, 'assembled_source_%s_m4a.tmp' % stream_id)
    video_stream = os.path.join(args.output_dir, 'assembled_source_%s_mp4.tmp' % stream_id)

    with open(audio_stream, 'wb') as outfile:
        logger.info('Assembling audio stream... %s' % audio_stream)
        files = list(filter(
            os.path.isfile,
            glob.glob(os.path.join(args.output_dir, '%s-*.m4a' % stream_id))))
        files = sorted(files, key=lambda x: _get_file_index(x))
        for f in files:
            with open(f, 'rb') as readfile:
                try:
                    shutil.copyfileobj(readfile, outfile)
                except IOError as e:
                    logger.error('Error processing %s' % f)
                    logger.error(e)
                    raise e

    with open(video_stream, 'wb') as outfile:
        logger.info('Assembling video stream... %s' % video_stream)
        files = list(filter(
            os.path.isfile,
            glob.glob(os.path.join(args.output_dir, '%s-*.m4v' % stream_id))))
        files = sorted(files, key=lambda x: _get_file_index(x))
        for f in files:
            with open(f, 'rb') as readfile:
                try:
                    shutil.copyfileobj(readfile, outfile)
                except IOError as e:
                    logger.error('Error processing %s' % f)
                    logger.error(e)
                    raise e

    assert os.path.isfile(audio_stream)
    assert os.path.isfile(video_stream)

    ffmpeg_binary = os.getenv('FFMPEG_BINARY', 'ffmpeg')
    cmd = [
        ffmpeg_binary, '-loglevel', 'panic',
        '-i', audio_stream,
        '-i', video_stream,
        '-c:v', 'copy', '-c:a', 'copy', args.output_filename]
    logger.info('Executing: "%s"' % ' '.join(cmd))
    exit_code = subprocess.call(cmd)

    assert not exit_code, 'ffmpeg exited with the code: %s' % exit_code
    assert os.path.isfile(args.output_filename), '%s not generated.' % args.output_filename

    logger.info('---------------------------------------------')
    logger.info('Generated file: %s' % args.output_filename)
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
        generate_srt(
            comments, download_start_time, srt_file,
            comments_delay=comments_info.get('initial_buffered_duration', 10.0))

        assert os.path.isfile(srt_file), '%s not generated.' % srt_file
        logger.info('Comments written to: %s' % srt_file)

    if args.cleanup and not exit_code:
        logger.debug('Cleaning up files...')
        for f in glob.glob(os.path.join(args.output_dir, '%s-*.*' % stream_id)):
            os.remove(f)
        os.remove(audio_stream)
        os.remove(video_stream)


if __name__ == '__main__':
    main()
