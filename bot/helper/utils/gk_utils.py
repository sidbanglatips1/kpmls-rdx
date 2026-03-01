import re
from os import path as ospath
from typing import Tuple, List, Iterator
from asyncio import sleep

from pyrogram.errors import UserNotParticipant, UserAlreadyParticipant, InviteHashInvalid, InviteHashExpired, FloodWait, MessageEmpty

from bot import logger, FloodWait, bot_dict, bot_lock, user_dict, manage_dict, smart_lock
from bot.core.tg_client import TgClient
from bot.core.config_manager import Config 
from bot.helper.telegram_helper.message_utils import send_message, send_alert
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.files_utils import clean_target
from bot.helper.regex import fetch_extra_info, sanitize_filename, extract_filename
from bot.helper.utils import readable_time, readable_size, safe_format, request
from bot.helper.ext_utils.media_utils import get_media_info, get_video_bit_codec
from bot.helper.ext_utils.files_utils import get_path_size


async def process_caps(listener, filename, path=None):
    custom_caption, prefix, suffix, remove_words = listener.user_data.get('AUTO_RENAME'), listener.user_data.get('PREFIX', ''), listener.user_data.get('SUFFIX', ''), listener.user_data.get('REMOVE')
    new_name = filename
    #listener.name or listener.file_details.get('caption') or
    cap_remove = []
    if remove_words:
        try:
            for x in sorted(remove_words.split('|'), key=len, reverse=True):
                if x.startswith('R:'):
                    new_name = re.sub(x.replace('R:', ''), '', new_name)
                elif x.startswith('CAP:'):
                    cap_remove.append(x.replace('CAP:', ''))
                else:
                    new_name = new_name.replace(x, '')
        except Exception as e:
            await send_message(listener.user.id, f'REMOVE ERROR: {str(e)}')
            
    if False: #replace:
        for rule in parse_rules(replace):
            try:
                old_text = process_text(rule["old"])
                new_text = process_text(rule["new"])
                pattern = re.compile(old_text, rule["flags"])
                new_name = pattern.re.sub(new_text, new_name, count=rule["times"] if rule["times"] >= 0 else 0)
            except re.error:
                f"Error: Invalid regex '{rule['old']}'"
            except Exception:
                logger.error("replac", exc_info=True)
    
    
    if prefix:
        prefix = prefix.replace('\s', ' ')
        if not new_name.startswith(prefix):
            new_name = f"{prefix}{new_name}"
        
    if suffix:
        suffix = suffix.replace('\s', ' ')
        name, ext = ospath.splitext(new_name)
        if suffix not in new_name:
            new_name = f"{name}{suffix}{ext}"
        
    if custom_caption:
        Info = fetch_extra_info(new_name)
        if Info.AutoRename:
            Episode = f"{Info.Start_Episode}-{Info.End_Episode[1:]}" if Info.End_Episode else Info.Start_Episode
            Duration, _Resolution, _Languages, _Subtitles = await get_media_info(path, extra_info=True)
            bitrate, codec = await get_video_bit_codec(path)
            Resolution = (Info.Resolution or _Resolution) + " " + bitrate
            Languages = [L.strip() for L in _Languages.split(',') if L.strip()] or Info.Languages
            Subtitles = [S.strip() for S in _Subtitles.split(',') if S.strip()]
            total_lang, total_sub = len(Languages), len(Subtitles)
            ShortLang = 'Single' if total_lang == 1 else ('Dual' if total_lang == 2 else f'Multi{total_lang}')
            ShortSub = '' if total_sub == 0 else (f"{Subtitles[0][0:1].upper()}Sub" if total_sub == 1 else 'MSub')
            Raw_Name, Extension = ospath.splitext(path)
            GK_FORMAT = f"{prefix}{Info.Name} {Info.Season}{Episode} {Info.Year} {Resolution} {Info.Ott} {Info.Quality} {' '.join(Languages)} {Info.Audio} {codec} {ShortSub}{suffix}{Extension}"
            GK_FORMAT = re.sub('[^\S\n]+', ' ', GK_FORMAT.strip())
            #logger.info(f"Languages: {Languages}")
            #logger.info(f"Subtitles: {Subtitles}")
            try:
                custom_caption = custom_caption.replace(' ', 'π')
                new_name = safe_format(
                    custom_caption,
                    gk=GK_FORMAT,
                    file_name=new_name,
                    file_size=readable_size(await get_path_size(path)),
                    file_caption=new_name,
                    languages=' '.join(Languages),
                    subtitles=' '.join(Subtitles),
                    duration=readable_time(Duration),
                    ott=Info.Ott,
                    quality=Info.Quality,
                    name=Info.Name,
                    year=Info.Year,
                    resolution=Resolution,
                    season=Info.Season,
                    episode=Episode,
                    audio=Info.Audio,
                    lib=codec,
                    extension=Extension,
                    shortsub=ShortSub,
                    shortlang=ShortLang,
                    raw_name=Raw_Name,
                    link=listener.source_url or '',
                )
                if Info.Part:
                    name, ext = ospath.splitext(new_name)
                    new_name = f"{name} {Info.Part}{ext}"
        
            except Exception as e:
                logger.error('ha', exc_info=True)
        else:
            new_name = custom_caption
    else:
        new_name = f"<b>{new_name}</b>"
        
    new_caption = new_name = re.sub('[^\S\n]+', ' ', new_name.strip()).replace('π', ' ')
    if cap_remove:
        for x in sorted(cap_remove, key=len, reverse=True):
            if x.startswith('R:'):
                new_caption = re.sub(x.replace('R:', ''), '', new_caption)
            else:
                new_caption = new_caption.replace(x, '')
    new_name = sanitize_filename(new_name)
    return new_caption, new_name
    
VALID_PREFIXES = {"all", "v", "a", "s"}

def _iter_meta_lines(raw_meta: str) -> Iterator[Tuple[int, str | None, str | None, str]]:
    if not isinstance(raw_meta, str):
        raise ValueError("Metadata must be a string.")

    raw_meta = raw_meta.lstrip("\ufeff\r\n").strip()
    if not raw_meta:
        return

    for line_no, raw_line in enumerate(raw_meta.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue

        if '=' not in line:
            yield line_no, None, None, f"Line {line_no}: missing '=' separator."
            continue

        left, val = line.split('=', 1)
        left, val = left.strip(), val.strip()

        if not val:
            yield line_no, None, None, f"Line {line_no}: empty value for '{left}'."
            continue

        prefix = None
        key = left

        if ':' in left:
            pre, key = left.split(':', 1)
            pre, key = pre.strip(), key.strip()
            if not pre or not key:
                yield line_no, None, None, f"Line {line_no}: invalid key or prefix."
                continue
            if pre not in VALID_PREFIXES:
                yield line_no, None, None, f"Line {line_no}: invalid prefix '{pre}'. Allowed: all, v, a, s."
                continue
            prefix = pre

        if any(ord(ch) < 32 for ch in key):
            yield line_no, None, None, f"Line {line_no}: metadata key contains control characters."
            continue

        yield line_no, prefix, key, val

async def validate_metadata_input(raw_meta: str) -> Tuple[bool, str]:
    errors = []
    seen = set()

    try:
        for line_no, prefix, key, val in _iter_meta_lines(raw_meta):
            if key is None:
                errors.append(val)
                continue

            key_id = f"{prefix or 'general'}:{key}"
            if key_id in seen:
                errors.append(
                    f"Line {line_no}: duplicate metadata key '{key}' for prefix '{prefix or 'general'}'."
                )
            else:
                seen.add(key_id)

        if not seen and not errors:
            errors.append("No valid metadata lines found.")

    except ValueError as e:
        errors.append(str(e))

    if errors:
        return False, "\n".join(errors)
    return True, ""

def metadata_parser(raw_meta: str) -> List[str]:
    try:
        if not isinstance(raw_meta, str) or not raw_meta.strip():
            return []

        args: List[str] = []
        for _, prefix, key, val in _iter_meta_lines(raw_meta):
            if key is None or val is None:
                return []  # Invalid format — return empty list immediately

            if prefix == "all":
                for s in ["", "s:v", "s:a", "s:s"]:
                    args += ['-metadata' if not s else f'-metadata:{s}', f'{key}={val}']
            elif prefix:
                args += [f'-metadata:s:{prefix}', f'{key}={val}']
            else:
                args += ['-metadata', f'{key}={val}']

        return args
    except Exception:
        return []
        

async def get_chat(client, chat):
    try:
        return await client.get_chat(chat)
    except Exception as e:
        return None

async def get_src_client(user_id, chat_id, userBot):
    clients = [TgClient.bot, userBot]
    if bot_dict['SAVEBOT'] and bot_dict['SAVEBOT'].me.id != userBot.me.id:
        client.append(bot_dict['SAVEBOT'])
    for client in clients:
        if str(client.me.id) == str(chat_id):
            return client
    await sleep(0)
    return userBot

async def send_cached_media(client, message, user_id, real_msg, media, delete=0):
    try:
        chat_id = user_dict.setdefault(user_id, {}).get('LEECH_DUMP_CHAT')
        if not chat_id:
            if client.me.id == TgClient.ID:
                chat_id = Config.LEECH_DUMP_CHAT
            else:
                temp_dict = manage_dict.setdefault(message.from_user.id, {})
                if temp_dict.get('SRC_PUBLIC_CHAT_JOINED'):
                    chat_id = Config.SRC_PUBLIC_CHAT
                else:
                    try:
                        await join_chat(client, Config.SRC_PUBLIC_CHAT)
                        temp_dict['SRC_PUBLIC_CHAT_JOINED'] = True
                        chat_id = Config.SRC_PUBLIC_CHAT
                    except Exception as e:
                        if 'Already' in e:
                            chat_id = Config.SRC_PUBLIC_CHAT
                        else:
                            chat_id = 'me'
        sent_ = await client.send_cached_media(
           chat_id=chat_id,
           file_id=media.file_id,
           caption=real_msg.caption,
           caption_entities=real_msg.caption_entities, 
           reply_markup=real_msg.reply_markup or None
        )
        for chat_id_ in {user_id, message.chat.id}:
            if sent_.chat.id != chat_id_:
                try:
                    return await TgClient.bot.copy_message(
                        chat_id=chat_id_, 
                        from_chat_id=sent_.chat.id,
                        message_id=sent_.id,
                        caption_entities=sent_.caption_entities,
                        reply_to_message_id=message.id
                    )
                except Exception as e:
                    logger.error('copy', exc_info=True)
                    return None 
            
        if chat_id == Config.SRC_PUBLIC_CHAT:
            try:
                await sent_.delete()
            except Exception as e:
                pass
            
    except MessageEmpty:
        await send_alert(f"**Hey Sir 🤓, Bot Failed To Send Cache Media.\n\n•Message ID: `{real_msg.id}`**")
        sent_ = await client.send_message(
           chat_id=user_id,
           text=f"**I Can't Send The File Now, Kindly Try Again Later...**"
           )
    except FloodWait as fw:
        await sleep(fw.value)
        sent_ = await send_cached_media(client=client, message=message, user_id=user_id, real_msg=real_msg, media=media, delete=delete)
    if sent_ and delete:
        await delete_message(sent_, delay=delete)
    return sent_


async def get_userbot(user_id: int, notify=False):
    async with bot_lock:
        try:
            user_session = user_dict.get(user_id, {}).get('SESSION')
            if user_savebot := bot_dict.get('user_id'):
                if not user_session:
                    if user_savebot.is_connected:
                        await user_savebot.stop()
                return user_savebot

            if not user_session:
                if notify:
                    await send_message(user_id, f"No Session String Found !\n\n• Add Your Session String In /{BotCommands.UserSetCommand[0]}.")
                return None
            
            ubot_name = f"TG-Premium-{user_id}"
            await clean_target(f"{ubot_name}.session")
            bot_dict[user_id] = user_savebot = TgClient.wztgClient(
                ubot_name,
                session_string=user_session,
                no_updates=True,
            )
            await user_savebot.start()
            return user_savebot

        except Exception as e:
            if notify:
                await send_message(user_id, f"Error: {str(e)}")
            logger.error("UserBot initialization failed", exc_info=True)
            return None

async def join_chat(user_bot, invite_link):
    try:
        await user_bot.join_chat(invite_link)
        text = f"Successfully Joined The <a href='{invite_link}'>Chat 😀</a>..."
    except UserAlreadyParticipant:
        text = f"Already Joined The <a href='{invite_link}'>Chat 🙂</a>..."
    except (InviteHashInvalid, InviteHashExpired):
        text = f"Can't Join, Expired Or Invalid <a href='{invite_link}'> Link 😔</a>..."
    except FloodWait as e:
        text = f"<a href='{invite_link}'>Too Many Requests, Try Again After {e.value} seconds 😕...</a>"
    except Exception as e:
        await notify_owner(e)
        text = f"Failed To Join <a href='{invite_link}'>Chat</a>, Error: {e}"
    return text

async def left_chat(bot, chat_id):
    try:
        await bot.leave_chat(chat_id)
        text = f"Successfully Left The Chat ✅"
    except UserNotParticipant:
        text = f"I Am Not Member Of The Chat..."
    except FloodWait as e:
        text = f"FloodWait, Try Again After {e.value} Seconds"
    except Exception as e:
        await notify_owner(e)
        text = f"Failed To Leave Chat\n\n Error: {e}"
    return text

def parse_chat_id(chat_id):
    s = str(chat_id)
    if s.lstrip("-").isdigit():
        raw = s.lstrip("-")
        if raw.startswith("100"):
            return int(s)
        return int(f"-100{raw}")
    if not s.startswith("@"):
        return f"@{s}"
    return s

async def notify_owner(text):
    try:
        await TgClient.bot.send_message(chat_id=Config.OWNER_ID, text=text)
    except Exception as e:
        logger.error('something', exc_info=True)

