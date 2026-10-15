# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import motor, asyncio
import motor.motor_asyncio
import time, logging
import pymongo, os
import logging
from bot.config import Config
from datetime import datetime, timedelta

DB_URI=Config.DB_URL
DB_NAME=Config.DB_NAME

dbclient = None
database = None

logging.basicConfig(level=logging.INFO)



default_verify = {
    'is_verified': False,
    'verified_time': 0,
    'verify_token': "",
    'link': ""
}

def new_user(id):
    return {
        '_id': id,
        'verify_status': default_verify.copy()
    }



class Sujoy:

    def __init__(self, DB_URI, DB_NAME):
        # SECURITY: fail fast instead of silently degrading to a plain dict.
        # The defaultdict fallback made the FIRST query on an unconfigured bot die with
        # "AttributeError: 'dict' object has no attribute 'find_one'" deep inside a handler.
        if not DB_URI:
            raise RuntimeError(
                "FATAL: DB_URL is not set. Provide a MongoDB connection string "
                "before starting the bot - it cannot persist anything without one."
            )
        try:
            self.dbclient = motor.motor_asyncio.AsyncIOMotorClient(DB_URI)
        except Exception as exc:
            raise RuntimeError(f"FATAL: invalid DB_URL: {exc}") from exc
        self.database = self.dbclient[DB_NAME]

        # existing collections
        self.settings = self.database["settings"]
        self.fsub_data = self.database['fsub']   
        self.rqst_fsub_data = self.database['request_forcesub']
        self.rqst_fsub_Channel_data = self.database['request_forcesub_channel']
        self.channel_data = self.database['channels']

        self.thumb_data = self.database['thumb']
        self.user_data = self.database['users']
        self.watermark_data = self.database['watermark']
        self.media_data = self.database['media']
        self.shortener_data1 = self.database['shortener1']
        self.settings_data1 = self.database['settings1']
        self.shortener_data2 = self.database['shortener2']
        self.settings_data2 = self.database['settings2']
        self.fsub_expire_data = self.database['fsub_expire_time']
        self.expire_mode_data = self.database['expire_mode']
        self.fsub_links_data = self.database['fsub_links']
        self.user_spoiler_data = self.database['user_spoilers']
        self.upload_data = self.database['upload']
        self.channel_data = self.database['channels']
        self.metadata = self.database['metadata']
        self.encoding_settings = self.database['encoding_settings']
        self.gdrive_data = self.database['gdrive']
        self.gdrive_tokens_data = self.database['gdrive_tokens']

    async def get_encoding_settings(self):
        """Return the global encoding profile, or an empty dict if unset."""
        return await self.encoding_settings.find_one({'_id': 'global'}) or {}

    async def set_encoding_settings(self, values):
        """Persist validated global encoding settings."""
        await self.encoding_settings.update_one(
            {'_id': 'global'},
            {'$set': values},
            upsert=True
        )

    async def get_last_notified_wzgram_version(self):
        """Return the last WZGram version notified to the admin."""
        record = await self.database["app_updates"].find_one({"_id": "wzgram"})
        return record.get("version") if record else None

    async def set_last_notified_wzgram_version(self, version: str):
        """Persist the last WZGram version notified to the admin."""
        await self.database["app_updates"].update_one(
            {"_id": "wzgram"},
            {"$set": {"version": str(version)}},
            upsert=True
        )

    async def ensure_user_defaults(self, user_id: int):
        """Persist default personal settings without replacing legacy choices."""
        user_id = int(user_id)
        await asyncio.gather(
            self.media_data.update_one(
                {"_id": user_id},
                {"$setOnInsert": {"media_type": "video"}},
                upsert=True,
            ),
            self.user_spoiler_data.update_one(
                {"user_id": user_id},
                {"$setOnInsert": {"spoiler": False}},
                upsert=True,
            ),
            self.upload_data.update_one(
                {"_id": user_id},
                {"$setOnInsert": {"upload_type": "group"}},
                upsert=True,
            ),
            self.metadata.update_one(
                {"_id": user_id},
                {"$setOnInsert": {"metadata": "Off"}},
                upsert=True,
            ),
            self.database["split_mode"].update_one(
                {"_id": user_id},
                {"$setOnInsert": {"split_mode": "normal"}},
                upsert=True,
            ),
        )


    # --------------------------
    # USER METADATA MANAGEMENT
    # --------------------------


    async def set_metadata_source(self, user_id: int, source: str):
        await self.metadata.update_one(
            {"_id": user_id},
            {"$set": {"metadata_source": source}},
            upsert=True
        )

    async def get_metadata_source(self, user_id: int) -> str:
        user_data = await self.metadata.find_one({"_id": user_id})
        return user_data.get("metadata_source", "filename") if user_data else "filename"

    async def get_metadata(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('metadata', "Off") if user else "Off"

    async def set_metadata(self, user_id, metadata):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'metadata': metadata}}, upsert=True)

    async def get_title(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('title', 'Nexon Bots [t.me/NexonBots]') if user else 'Nexon Bots [t.me/NexonBots]'

    async def set_title(self, user_id, title):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'title': title}}, upsert=True)

    async def get_author(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('author', '[Nexon Bots]') if user else '[Nexon Bots]'

    async def set_author(self, user_id, author):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'author': author}}, upsert=True)

    async def get_artist(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('artist', '[Nexon Bots]') if user else '[Nexon Bots]'

    async def set_artist(self, user_id, artist):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'artist': artist}}, upsert=True)

    async def get_audio(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('audio', '[Nexon Bots]') if user else '[Nexon Bots]'

    async def set_audio(self, user_id, audio):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'audio': audio}}, upsert=True)

    async def get_subtitle(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('subtitle', "[Nexon Bots]") if user else "[Nexon Bots]"

    async def set_subtitle(self, user_id, subtitle):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'subtitle': subtitle}}, upsert=True)

    async def get_video(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('video', '[Nexon Bots]') if user else '[Nexon Bots]'

    async def set_video(self, user_id, video):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'video': video}}, upsert=True)

    async def get_encoded_by(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('encoded_by', "Nexon Bots [Sujoy]") if user else "Nexon Bots [Sujoy]"

    async def set_encoded_by(self, user_id, encoded_by):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'encoded_by': encoded_by}}, upsert=True)
        
    async def get_custom_tag(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('custom_tag', "[Nexon Bots]") if user else "[Nexon Bots]"

    async def set_custom_tag(self, user_id, custom_tag):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'custom_tag': custom_tag}}, upsert=True)

    async def get_commentz(self, user_id):
        user = await self.metadata.find_one({'_id': int(user_id)})
        return user.get('commentz', "[Nexon Bots]") if user else "[Nexon Bots]"

    async def set_commentz(self, user_id, commentz):
        await self.metadata.update_one({'_id': int(user_id)}, {'$set': {'commentz': commentz}}, upsert=True)


    # --------------------------
    # USER SPOILER MANAGEMENT
    # --------------------------

    async def set_user_spoiler(self, user_id: int, enabled: bool = True) -> bool:
        """
        Save spoiler preference for a user.
        Always returns True if operation succeeds, False otherwise.
        """
        try:
            await self.user_spoiler_data.update_one(
                {"user_id": user_id},
                {"$set": {"spoiler": bool(enabled)}},
                upsert=True
            )
            return True
        except Exception as e:
            logging.error(f"Error setting user spoiler: {e}")
            return False

    async def get_user_spoiler(self, user_id: int) -> bool:
        """
        Get spoiler preference for a user.
        Always returns True or False.
        """
        try:
            data = await self.user_spoiler_data.find_one({"user_id": user_id})
            if data and "spoiler" in data:
                return bool(data["spoiler"])
            return False
        except Exception as e:
            logging.error(f"Error fetching user spoiler: {e}")
            return False



    # ========== CHANNEL MANAGEMENT ==========
    async def set_user_channel(self, user_id: int, channel_id: int):
        try:
            await self.channel_data.update_one(
                {"_id": user_id},
                {"$set": {"channel_id": channel_id}},
                upsert=True
            )
        except Exception as e:
            logging.error(f"[DB] Failed to set user channel: {e}")

    async def get_user_channel(self, user_id: int):
        try:
            data = await self.channel_data.find_one({"_id": user_id})
            return data.get("channel_id") if data else None
        except Exception as e:
            logging.error(f"[DB] Failed to get user channel: {e}")
            return None

    async def del_user_channel(self, user_id: int):
        try:
            await self.channel_data.update_one(
                {"_id": user_id},
                {"$unset": {"channel_id": ""}}
            )
        except Exception as e:
            logging.error(f"[DB] Failed to delete user channel: {e}")


    # ========== UPLOAD PREFERENCE ==========
    async def set_upload_preference(self, user_id: int, upload_type: str):
        """
        upload_type = "dm" / "channel" / "group"
        """
        try:
            await self.upload_data.update_one(
                {"_id": user_id},
                {"$set": {"upload_type": upload_type}},
                upsert=True
            )
        except Exception as e:
            logging.error(f"[DB] Failed to set upload preference: {e}")

    async def get_upload_preference(self, user_id: int):
        try:
            user = await self.upload_data.find_one({"_id": user_id})
            if user and "upload_type" in user:
                return user["upload_type"]
            return "group"  # default
        except Exception as e:
            logging.error(f"[DB] Failed to get upload preference: {e}")
            return "group"

    async def del_upload_preference(self, user_id: int):
        await self.upload_data.delete_one({"_id": user_id})

    # "telegram" (default) or "gdrive" - Milestone 2 upload location
    async def set_upload_location(self, user_id: int, location: str):
        try:
            await self.upload_data.update_one(
                {"_id": user_id},
                {"$set": {"location": location}},
                upsert=True
            )
        except Exception as e:
            logging.error(f"[DB] Failed to set upload location: {e}")

    async def get_upload_location(self, user_id: int):
        try:
            user = await self.upload_data.find_one({"_id": user_id})
            if user and user.get("location") in ("telegram", "gdrive"):
                return user["location"]
            return "telegram"
        except Exception as e:
            logging.error(f"[DB] Failed to get upload location: {e}")
            return "telegram"


    # ========== GOOGLE DRIVE SETTINGS ==========
    async def get_gdrive_settings(self, user_id: int) -> dict:
        try:
            doc = await self.gdrive_data.find_one({"_id": int(user_id)}) or {}
        except Exception as e:
            logging.error(f"[DB] Failed to get Drive settings: {e}")
            doc = {}
        return {
            "email": str(doc.get("email", "") or ""),
            "own_drive": bool(doc.get("own_drive", False)),
            "auto_folder": bool(doc.get("auto_folder", True)),
            "parent_folder": str(doc.get("parent_folder", "") or ""),
        }

    async def set_gdrive_setting(self, user_id: int, key: str, value):
        try:
            await self.gdrive_data.update_one(
                {"_id": int(user_id)},
                {"$set": {key: value}},
                upsert=True
            )
        except Exception as e:
            logging.error(f"[DB] Failed to set Drive setting {key}: {e}")

    # ========== GOOGLE DRIVE TOKENS (survive reboots/deploys) ==========
    async def get_gdrive_tokens(self, user_id: int):
        try:
            doc = await self.gdrive_tokens_data.find_one({"_id": int(user_id)}) or {}
        except Exception as e:
            logging.error(f"[DB] Failed to get Drive tokens: {e}")
            return None
        tokens = doc.get("tokens")
        return tokens if isinstance(tokens, dict) and tokens.get("access_token") else None

    async def set_gdrive_tokens(self, user_id: int, tokens: dict):
        try:
            await self.gdrive_tokens_data.update_one(
                {"_id": int(user_id)},
                {"$set": {"tokens": tokens}},
                upsert=True
            )
        except Exception as e:
            logging.error(f"[DB] Failed to set Drive tokens: {e}")

    async def delete_gdrive_tokens(self, user_id: int):
        try:
            await self.gdrive_tokens_data.delete_one({"_id": int(user_id)})
        except Exception as e:
            logging.error(f"[DB] Failed to delete Drive tokens: {e}")

    async def gdrive_connected_uids(self) -> list:
        """User ids with a saved Drive connection (for the upload sweeper)."""
        try:
            docs = await self.gdrive_tokens_data.find({}, {"_id": 1}).to_list(length=2000)
            return [int(d["_id"]) for d in docs]
        except Exception as e:
            logging.error(f"[DB] Failed to list gdrive uids: {e}")
            return []


    # --------------------------
    # VERIFICATION MANAGEMENT
    # --------------------------

    async def set_verified_time(self, duration: int):
        """Set global verification duration (e.g., 86400 seconds for 24h)."""
        try:
            await self.settings.update_one(
                {"_id": "verified_duration"},
                {"$set": {"duration": duration}},
                upsert=True
            )
            return True
        except Exception as e:
            logging.error(f"Error setting verified duration: {e}")
            return False

    async def get_verified_time(self):
        """Get global verification duration (seconds)."""
        try:
            settings = await self.settings.find_one({"_id": "verified_duration"})
            return settings.get("duration", 86400) if settings else 86400
        except Exception as e:
            logging.error(f"Error fetching verified duration: {e}")
            return 86400

    async def db_verify_status(self, user_id):
        user = await self.user_data.find_one({'_id': int(user_id)})
        res = default_verify.copy()
        if user and isinstance(user.get('verify_status'), dict):
            res.update(user['verify_status'])
        try:
            res['verified_time'] = float(res.get('verified_time') or 0)
        except (ValueError, TypeError):
            res['verified_time'] = 0.0
        return res

    async def db_update_verify_status(self, user_id, verify):
        status = default_verify.copy()
        if isinstance(verify, dict):
            status.update(verify)
        try:
            status['verified_time'] = float(status.get('verified_time') or 0)
        except (ValueError, TypeError):
            status['verified_time'] = 0.0
        await self.user_data.update_one(
            {'_id': int(user_id)},
            {'$set': {'verify_status': status}},
            upsert=True
        )

    async def get_verify_status(self, user_id):
        verify = await self.db_verify_status(user_id)
        return verify

    async def update_verify_status(self, user_id, verify_token=None, is_verified=None, verified_time=None, link=None):
        update_fields = {}
        if verify_token is not None:
            update_fields['verify_status.verify_token'] = verify_token
        if is_verified is not None:
            update_fields['verify_status.is_verified'] = is_verified
        if verified_time is not None:
            try:
                update_fields['verify_status.verified_time'] = float(verified_time)
            except (ValueError, TypeError):
                update_fields['verify_status.verified_time'] = 0.0
        if link is not None:
            update_fields['verify_status.link'] = link
        if update_fields:
            update_doc = {
                '$set': update_fields,
                '$setOnInsert': {
                    'verify_status.verify_token': '',
                    'verify_status.is_verified': False,
                    'verify_status.verified_time': 0.0,
                    'verify_status.link': ''
                }
            }
            await self.user_data.update_one(
                {'_id': int(user_id)},
                update_doc,
                upsert=True
            )

    # Shortener Token
    async def set_shortener_url1(self, url):
        try:
        # Check if an active shortener exists
            existing = await self.shortener_data1.find_one({"active": True})
            if existing:
            # Update the URL of the existing active shortener
                await self.shortener_data1.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"shortener_url": url, "updated_at": datetime.utcnow()}}
                )
            else:
            # Insert a new active shortener with the given URL
                await self.shortener_data1.insert_one({
                    "shortener_url": url,
                    "api_key": None,
                    "active": True,
                    "created_at": datetime.utcnow()
                })
            return True
        except Exception as e:
            logging.error(f"Error setting shortener URL: {e}")
            return False

    async def set_shortener_api1(self, api):
        try:
        # Check if an active shortener exists
            existing = await self.shortener_data1.find_one({"active": True})
            if existing:
            # Update the API key of the existing active shortener
                await self.shortener_data1.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"api_key": api, "updated_at": datetime.utcnow()}}
                )
            else:
            # Insert a new active shortener with the given API key
                await self.shortener_data1.insert_one({
                    "shortener_url": None,
                    "api_key": api,
                    "active": True,
                    "created_at": datetime.utcnow()
                })
            return True
        except Exception as e:
            logging.error(f"Error setting shortener API key: {e}")
            return False

    async def get_shortener_url1(self):
        try:
        # Retrieve the shortener URL of the active shortener
            shortener = await self.shortener_data1.find_one({"active": True}, {"_id": 0, "shortener_url": 1})
            return shortener.get("shortener_url") if shortener else None
        except Exception as e:
            logging.error(f"Error fetching shortener URL: {e}")
            return None

    async def get_shortener_api1(self):
        try:
        # Retrieve the API key of the active shortener
            shortener = await self.shortener_data1.find_one({"active": True}, {"_id": 0, "api_key": 1})
            return shortener.get("api_key") if shortener else None
        except Exception as e:
            logging.error(f"Error fetching shortener API key: {e}")
            return None


    async def deactivate_shortener1(self):
        try:
            # Deactivate all active shorteners
            await self.shortener_data1.update_many({"active": True}, {"$set": {"active": False}})
            return True
        except Exception as e:
            logging.error(f"Error deactivating shorteners: {e}")
            return False

    
    async def set_tut_video1(self, video_url: str):
        try:
            # Update the tutorial video URL in the database
            result = await self.settings_data1.update_one(
                {"_id": "tutorial_video"},
                {"$set": {"tutorial_video_url": video_url}},
                upsert=True
            )
            return True  # Return True if the update was successful
        except Exception as e:
            logging.error(f"Error updating tutorial video URL: {e}")
            return False

    async def get_tut_video1(self):
        try:
            # Retrieve the tutorial video URL from the database
            settings = await self.settings_data1.find_one({"_id": "tutorial_video"})
            return settings.get("tutorial_video_url") if settings else None
        except Exception as e:
            logging.error(f"Error fetching tutorial video URL: {e}")
            return None

    # Shortener Token
    async def set_shortener_url2(self, url):
        try:
        # Check if an active shortener exists
            existing = await self.shortener_data2.find_one({"active": True})
            if existing:
            # Update the URL of the existing active shortener
                await self.shortener_data2.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"shortener_url": url, "updated_at": datetime.utcnow()}}
                )
            else:
            # Insert a new active shortener with the given URL
                await self.shortener_data2.insert_one({
                    "shortener_url": url,
                    "api_key": None,
                    "active": True,
                    "created_at": datetime.utcnow()
                })
            return True
        except Exception as e:
            logging.error(f"Error setting shortener URL: {e}")
            return False

    async def set_shortener_api2(self, api):
        try:
        # Check if an active shortener exists
            existing = await self.shortener_data2.find_one({"active": True})
            if existing:
            # Update the API key of the existing active shortener
                await self.shortener_data2.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"api_key": api, "updated_at": datetime.utcnow()}}
                )
            else:
            # Insert a new active shortener with the given API key
                await self.shortener_data2.insert_one({
                    "shortener_url": None,
                    "api_key": api,
                    "active": True,
                    "created_at": datetime.utcnow()
                })
            return True
        except Exception as e:
            logging.error(f"Error setting shortener API key: {e}")
            return False

    async def get_shortener_url2(self):
        try:
        # Retrieve the shortener URL of the active shortener
            shortener = await self.shortener_data2.find_one({"active": True}, {"_id": 0, "shortener_url": 1})
            return shortener.get("shortener_url") if shortener else None
        except Exception as e:
            logging.error(f"Error fetching shortener URL: {e}")
            return None

    async def get_shortener_api2(self):
        try:
        # Retrieve the API key of the active shortener
            shortener = await self.shortener_data2.find_one({"active": True}, {"_id": 0, "api_key": 1})
            return shortener.get("api_key") if shortener else None
        except Exception as e:
            logging.error(f"Error fetching shortener API key: {e}")
            return None


    async def deactivate_shortener2(self):
        try:
            # Deactivate all active shorteners
            await self.shortener_data2.update_many({"active": True}, {"$set": {"active": False}})
            return True
        except Exception as e:
            logging.error(f"Error deactivating shorteners: {e}")
            return False

    async def set_tut_video2(self, video_url: str):
        try:
            # Update the tutorial video URL in the database
            result = await self.settings_data2.update_one(
                {"_id": "tutorial_video"},
                {"$set": {"tutorial_video_url": video_url}},
                upsert=True
            )
            return True  # Return True if the update was successful
        except Exception as e:
            logging.error(f"Error updating tutorial video URL: {e}")
            return False

    async def get_tut_video2(self):
        try:
            # Retrieve the tutorial video URL from the database
            settings = await self.settings_data2.find_one({"_id": "tutorial_video"})
            return settings.get("tutorial_video_url") if settings else None
        except Exception as e:
            logging.error(f"Error fetching tutorial video URL: {e}")
            return None
        
    # USER DATA
    async def present_user(self, user_id: int):
        found = await self.user_data.find_one({'_id': user_id})
        return bool(found)

    async def add_user(self, user_id: int):
        try:
            await self.user_data.update_one({'_id': int(user_id)}, {'$setOnInsert': {'_id': int(user_id)}}, upsert=True)
        except Exception:
            pass
        return

    async def full_userbase(self):
        user_ids = []
        async for doc in self.user_data.find({}, {'_id': 1}):
            user_ids.append(doc['_id'])
        return user_ids

    async def del_user(self, user_id: int):
        await self.user_data.delete_one({'_id': user_id})
        return

    # THUMBNAIL DATA
    async def set_thumbnail(self, user_id: int, file_id: str):
        await self.thumb_data.update_one(
            {'_id': user_id},
            {'$set': {'thumb_file_id': file_id}},
            upsert=True
        )

    async def get_thumbnail(self, user_id: int):
        doc = await self.thumb_data.find_one({'_id': user_id})
        return doc.get('thumb_file_id') if doc else None

    async def del_thumbnail(self, user_id: int):
        await self.thumb_data.delete_one({'_id': user_id})


    # In your DB class
    async def set_watermark(self, user_id: int, path: str):
        await self.watermark_data.update_one({"_id": user_id}, {"$set": {"watermark": path}}, upsert=True)

    async def get_watermark(self, user_id: int) -> str:
        data = await self.watermark_data.find_one({"_id": user_id})
        return data.get("watermark") if data else None

    async def del_watermark(self, user_id: int):
        await self.watermark_data.update_one({"_id": user_id}, {"$unset": {"watermark": ""}})
    
    
    async def set_media_preference(self, id, media_type):
        try:
            #print(f"[SET] Setting media_type for user {id} to {media_type}")
            await self.media_data.update_one(
                {"_id": int(id)},
                {"$set": {"media_type": media_type}},
                upsert=True
            )
            #print(f"[SET] Media preference updated for user {id}")
        except Exception as e:
            print(f"[ERROR] Failed to set media preference for user {id}: {e}")

    async def get_media_preference(self, id):
        try:
            #print(f"[GET] Fetching media preference for user {id}")
            user = await self.media_data.find_one({"_id": int(id)})
            if user and "media_type" in user:
                #print(f"[GET] Found media_type: {user['media_type']} for user {id}")
                return user["media_type"]
            # New users receive streaming-video delivery by default.
            return "video"
        except Exception as e:
            print(f"[ERROR] Failed to get media preference for user {id}: {e}")
            return "video"

    async def set_split_mode(self, id, split_mode: str):
        try:
            mode = "binary" if str(split_mode).lower() == "binary" else "normal"
            await self.database["split_mode"].update_one(
                {"_id": int(id)},
                {"$set": {"split_mode": mode}},
                upsert=True
            )
        except Exception as e:
            logging.error(f"[ERROR] Failed to set split mode for user {id}: {e}")

    async def get_split_mode(self, id) -> str:
        try:
            user = await self.database["split_mode"].find_one({"_id": int(id)})
            if user and "split_mode" in user:
                mode = str(user["split_mode"]).lower()
                return "binary" if mode == "binary" else "normal"
            return "normal"
        except Exception as e:
            logging.error(f"[ERROR] Failed to get split mode for user {id}: {e}")
            return "normal"



    # CHANNEL MANAGEMENT
    async def channel_exist(self, channel_id: int):
        found = await self.fsub_data.find_one({'_id': channel_id})
        return bool(found)

    async def add_channel(self, channel_id: int):
        if not await self.channel_exist(channel_id):
            await self.fsub_data.insert_one({'_id': channel_id})
            return

    async def rem_channel(self, channel_id: int):
        if await self.channel_exist(channel_id):
            await self.fsub_data.delete_one({'_id': channel_id})
            return

    del_channel = rem_channel

    async def show_channels(self):
        channel_docs = await self.fsub_data.find().to_list(length=None)
        channel_ids = [doc['_id'] for doc in channel_docs]
        return channel_ids


# Get current mode of a channel
    async def get_channel_mode(self, channel_id: int):
        data = await self.fsub_data.find_one({'_id': channel_id})
        return data.get("mode", "off") if data else "off"

    # Set mode of a channel
    async def set_channel_mode(self, channel_id: int, mode: str):
        await self.fsub_data.update_one(
            {'_id': channel_id},
            {'$set': {'mode': mode}},
            upsert=True
        )

    # REQUEST FORCE-SUB MANAGEMENT

    async def req_user(self, channel_id: int, user_id: int):
        try:
            await self.rqst_fsub_Channel_data.update_one(
                {'_id': int(channel_id)},
                {'$addToSet': {'user_ids': int(user_id)}},
                upsert=True
            )
        except Exception as e:
            print(f"[DB ERROR] Failed to add user to request list: {e}")


    async def del_req_user(self, channel_id: int, user_id: int):

        await self.rqst_fsub_Channel_data.update_one(
            {'_id': channel_id}, 
            {'$pull': {'user_ids': user_id}}
        )


    async def req_user_exist(self, channel_id: int, user_id: int):
        try:
            found = await self.rqst_fsub_Channel_data.find_one({
                '_id': int(channel_id),
                'user_ids': int(user_id)
            })
            return bool(found)
        except Exception as e:
            print(f"[DB ERROR] Failed to check request list: {e}")
            return False  



    async def reqChannel_exist(self, channel_id: int):
        channel_ids = await self.show_channels()
        if channel_id in channel_ids:
            return True
        else:
            return False



db = Sujoy(DB_URI, DB_NAME)

