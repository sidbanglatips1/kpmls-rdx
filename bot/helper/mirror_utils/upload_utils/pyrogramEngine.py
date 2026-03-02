#!/usr/bin/env python3
from traceback import format_exc
from logging import getLogger, ERROR
from aiofiles.os import remove as aioremove, path as aiopath, rename as aiorename, makedirs, rmdir, mkdir
from os import walk, path as ospath
from time import time
from PIL import Image
from pyrogram.types import InputMediaVideo, InputMediaDocument, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, RPCError, PeerIdInvalid, ChannelInvalid
from asyncio import sleep
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type, RetryError
from re import match as re_match, sub as re_sub
from natsort import natsorted
from aioshutil import copy

from bot import config_dict, user_data, GLOBAL_EXTENSION_FILTER, bot, user, IS_PREMIUM_USER
from bot.helper.themes import BotTheme
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import sendCustomMsg, editReplyMarkup, sendMultiMessage, chat_info, deleteMessage, get_tg_link_content
from bot.helper.ext_utils.fs_utils import clean_unwanted, is_archive, get_base_name
from bot.helper.ext_utils.bot_utils import get_readable_file_size, is_telegram_link, is_url, sync_to_async, download_image_url
from bot.helper.ext_utils.leech_utils import get_audio_thumb, get_media_info, get_document_type, get_ss, get_mediainfo_link, format_filename
from bot.helper.ext_utils.ffmpeg import take_ss
from bot.helper.utils.gk_utils import process_caps  # GK AUTO RENAME

LOGGER = getLogger(__name__)
getLogger("pyrogram").setLevel(ERROR)


class TgUploader:

    def __init__(self, name=None, path=None, listener=None):
        self.name = name
        self.__last_uploaded = 0
        self.__processed_bytes = 0
        self.__listener = listener
        self.__path = path
        self.__start_time = time()
        self.__total_files = 0
        self.__is_cancelled = False
        self.__retry_error = False
        self.__thumb = f"Thumbnails/{listener.message.from_user.id}.jpg"
        self.__sent_msg = None
        self.__has_buttons = False
        self.__msgs_dict = {}
        self.__corrupted = 0
        self.__is_corrupted = False
        self.__media_dict = {'videos': {}, 'documents': {}}
        self.__last_msg_in_group = False
        self.__prm_media = False
        self.__client = bot
        self.__up_path = ''
        self.__mediainfo = False
        self.__as_doc = False
        self.__media_group = False
        self.__upload_dest = ''
        self.__bot_pm = False
        self.__user_id = listener.message.from_user.id
        self.__leechmsg = {}
        self.__leech_utils = self.__listener.leech_utils

    async def __prepare_file(self, prefile_, dirpath):
        try:
            # Original rename system
            file_, cap_mono = await format_filename(prefile_, self.__user_id, dirpath)

            # ===== GK AUTO RENAME (SAFE & NO DOUBLE RENAME) =====
            try:
                gk_cap, new_name = await process_caps(self.__listener, file_, self.__up_path)
                if new_name and new_name != file_:
                    file_ = new_name  # Only override name, actual rename handled below
            except Exception as e:
                LOGGER.error(f"GK Rename Error: {e}")

        except Exception as err:
            await self.__listener.onUploadError(f'Error in Format Filename : {err}')
            raise

        # Existing safe rename logic (kept original for seed/copy safety)
        if prefile_ != file_:
            if self.__listener.seed and not self.__listener.newDir and not dirpath.endswith("/splited_files_mltb"):
                dirpath = f'{dirpath}/copied_mltb'
                await makedirs(dirpath, exist_ok=True)
                new_path = ospath.join(dirpath, file_)
                self.__up_path = await copy(self.__up_path, new_path)
            else:
                new_path = ospath.join(dirpath, file_)
                await aiorename(self.__up_path, new_path)
                self.__up_path = new_path

        # Filename length trim (original logic untouched)
        if len(file_) > 60:
            if is_archive(file_):
                name = get_base_name(file_)
                ext = file_.split(name, 1)[1]
            elif match := re_match(r'.+(?=\..+\.0*\d+$)|.+(?=\.part\d+\..+)', file_):
                name = match.group(0)
                ext = file_.split(name, 1)[1]
            elif len(fsplit := ospath.splitext(file_)) > 1:
                name = fsplit[0]
                ext = fsplit[1]
            else:
                name = file_
                ext = ''
            extn = len(ext)
            remain = 60 - extn
            name = name[:remain]

            if self.__listener.seed and not self.__listener.newDir and not dirpath.endswith("/splited_files_mltb"):
                dirpath = f'{dirpath}/copied_mltb'
                await makedirs(dirpath, exist_ok=True)
                new_path = ospath.join(dirpath, f"{name}{ext}")
                self.__up_path = await copy(self.__up_path, new_path)
            else:
                new_path = ospath.join(dirpath, f"{name}{ext}")
                await aiorename(self.__up_path, new_path)
                self.__up_path = new_path

        return cap_mono, file_
