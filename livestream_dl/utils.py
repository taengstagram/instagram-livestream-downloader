import logging
import json
import codecs
import sys
import os
import re
import itertools
import warnings

from instagram_private_api.compat import compat_urllib_request


class TerminalColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Formatter(logging.Formatter):

    def __init__(self, fmt=None, datefmt=None):
        super(Formatter, self).__init__(fmt, datefmt)

    @staticmethod
    def supports_color():
        """
        from https://github.com/django/django/blob/master/django/core/management/color.py

        Return True if the running system's terminal supports color,
        and False otherwise.
        """
        plat = sys.platform
        supported_platform = plat != 'Pocket PC' and (plat != 'win32' or 'ANSICON' in os.environ)

        # isatty is not always implemented, #6223.
        is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
        if not supported_platform or not is_a_tty:
            return False
        return True

    def format(self, record):
        if not self.supports_color():
            return str(record.msg)

        color = ''
        if record.levelno == logging.ERROR:
            color = TerminalColors.FAIL
        if record.levelno == logging.INFO:
            color = TerminalColors.OKGREEN
        if record.levelno == logging.WARNING:
            color = TerminalColors.WARNING
        return color + str(record.msg) + TerminalColors.ENDC


class UserConfig(object):

    def __init__(self, section, defaults, argparser=None, configparser=None):
        self.section = section
        self.defaults = defaults
        self.argparse = argparser
        self.configparser = configparser

    def get(self, key, type=None):
        value = None
        if self.argparse:
            value = getattr(self.argparse, key)

        # argparser takes precedence over configparser
        if value:
            return value
        try:
            if not value and self.configparser and self.configparser.has_option(self.section, key):
                if type == int:
                    value = self.configparser.getint(self.section, key)
                elif type == float:
                    value = self.configparser.getfloat(self.section, key)
                elif type == bool:
                    value = self.configparser.getboolean(self.section, key)
                elif type == list:
                    items = self.configparser.get(self.section, key)
                    if items:
                        value = [i.strip() for i in items.split(',')]
                else:
                    value = self.configparser.get(self.section, key)
                if value is None or value == '':
                    warnings.warn(
                        'Empty settings in the config file will cause '
                        'errors in a future version. Please remove "%s=" '
                        'from livestream_dl.cfg as soon as possible.' % key,
                        FutureWarning, stacklevel=9)
        except ValueError:
            pass

        return value or self.defaults.get(key)

    def __str__(self):
        return 'UserConfig(%s)' % ', '.join([
            'settings=%s' % self.settings,
            'username=%s' % self.username,
            'password=%s' % self.password,
            'outputdir=%s' % self.outputdir,
            'commenters=[%s]' % ','.join(self.commenters),
            'collectcomments=%s' % self.collectcomments,
            'nocleanup=%s' % self.nocleanup,
            'openwhendone=%s' % self.openwhendone,
            'mpdtimeout=%s' % self.mpdtimeout,
            'downloadtimeout=%s' % self.downloadtimeout,
            'verbose=%s' % self.verbose,
            'ffmpegbinary=%s' % self.ffmpegbinary,
            'skipffmpeg=%s' % self.skipffmpeg,
            'log=%s' % self.log,
            'filenameformat=%s' % self.filenameformat,
            'noreplay=%s' % self.noreplay,
        ])

    @property
    def settings(self):
        return self.get('settings')

    @property
    def username(self):
        return self.get('username')

    @property
    def password(self):
        return self.get('password')

    @property
    def outputdir(self):
        return self.get('outputdir')

    @property
    def commenters(self):
        return self.get('commenters', type=list)

    @property
    def collectcomments(self):
        return self.get('collectcomments', type=bool)

    @property
    def nocleanup(self):
        return self.get('nocleanup', type=bool)

    @property
    def openwhendone(self):
        return self.get('openwhendone', type=bool)

    @property
    def mpdtimeout(self):
        return self.get('mpdtimeout', type=int)

    @property
    def downloadtimeout(self):
        return self.get('downloadtimeout', type=int)

    @property
    def verbose(self):
        return self.get('verbose', type=bool)

    @property
    def skipffmpeg(self):
        return self.get('skipffmpeg', type=bool)

    @property
    def ffmpegbinary(self):
        return self.get('ffmpegbinary')

    @property
    def log(self):
        return self.get('log')

    @property
    def filenameformat(self):
        return self.get('filenameformat')

    @property
    def noreplay(self):
        return self.get('noreplay', type=bool)


def check_for_updates(current_version):
    try:
        repo = 'taengstagram/instagram-livestream-downloader'
        res = compat_urllib_request.urlopen('https://api.github.com/repos/%s/releases' % repo)
        json_res = res.read().decode('utf-8')
        releases = json.loads(json_res)
        if not releases:
            return ''
        latest_tag = releases[0]['tag_name']
        release_link = releases[0].get('html_url') or ('https://github.com/%s/' % repo)
        if latest_tag != current_version:
            return (
                '[!] A newer version %(tag)s is available.\n'
                'Upgrade with the command:\n'
                '    pip install git+https://git@github.com/%(repo)s.git@%(tag)s'
                ' --process-dependency-links --upgrade'
                '\nCheck %(release_link)s for more information.'
                % {'tag': latest_tag, 'repo': repo, 'release_link': release_link})
    except Exception as e:
        print('[!] Error checking updates: %s' % str(e))

    return ''


def to_json(python_object):
    """For py3 compat"""
    if isinstance(python_object, bytes):
        return {'__class__': 'bytes',
                '__value__': codecs.encode(python_object, 'base64').decode()}
    raise TypeError(repr(python_object) + ' is not JSON serializable')


def from_json(json_object):
    """For py3 compat"""
    if '__class__' in json_object:
        if json_object['__class__'] == 'bytes':
            return codecs.decode(json_object['__value__'].encode(), 'base64')
    return json_object


def generate_safe_path(name, parent_path, is_file=True):
    mobj = re.match(r'(?P<nm>.*)\.(?P<ext>[a-z0-9]+)?$', name)

    if not is_file or not mobj:
        # path has no extension
        name_sans_ext = name
        ext = ''
    else:
        # has extension
        name_sans_ext = mobj.group('nm')
        ext = mobj.group('ext')

    # Generate suitable numeric-based rename if path exists
    # Example: test.txt -> test-1.txt -> test-2.txt, test-3.txt
    # Example: test_folder -> test_folder-1 -> test_folder-2
    for s in itertools.count(0, step=1):
        if not s:
            target_name = name
        else:
            if is_file:
                target_name = '%s-%s%s' % (name_sans_ext, s, ('.%s' % ext) if ext else '')
            else:
                target_name = '%s-%s' % (name_sans_ext, s)
        if not os.path.exists(os.path.join(parent_path, target_name)):
            return os.path.join(parent_path, target_name)
