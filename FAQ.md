# Frequently Asked Questions

## Login Problems

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
