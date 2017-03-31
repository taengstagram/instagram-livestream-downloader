# Advance Usage Options

## Custom settings

You can use a combination of command arguments and/or a configuration file to customise the downloader's behaviour.

Command options take precedence over the config file.

### Command Options
Use ``livestream_dl -h`` to see the full list of available options.

* ``-u``/``-username``
    - The IG username to login with
* ``-p``/``-password``
    - The IG password to login with
* ``-settings``
    - File path to which to auth settings are saved
* ``-o``/``-outputdir``
    - Folder in which to save downloaded files
* ``-commenters``
    - List of commenters to collect comments from
* ``-collectcomments``
    - Collect comments from verified users
* ``-nocleanup``
    - Do not remove the temporary files downloaded
* ``-openwhendone``
    - Open assembled file in the default webbrowser
* ``-mpdtimeout``
    - Set timeout interval for mpd download
* ``-downloadtimeout``
    - Set timeout interval for segments download
* ``-verbose``
    - Enable verbose messages for debugging
* ``-ffmpegbinary``
    - Custom path to the ffmpeg binary
* ``-skipffmpeg``
    - Don't assemble downloaded files into an .mp4 file
* ``-log``
    - Save all messages to the log file path specified
* ``-ignoreconfig``
    - Ignore the config file if present
* ``-version``
    - Show current version and check for updates

Examples:

* ``livestream_dl -u 'myloginusername' -p 'mypassword' 'myfavigacct'``
    - Suppress the manual prompt for password

* ``livestream_dl -u 'myloginusername' -outputdir 'C:\instagram_live_downloads\' 'myfavigacct'``
    - saves downloads to ``C:\instagram_live_downloads\``

* ``livestream_dl -u 'myloginusername' -commenters johndoe janedoe -collectcomments 'myfavigacct'``
    - saves comments from verified users as well as 'johndoe' and 'janedoe'

### Config File
You can specify default custom settings via a configuration file ``livestream_dl.cfg``. A [sample](sample.cfg) configuration file is available for reference.

