# Frequently Asked Questions

### "The username you entered doesn't appear to belong to an account."

Try enclosing your login username, and any additional parameters with double quotes ``"``, example:

```bash
livestream_dl -u "my.username" "interesting.streamer"
```

If all else fails, open your favourite text editor (Notepad is fine!) and paste the following in it, replacing the username and password with yours.

```
[livestream_dl]
username=myusername
password=mysuperpassword
```

Save the text file as ``livestream_dl.cfg`` (make sure the file extension is ``.cfg``) in the folder path you're calling ``livestream_dl`` from.

Then try again with:

```bash
livestream_dl "interesting.streamer"
```

***

### Figuring out how much of a live stream is missed

In addition to the ``.mp4`` file downloaded, there is an accompanying ``.json`` file. Open the ``.json`` file in any text editor (example Notepad) and look for 2 values ``initial_buffered_duration`` and ``delay``.

``missing = delay - initial_buffered_duration``

Example:

```json
  "initial_buffered_duration": 10.01,
  "delay": 15,
```

Therefore in this example, the download missed the first ``15 - 10.01 = 5 seconds`` of the live stream.

***

### Running livestream_dl recursively
The recommended way is to use a bash/batch script. For Windows, you may review the conversation in this [issue](https://github.com/taengstagram/instagram-livestream-downloader/issues/5) to get started.

***

### "FileNotFoundError: [WinError 2] The system cannot find the file specified"
If you see this error while assembling files, you probably don't have ffmpeg installed, or if you did, you did not set it properly in ``PATH``.

This may help http://adaptivesamples.com/how-to-install-ffmpeg-on-windows/

To verify if ffmpeg is properly installed, enter this in the Command Line:

```
ffmpeg -version
```
