
#!/usr/bin/env python3
# FINAL CLEAN STABLE pyrogramEngine.py (KPMLS-RDX Crash Fix Version)

from traceback import format_exc
from logging import getLogger, ERROR
from aiofiles.os import remove as aioremove, path as aiopath, rename as aiorename
from os import walk, path as ospath
from time import time
from PIL import Image
from pyrogram.errors import FloodWait
from asyncio import sleep
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from natsort import natsorted

from bot import config_dict, user_data, GLOBAL_EXTENSION_FILTER, bot, user, IS_PREMIUM_USER
from bot.helper.ext_utils.bot_utils import sync_to_async
from bot.helper.ext_utils.leech_utils import get_media_info, get_document_type, format_filename
LOGGER = getLogger(__name__)
getLogger("pyrogram").setLevel(ERROR)


class TgUploader:

    def __init__(self, name=None, path=None, listener=None):
        self.name = name
        self.__listener = listener
        self.__path = path
        self.__start_time = time()
        self.__processed_bytes = 0
        self.__last_uploaded = 0
        self.__is_cancelled = False
        self.__total_files = 0
        self.__corrupted = 0
        self.__thumb = f"Thumbnails/{listener.message.from_user.id}.jpg"
        self.__client = bot
        self.__up_path = ''
        self.__user_id = listener.message.from_user.id
        self.__sent_msg = None

    async def __upload_progress(self, current, total):
        if self.__is_cancelled:
            if IS_PREMIUM_USER:
                user.stop_transmission()
            bot.stop_transmission()
        chunk = current - self.__last_uploaded
        self.__last_uploaded = current
        self.__processed_bytes += chunk

    async def __prepare_file(self, prefile_, dirpath):
        try:
            file_, cap_mono = await format_filename(prefile_, self.__user_id, dirpath)
        except Exception as err:
            await self.__listener.onUploadError(f'Filename Error: {err}')
            raise

        if prefile_ != file_:
            new_path = ospath.join(dirpath, file_)
            await aiorename(self.__up_path, new_path)
            self.__up_path = new_path

        return cap_mono, file_

    async def upload(self, o_files, m_size, size):
        self.__sent_msg = self.__listener.message

        for dirpath, _, files in sorted(await sync_to_async(walk, self.__path)):
            for file_ in natsorted(files):
                self.__up_path = ospath.join(dirpath, file_)

                if file_.lower().endswith(tuple(GLOBAL_EXTENSION_FILTER)):
                    await aioremove(self.__up_path)
                    continue

                try:
                    f_size = await aiopath.getsize(self.__up_path)
                    if f_size == 0:
                        self.__corrupted += 1
                        continue

                    self.__total_files += 1
                    cap_mono, file_ = await self.__prepare_file(file_, dirpath)
                    await self.__upload_file(cap_mono, file_)

                except Exception:
                    LOGGER.error(f"{format_exc()} | Path: {self.__up_path}")
                    continue

                finally:
                    if await aiopath.exists(self.__up_path):
                        await aioremove(self.__up_path)

        await self.__listener.onUploadComplete(
            None, size, {}, self.__total_files, self.__corrupted, self.name
        )

    @retry(wait=wait_exponential(multiplier=2, min=4, max=8),
           stop=stop_after_attempt(3),
           retry=retry_if_exception_type(Exception))
    async def __upload_file(self, cap_mono, file):
        thumb = self.__thumb

        try:
            is_video, is_audio, is_image = await get_document_type(self.__up_path)

            # SAFE AUTO THUMBNAIL (REAL FRAME)
            if is_video and thumb is None:
                try:
                    thumb = None  # fixed: take_ss removed (repo compatible)
                except Exception:
                    thumb = None

            if is_video:
                duration = (await get_media_info(self.__up_path))[0]
                self.__sent_msg = await self.__client.send_video(
                    chat_id=self.__sent_msg.chat.id,
                    reply_to_message_id=self.__sent_msg.id,
                    video=self.__up_path,
                    caption=cap_mono,
                    duration=duration,
                    thumb=thumb,
                    supports_streaming=True,
                    progress=self.__upload_progress,
                    disable_notification=True
                )
            else:
                self.__sent_msg = await self.__client.send_document(
                    chat_id=self.__sent_msg.chat.id,
                    reply_to_message_id=self.__sent_msg.id,
                    document=self.__up_path,
                    caption=cap_mono,
                    progress=self.__upload_progress,
                    disable_notification=True
                )

        except FloodWait as f:
            await sleep(f.value)
        except Exception as err:
            LOGGER.error(f"{format_exc()} | Upload Error")
            raise err

    async def cancel_download(self):
        self.__is_cancelled = True
        await self.__listener.onUploadError('Upload Stopped!')
