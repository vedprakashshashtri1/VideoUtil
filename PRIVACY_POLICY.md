# Privacy Policy — VideoUtil Bot

_Last updated: 1 October 2026_

VideoUtil ("the bot") is a private Telegram bot for video work (compress,
cut, merge, leech downloads, and more). This page explains what data the bot
touches and how it is handled. The bot is operated by a single developer who
can be reached at **[@NexonContactBot](https://t.me/NexonContactBot)**.

## What the bot accesses

**From Telegram (while you use the bot):**

- Your Telegram user ID and username — used to recognize you, check access
  (authorized users / premium plans) and deliver your files.
- Messages and files you send to the bot on purpose (a video to compress, a
  link to download, a settings choice). They are processed only to complete
  the task you asked for.

**From Google Drive (only if you tap "Connect Google Drive"):**

- Your Google account **email address** — shown on the settings page so you
  can see which account is connected.
- **Drive file contents and metadata** — only when you give the bot a Drive
  file or folder link to download (leech) or a file to upload. The bot reads,
  copies or writes exactly the files your link points to, at your request.
- An **OAuth refresh token** — stored so the connection survives restarts.
  You can remove it anytime with the bot's disconnect button; it is then
  deleted from both the server file and the database.

The bot does **not** read any other Drive files, does not touch files you did
not link, and never sees your Google password (Google's own sign-in page
handles the login).

## What the bot does NOT do

- Does not sell, rent or share your data with advertisers or third parties.
- Does not use your Google data for anything other than the task you started
  (Google's Limited use rules).
- Does not track you across apps or build profiles.

## Storage and retention

- Telegram IDs, settings and premium status live in the bot's MongoDB
  database for as long as the bot runs.
- Google Drive tokens are kept until you disconnect, then deleted.
- Downloaded/processed files live in the bot's temporary working folder and
  are removed after the upload finishes (or when you clear the queue).

## Security

Data travels over HTTPS/TLS. Database and file access are limited to the
bot's own runtime. No system is perfect, but the bot only keeps what it
needs to work.

## Changes

If this policy changes, the updated version will be published on this same
page.

## Contact

Questions or data removal requests: Telegram **[@NexonContactBot](https://t.me/NexonContactBot)** —
channel **[@NexonBots](https://t.me/NexonBots)**.
