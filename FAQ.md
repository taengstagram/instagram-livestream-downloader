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
### Figuring out how much of a live stream is missed

In addition to the ``.mp4`` file downloaded, there is an accompanying ``.json`` file. Open the ``.json`` file in any text editor (example Notepad) and look for 2 values ``initial_buffered_duration`` and ``delay``.

``missing = delay - initial_buffered_duration``

Example:

```json
  "initial_buffered_duration": 10.01,
  "delay": 15,
```

Therefore in this example, the download missed the first ``15 - 10.01 = 5 seconds`` of the live stream.
