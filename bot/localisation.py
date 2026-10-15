# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from bot.get_cfg import get_config


class Localisation:
    START_TEXT = (
        "<blockquote>Hᴇʟʟᴏ {mention}, \n\n"
        "Tʜɪs ɪs ᴀ <b> Mᴜʟᴛɪғᴜɴᴄᴛɪᴏɴᴀʟ Vɪᴅᴇᴏ Eᴅɪᴛᴏʀ Bᴏᴛ</b>. \n\n"
        "<b>Pʟᴇᴀsᴇ sᴇɴᴅ ᴍᴇ ᴀɴʏ Tᴇʟᴇɢʀᴀᴍ ᴠɪᴅᴇᴏ ғɪʟᴇ I ᴡɪʟʟ ᴍᴀᴋᴇ ɪᴛ ᴀs ʏᴏᴜ ᴡɪsʜ "
        "& I ᴡᴀs ᴅᴇᴠᴇʟᴏᴘᴇᴅ ғᴏʀ @NexonBots !</b> \n\n"
        "/help ғᴏʀ ᴍᴏʀᴇ ᴅᴇᴛᴀɪʟs.</blockquote>"
    )

    FSUB_TEXT = (
        "<blockquote>Hᴇʟʟᴏ {mention}, \n\n"
        "Tʜɪs ɪs ᴀ <b> Mᴜʟᴛɪғᴜɴᴄᴛɪᴏɴᴀʟ Vɪᴅᴇᴏ Eᴅɪᴛᴏʀ Bᴏᴛ</b>. \n\n"
        "<b>Pʟᴇᴀsᴇ ᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟs ᴛᴏ ᴜsᴇ ᴛʜɪs ʙᴏᴛ & I ᴡᴀs ᴅᴇᴠᴇʟᴏᴘᴇᴅ ғᴏʀ @NexonBots !</b> \n\n"
        "/help ғᴏʀ ᴍᴏʀᴇ ᴅᴇᴛᴀɪʟs.</blockquote>"
    )

    FSUB_PIC = "https://i.ibb.co/prsNZS0f/x.jpg"

    ABS_TEXT = " 🇫 🇺 🇨 🇰  🇴 🇫 🇫 ."
    HLP_TEXT = " use /help ."

    FORMAT_SELECTION = (
        "<blockquote>Select the desired format: <a href='{}'>file size might be approximate</a> \n"
        "If you want to set custom thumbnail, send photo before or quickly after tapping on any of the below buttons.\n"
        "You can use /deletethumbnail to delete the auto-generated thumbnail.</blockquote>"
    )

    DOWNLOAD_START = "<blockquote> ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ...</blockquote>\n"
    UPLOAD_START = "<blockquote> ᴜᴘʟᴏᴀᴅɪɴɢ ...</blockquote>\n"
    COMPRESS_START = "<blockquote> ᴛʀʏɪɴɢ ᴛᴏ ᴇɴᴄᴏᴅᴇ ...</blockquote>"

    UPLOAD_SENT_TEXT = (
        "<blockquote>👋 {mention},\n\n"
        "Yᴏᴜʀ ғɪʟᴇ ʜᴀs ʙᴇᴇɴ sᴇɴᴛ ᴛᴏ ʏᴏᴜʀ <b>{dest}</b>. \n\n"
        "Pʟᴇᴀsᴇ ᴄʜᴇᴄᴋ ᴛʜᴇʀᴇ.</blockquote>"
    )

    COMPRESS_SUCCESS = "<blockquote><b>Eɴᴄᴏᴅᴇᴅ Bʏ @NexonBots</b></blockquote>"
    COMPRESS_PROGRESS = "<blockquote>🕛 ETA: {} ♻️ Progress: {}%</blockquote>"

    SAVED_CUSTOM_THUMB_NAIL = "<blockquote>Custom video / file thumbnail saved. This image will be used in the video / file.</blockquote>"
    DEL_ETED_CUSTOM_THUMB_NAIL = "✅ Custom thumbnail cleared successfully."
    FF_MPEG_DEL_ETED_CUSTOM_MEDIA = "✅ Media cleared successfully."
    SAVED_RECVD_DOC_FILE = "✅ Downloaded Successfully."
    CUSTOM_CAPTION_UL_FILE = "HUNTERS"
    NO_CUSTOM_THUMB_NAIL_FOUND = "No Custom ThumbNail found."
    NO_VOID_FORMAT_FOUND = "no-one gonna help you\n{}"
    USER_ADDED_TO_DB = "User <a href='tg://user?id={}'>{}</a> added to {} till {}."
    FF_MPEG_RO_BOT_STOR_AGE_ALREADY_EXISTS = (
        "⚠️ Already one Process going on! ⚠️ \n\nCheck Live Status on Updates Channel."
    )

    # Empty default: /help renders the live command list from bot.command_menu.
    HELP_MESSAGE = get_config("STRINGS_HELP_MESSAGE", "")


    WRONG_MESSAGE = get_config(
        "STRINGS_WRONG_MESSAGE",
        "current CHAT ID: <code>{CHAT_ID}</code>"
    )

    NOT_AUTH = get_config(
        "NOT_AUTH",
        "<blockquote>𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘀𝗲𝗱 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗯𝗼𝘁.</blockquote>"
    )

    META_TXT = """
**ᴍᴀɴᴀɢɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ ғᴏʀ ʏᴏᴜʀ ᴠɪᴅᴇᴏs ᴀɴᴅ ғɪʟᴇs**

**ᴠᴀʀɪᴏᴜꜱ ᴍᴇᴛᴀᴅᴀᴛᴀ:**
<blockquote expandable>
- **ᴛɪᴛʟᴇ**: Descriptive title of the media.
> - **ᴀᴜᴛʜᴏʀ**: The creator or owner of the media.
> - **ᴀʀᴛɪꜱᴛ**: The artist associated with the media.
> - **ᴀᴜᴅɪᴏ**: Title or description of audio content.
> - **ꜱᴜʙᴛɪᴛʟᴇ**: Title of subtitle content.
> - **ᴠɪᴅᴇᴏ**: Title or description of video content.
> - **ᴇɴᴄᴏᴅᴇ ʙʏ**: The person who encoded the video.
> - **ᴄᴜꜱᴛᴏᴍ ᴛᴀɢ**: Any Title.
> - **ᴄᴏᴍᴍᴇɴᴛ**: Any Title.
</blockquote>

**ᴄᴏᴍᴍᴀɴᴅꜱ ᴛᴏ ᴛᴜʀɴ ᴏɴ/ᴏғғ ᴍᴇᴛᴀᴅᴀᴛᴀ:**
➜ /metadata — Turn on or off metadata.

**ᴄᴏᴍᴍᴀɴᴅꜱ ᴛᴏ ꜱᴇᴛ ᴍᴇᴛᴀᴅᴀᴛᴀ:**
<blockquote expandable>
➜ /settitle — Set a custom title of media.
> ➜ /setauthor — Set the author.
> ➜ /setartist — Set the artist.
> ➜ /setaudio — Set audio title.
> ➜ /setsubtitle — Set subtitle title.
> ➜ /setvideo — Set video title.
> ➜ /setencoded_by — Set encoded by title.
> ➜ /setcustom_tag — Set custom tag title.
> ➜ /setcomment — Set comment title.
> ➜ /setallmeta — Set all metadata.
</blockquote>

**ᴇxᴀᴍᴘʟᴇ:** `/settitle Your Title Here`

**ᴜꜱᴇ ᴛʜᴇꜱᴇ ᴄᴏᴍᴍᴀɴᴅꜱ ᴛᴏ ᴇɴʀɪᴄʜ ʏᴏᴜʀ ᴍᴇᴅɪᴀ ᴡɪᴛʜ ᴀᴅᴅɪᴛɪᴏɴᴀʟ ᴍᴇᴛᴀᴅᴀᴛᴀ ɪɴꜰᴏʀᴍᴀᴛɪᴏɴ!**
"""
