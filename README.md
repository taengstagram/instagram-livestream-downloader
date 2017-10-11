# Instagram Live Stream Downloader [![Release](https://img.shields.io/badge/latest_release-v0.3.8-ff4980.svg)](https://github.com/taengstagram/instagram-livestream-downloader/releases)


### 2017.08 Notice
I am no longer actively maintaining or supporting this project. Use at your own discretion. I've left the issues open so that you can get help from fellow users, but please maintain basic GitHub courtesy. Close your issues if it is resolved. Don't hijack un-related issues.

---

``livestream_dl`` is a Python console script that downloads an Instagram Live stream. It only downloads a stream that is available for *replay*, or *currently ongoing*, and cannot capture any part of a stream that has already passed.

Python 2.7 and >=3.5 compatible.

> __Warning__: The downloader will download and write to disk many temporary files. If you have a flaky/poor connection, the resulting video file will be choppy due to dropped frames. There is no fix for this.

## Installation

Make sure you have the [prerequisites](PREREQUISITES.md) installed.

In the Command Prompt / Terminal:

```bash
pip install git+https://git@github.com/taengstagram/instagram-livestream-downloader.git@0.3.8 --process-dependency-links
```

## Usage

```bash
livestream_dl -u "<username>" "<instagram-live-username>"
```

Where:

- ``<username>`` is your ig username
- ``<instagram-live-username> `` is the ig user whose stream you want to save
- Example: ``livestream_dl -u "jane" "johndoe"``

Enter the account password when prompted. As the script runs, you should see something similar to:

```
INSTAGRAM LIVESTREAM DOWNLOADER (v0.3.8)
=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
Type in the password for jane and press "Enter"
(Your password will not show on screen):
------------------------------------------------------------------
Broadcast by: johndoe 	(17849164549199999)  Type: Live
Viewers: 418 		Started: 2m 33s ago
Dash URL: https://scontent-xxx3-1.cdninstagram.com/hvideo-frc1/v/dash-hd/17849164549199999.mpd
------------------------------------------------------------------
Downloading into downloaded/20170301_johndoe_17849164549199999_live_downloads/ ...
[i] To interrupt the download, press CTRL+C
Broadcast Status Check: stopped
Assembling files....
------------------------------------------------------------------
Generated file(s):
downloaded/20170301_johndoe_17849164549199999_live.mp4
------------------------------------------------------------------
```

If it is a [replay](http://blog.instagram.com/post/162048719842/160720-replay-live-stories) download, you'll see something like:

```
INSTAGRAM LIVESTREAM DOWNLOADER (v0.3.8)
=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
Type in the password for jane and press "Enter"
(Your password will not show on screen):
------------------------------------------------------------------
Broadcast by: johndoe 	(17849164549199999)  Type: Replay
Duration: 4m 18s 		Started: 5m 30s ago
------------------------------------------------------------------
Downloading into downloaded/20170301_johndoe_17849164549199999_replay_downloads/ ...
[i] To interrupt the download, press CTRL+C
------------------------------------------------------------------
Generated file(s):
downloaded/20170301_johndoe_17849164549199999_replay.mp4
------------------------------------------------------------------
```


You can refer to the [Advance Usage doc](ADVANCE_USAGE.md) for more options.

## Updating

The latest version is __v0.3.8__. To update your copy:

```bash
pip install git+https://git@github.com/taengstagram/instagram-livestream-downloader.git@0.3.8 --process-dependency-links --upgrade
```

You can check if a new version is available with:

```bash
livestream_dl -version
```

Get update notifications using [IFTTT](https://ifttt.com) and the [release RSS feed](https://github.com/taengstagram/instagram-livestream-downloader/releases.atom).

## Problems?

If your problem isn't already covered in the [FAQ](FAQ.md) or not already an existing issue (closed/open), please submit a [new issue](https://github.com/taengstagram/instagram-livestream-downloader/issues/new). Make sure to provide the information required to diagnose the problem.

## Uninstall

Simply run:

```bash
pip uninstall instagram-livestream-downloader
```

## Disclaimer

This is not affliated, endorsed or certified by Instagram. Use at your own risk.
