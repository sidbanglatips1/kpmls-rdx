from asyncio import sleep
from functools import partial
from html import escape
from io import BytesIO
from os import getcwd, path as ospath
from re import sub
from time import time
from aiofiles.os import makedirs, remove, path as aiopath
from langcodes import Language

from pyrogram.filters import create
from pyrogram.types import CallbackQuery
from pyrogram.handlers import MessageHandler

from bot.helper.ext_utils.status_utils import get_readable_file_size
from .. import excluded_extensions, sudo_users, user_dict, logger, bot_loop
from ..core.config_manager import Config
from ..core.tg_client import TgClient
from ..helper.ext_utils.bot_utils import get_size_bytes, new_task, update_user_ldata, has_premium
from ..helper.ext_utils.db_handler import database
from ..helper.ext_utils.media_utils import convert_to_jpeg, AddPhotoWatermark
from ..helper.telegram_helper.button_build import ButtonBuild
from ..helper.telegram_helper.message_utils import delete_message, edit_message, send_file, send_message
from ..helper.telegram_helper.bot_commands import BotCommands
from bot.helper.uset_helper import (leech_options, rclone_options, gdrive_options, ffset_options, advanced_options, yt_options, user_settings_text, pro_dict, 
    default_val, INT_KEYS, bool_dict, gofile_keys, uset_list, wm_dict, wmark_options_common, text_wm_options, image_wm_options, get_return_key, default_upload_details, WM_POSITIONS_DICT)
from bot.helper.utils import is_latest_pypi_version, get_path_dict
from bot.helper.telegram_helper.button_maker import ButtonMaker
from bot.helper.utils.gk_utils import validate_metadata_input


handler_dict = {}
TIMEOUT = 60 
VALIDATE_KEYS = ('LEECH_DUMP_CHAT')



@new_task
async def add_file(_, message, key, rfunc=None, value=None, query=None):
    user_id = message.from_user.id if query is None else query.from_user.id
    handler_dict[user_id] = False
    path_dict = get_path_dict(user_id)
    path = path_dict.get(key)
    if path:
        #await makedirs(ospath.dirname(path), exist_ok=True)
        await message.download(file_name=path)
        if key in ('THUMBNAIL', 'ATTACHMENT'):
            if key == 'ATTACHMENT' and (attach_name := message.caption):
                if not attach_name.endswith('.jpg'):
                    attach_name += '.jpg'
                bot_loop.create_task(update_user_ldata(user_id, 'ATTACHMENT_NAME', attach_name))
                
            await convert_to_jpeg(path)
            
        if key == 'INTRO_VIDEO':
            path = message.video.file_id
            
        await delete_message(message)
    bot_loop.create_task(update_user_ldata(user_id, key, path))
    if rfunc:
        await rfunc()

async def validate_uset(key, value):
    if key == 'LEECH_DUMP_CHAT':
        topic_id = None
        if '|' in value:    
            chat_id, topic_id = str(value).split('|', 1)
        else:
            if value.lstrip('-').isdigit():
                chat_id = int(value)
            else:
                chat_id = value.replace('@', '')
        try:
            ms = await TgClient.bot.send_message(chat_id, text='Test...', message_thread_id=topic_id)
            await delete_message(ms)
            return value
        except Exception as e:
            raise ValueError(str(e))
            
async def get_value(key, user_id, default_value=False, user_data=None, is_private=True):
    if user_data is None:
        user_data = user_dict.get(user_id, {})
    path_dict = get_path_dict(user_id)

    if path_key := path_dict.get(key):
        exists = await aiopath.exists(path_key)
        value = 'ADDED' if exists else 'NOT SET'
        return value, exists
    value = user_data.get(key, '')
    if str(value).lower() in {'none', ''}:
        value = Config.get(key) if default_value else 'none' 
    value_exists = str(value).lower() not in {'not set', 'disabled', 'false', 'none', ''}
    if not value_exists:
        value = default_val
    return value, value_exists

async def thumb_handler_direct_func(client, message):
    try:
        user_id = message.from_user.id
        arg = message.command[0]
        if arg in BotCommands.ThumbAddCommand:
            if not (reply_msg := message.reply_to_message) or not reply_msg.photo:
                return await send_message(message, '>**Reply To Any Photo To Add Thumbnail !**')
            query = await send_message(message, ">**Adding Thumbnail...**", photo=Config.GKBOTZ_IMAGE)
            await add_file(client, reply_msg, key='THUMBNAIL')
            
        elif arg in BotCommands.ThumbDelCommand:
            query = await send_message(message, ">**Deleting Thumbnail...**", photo=Config.GKBOTZ_IMAGE)
            thumb_path = f"thumbnails/{user_id}.jpg"
            if await aiopath.exists(thumb_path):
                await remove(thumb_path)
            await update_user_ldata(user_id, key='THUMBNAIL')
            
        else:
            query = await send_message(message, ">**Fetching Thumbnail...**", photo=Config.GKBOTZ_IMAGE)
        query.from_user = message.from_user
        await sleep(3)
        await update_user_settings(query, stype='leech', key='THUMBNAIL')
    
    except Exception as e:
        logger.error('Kh', exc_info=True)

@new_task
async def set_option(_, message, key, rfunc, value=None, query=None):
    user_id = message.from_user.id if query is None else query.from_user.id
    handler_dict[user_id] = False
    value = message.text if value is None and (message and hasattr(message, 'text')) else value
    success = True
    text = ''
    if value:
        try:
            if key in VALIDATE_KEYS:
                await validate_uset(key, value)
            elif key in INT_KEYS:
                value = int(value)
        except Exception as e:
            await rfunc()
            return await send_message(message, str(e), delete=33)
        if key == 'SAMPLE_IMAGE':
            if value < MIN_SAMPLE_IMAGE:
                text = f'Sample Image Value Should Be More Than {MIN_SAMPLE_IMAGE} !'
            elif value > MAX_SAMPLE_IMAGE:
                text = f'Sample Image Value Should Be Less Than {MAX_SAMPLE_IMAGE} !'
            if text:
                await send_message(message, text, delete=33)
                return await rfunc()
        
        elif key == 'SAMPLE_VIDEO':
            if value < MIN_SAMPLE_VIDEO:
                text = f'Sample Video Value Should Be More Than {MIN_SAMPLE_VIDEO} !'
            elif value > MAX_SAMPLE_VIDEO:
                text = f'Sample Video Value Should Be Less Than {MAX_SAMPLE_VIDEO} !'
            if text: 
                await send_message(message, text, delete=33)
                return await rfunc()
            
        elif key == "LEECH_SPLIT_SIZE":
            if not value.isdigit():
                value = get_size_bytes(value)
            value = min(int(value), TgClient.MAX_SPLIT_SIZE)
        # elif key == "LEECH_DUMP_CHAT": # TODO: Add
        elif key == "YT_TAGS":
            if isinstance(value, str):
                value = [tag.strip() for tag in value.split(",") if tag.strip()]
            elif not isinstance(value, list):
                await send_message(message, "YT Tags must be a comma-separated string.")
                return
        elif key == "YT_CATEGORY_ID":
            if isinstance(value, str) and value.isdigit():
                value = int(value)
            elif not isinstance(value, int):
                await send_message(message, "YT Category ID must be a whole number.")
                return
        elif key == "YT_PRIVACY_STATUS":
            allowed_statuses = ["public", "private", "unlisted"]
            if not isinstance(value, str) or value.lower() not in allowed_statuses:
                await send_message(
                    message,
                    f"YT Privacy Status must be one of: {', '.join(allowed_statuses)}.",
                )
                return
            value = value.lower()
        elif key in ["UPLOAD_PATHS", "FFMPEG_CMDS", "YT_DLP_OPTIONS"]:
            if value.startswith("{") and value.endswith("}"):
                try:
                    value = eval(sub(r"\s+", " ", value))
                except Exception as e:
                    await send_message(message, str(e))
                    return
            else:
                await send_message(message, "It must be dict!")
                return
        else:
            value = Config.value_parser(key, value)
            
    if success:
        await update_user_ldata(user_id, key, value)
    await rfunc()
    if not query:
        return await delete_message(message)
    
@new_task
async def edit_user_settings(client, query):
    from_user = query.from_user
    user_id = from_user.id
    handler_dict[user_id] = False
    name = from_user.mention
    message = query.message
    data = query.data.split()
    path_dict = get_path_dict(user_id)
    
    thumb_path = f"thumbnails/{user_id}.jpg"
    rclone_conf = f"rclone/{user_id}.conf"
    token_pickle = f"tokens/{user_id}.pickle"
    yt_cookie_path = f"cookies/{user_id}/cookies.txt"

    user_data = user_dict.get(user_id, {})
    if user_id != int(data[1]):
        return await query.answer("Not Yours!", show_alert=True)
    
    if len(data) >= 3 and data[2] in PREMIUM_FEATURES and not has_premium(query.from_user.id, query.message.chat.id):
        return await query.answer('Opps Premium Features Only !', True)
        
    if data[-1] in bool_dict:
        key = data[-1]
        return_key = get_return_key(key)
        value, value_exists = await get_value(key, user_id, user_data=user_data)
        if bool_dict[key][0] in [True, False]:
            value = value_exists
        list_ = bool_dict[key]
        try:
            index = list_.index(value)
        except Exception:
            index = 0
        new_value = list_[(index + 1) % len(list_)]
        query.message.from_user = query.from_user
        await update_user_ldata(user_id, key, new_value)
        await update_user_settings(query, stype=return_key)
        return
    
    elif data[-1] == "SET":
        key = data[3]
        return_key = get_return_key(key)
        value, value_exists = await get_value(key, user_id, user_data=user_data)
        query.message.from_user = query.from_user
        new_value = data[-2]
        await update_user_ldata(user_id, key, new_value)
        await update_user_settings(query, stype=return_key)
        return
    
    elif data[2] == 'gk':
        key = data[3]
        edit_mode = data[-1] == 'edit'
        show_menu = data[-1] == 'MENU'
        rfunc = partial(update_user_settings, query, stype=get_return_key(key), edit_mode=edit_mode, show_menu=show_menu)
        await rfunc(key=key)
        if data[-1] == 'login' and key=='SESSION': # Special 
            if not await is_latest_pypi_version('pyrofork'):
                await query.answer('Use This Bot To Generate Session String !', show_alert=True)
                return await edit_message(query, "Kindly Generate Session Via: @GK_SessionBot\n\nAfter Getting Session Send Session Here")
            await query.answer()
            from bot.modules.ssgen import generate_session_string
            if user_session_str := await generate_session_string(client, query):
                await set_option(None, query, key, rfunc, value=user_session_str, query=query)
                return
            
        if data[-1] == 'del':
            if key in path_dict and await aiopath.exists(path_dict[key]):
                await remove(path_dict[key])
                
            await set_option(None, None, key, rfunc, query=query)
            return
        
        if edit_mode:
            to_func = set_option
            type = 'text'
            rfunc = partial(update_user_settings, query, stype=get_return_key(key))
            if key == 'SESSION':
                if query.message.chat.type.name != 'PRIVATE':
                    await query.answer('Kindly Open User Setting In PM To View/Edit Session Settings !', show_alert=True)
                    btn = ButtonMaker()
                    btn.ubutton('View PM', f't.me/{client.me.username}?start=ssgen')
                    return await edit_message(query, "Click Button Below To Start Me In PM And Generate Session String !", buttons=btn.build(1))
            
            elif key in path_dict:
                to_func = add_file
                type = 'photo' if key in {'ATTACHMENT', 'THUMBNAIL', 'WM_IMAGE'} else ('video' if key == 'INTRO_VIDEO' else 'document')
            
            pfunc = partial(to_func, key=data[3], rfunc=rfunc)
            await event_handler(client, query, pfunc, rfunc, type=type)
        return
    
    elif data[2] == "setevent":
        await query.answer()
        
    elif data[2] in [
        "general",
        "mirror",
        "leech",
        "ffset",
        "advanced",
        "gdrive",
        "rclone",
        "gofile",
        'wmark',
    ]:
        await query.answer()
        await update_user_settings(query, stype=data[2])
    elif data[2] == "yttools":
        await query.answer()
        await update_user_settings(query, stype=data[2])
    elif data[2] == "menu":
        await query.answer()
        await get_menu(data[3], message, user_id)
    elif data[2] == "tog":
        await query.answer()
        await update_user_ldata(user_id, data[3], data[4] == "t")
        if data[3] == "STOP_DUPLICATE":
            back_to = "gdrive"
        elif data[3] in ["USER_TOKENS", "USE_DEFAULT_COOKIE"]:
            back_to = "general"
        else:
            back_to = "leech"
        await update_user_settings(query, stype=back_to)
    elif data[2] == "file":
        await query.answer()
        buttons = ButtonBuild()
        text = user_settings_text[data[3]][2]
        buttons.data_button("Stop", f"userset {user_id} menu {data[3]} stop")
        buttons.data_button("Back", f"userset {user_id} menu {data[3]}", "footer")
        buttons.data_button("Close", f"userset {user_id} close", "footer")
        prompt_title = data[3].replace("_", " ").title()
        new_message_text = f"⌬ <b>Set {prompt_title}</b>\n\n{text}"
        await edit_message(message, new_message_text, buttons.build_menu(1))
        rfunc = partial(get_menu, data[3], message, user_id)
        pfunc = partial(add_file, key=data[3], rfunc=rfunc)
        type = 'photo' if data[3] in {'ATTACHMENT', 'THUMBNAIL'} else 'document'
        await event_handler(
            client,
            query,
            pfunc,
            rfunc,
            type=type,
        )
    elif data[2] in ["set", "addone", "rmone"]:
        await query.answer()
        buttons = ButtonBuild()
        if data[2] == "set":
            text = user_settings_text[data[3]][2]
            func = set_option
        elif data[2] == "addone":
            text = f"Add one or more string key and value to {data[3]}. Example: {{'key 1': 62625261, 'key 2': 'value 2'}}. Timeout: {TIMEOUT} sec"
            func = add_one
        elif data[2] == "rmone":
            text = f"Remove one or more key from {data[3]}. Example: key 1/key2/key 3. Timeout: {TIMEOUT} sec"
            func = remove_one
        buttons.data_button("Stop", f"userset {user_id} menu {data[3]} stop")
        buttons.data_button("Back", f"userset {user_id} menu {data[3]}", "footer")
        buttons.data_button("Close", f"userset {user_id} close", "footer")
        msg_txt = (message.caption if hasattr(message, 'caption') and message.caption else message.text).html
        await edit_message(
            message, msg_txt + "\n\n" + text, buttons.build_menu(1)
        )
        rfunc = partial(get_menu, data[3], message, user_id)
        pfunc = partial(func, key=data[3], rfunc=rfunc)
        await event_handler(client, query, pfunc, rfunc)
    elif data[2] == "remove":
        await query.answer("Removed!", show_alert=True)
        if data[3] in [
            "RCLONE_CONFIG",
            "TOKEN_PICKLE",
            "USER_COOKIE_FILE",
        ]:
            if data[3] == "RCLONE_CONFIG":
                fpath = rclone_conf
            elif data[3] == "USER_COOKIE_FILE":
                fpath = yt_cookie_path
            else:
                fpath = token_pickle
            if await aiopath.exists(fpath):
                await remove(fpath)
            del user_data[data[3]]
            await database.update_user_doc(user_id, data[3])
        else:
            await update_user_ldata(user_id, data[3], "")
        await get_menu(data[3], message, user_id)
    elif data[2] == "reset":
        user_data.pop(data[3], None)
        await database.update_user_data(user_id, key=data[3], value=0)
        await query.answer("Reset Done!", show_alert=True)
        await get_menu(data[3], message, user_id)
    elif data[2] == "confirm_reset_all":
        await query.answer()
        buttons = ButtonBuild()
        buttons.data_button("Yes", f"userset {user_id} do_reset_all yes")
        buttons.data_button("No", f"userset {user_id} do_reset_all no")
        buttons.data_button("Close", f"userset {user_id} close", "footer")
        text = "<i>Are you sure you want to reset all your user settings?</i>"
        await edit_message(query, text, buttons.build_menu(2))
    elif data[2] == "do_reset_all":
        if data[3] == "yes":
            await query.answer("Reset Done!", show_alert=True)
            user_data = user_dict.get(user_id, {})
            for k in list(user_data.keys()):
                if k not in ("SUDO", "AUTH", "VERIFY_TOKEN", "VERIFY_EXPIRE_TIME"):
                    del user_data[k]
            for fpath in get_path_dict.values():
                if await aiopath.exists(fpath):
                    await remove(fpath)
            await update_user_settings(query, stype='main')
            await database.update_user_data(user_id)
        else:
            await query.answer("Reset Cancelled.", show_alert=True)
            await update_user_settings(query, stype='main')
    elif data[2] == "view":
        await query.answer()
        await send_file(message, thumb_path, name)
    elif data[2] in default_upload_details:
        await query.answer()
        next_key = list(default_upload_details)[(list(default_upload_details).index(data[2]) + 1) % len(default_upload_details)]
        await update_user_ldata(user_id, "DEFAULT_UPLOAD", next_key)
        await update_user_settings(query, stype="general")
    elif data[2] == "back":
        await query.answer()
        stype = data[3] if len(data) == 4 else "main"
        await update_user_settings(query, stype=stype)
    else:
        await query.answer()
        await delete_message(message, message.reply_to_message)
        
async def get_user_settings(message, stype="", key=None, edit_mode=False, show_menu=False):
    from_user = message.from_user
    if isinstance(message, CallbackQuery):
        message = message.message
    is_private = message.chat.type.name == 'PRIVATE'
    user_id = from_user.id
    user_name = from_user.mention(style="html")
    buttons = ButtonBuild()
    path_dict = get_path_dict(user_id)
    rclone_conf = f"rclone/{user_id}.conf"
    token_pickle = f"tokens/{user_id}.pickle"
    user_data = user_dict.get(user_id, {})
    photo = Config.GKBOTZ_IMAGE
    return_key = get_return_key(key)
    is_private = message.chat.type.name == 'PRIVATE'
    need_edit_key = True 
    BUTTON_ROW = 2
    
    if key:
        text = ''
        extra_text = ''
        value, value_exists = await get_value(key, user_id, user_data=user_data)
        value = "ENABLED" if value is True else ("DISABLED" if value is False else ('ADDED' if (value != default_val and key in {'REMOVE', 'SESSION'}) else value))
        if value not in {'ENABLED', 'DISABLED'} and message.chat.type.name != 'PRIVATE' and value_exists:
            value = 'ADDED'
        if key == 'THUMBNAIL':
            auto_thumb, auto_thumb_exists = await get_value('AUTO_THUMBNAIL', user_id, user_data=user_data)
            extra_text = f'\n┊ **Auto Thumbnail**: {auto_thumb}'
            buttons.data_button(('✓ ' if auto_thumb_exists else '') + pro_dict['AUTO_THUMBNAIL'][0], f'userset {user_id} gk AUTO_THUMBNAIL', 'header')
        elif key == 'WM_POSITION' and show_menu:
            BUTTON_ROW = 3
            need_edit_key = False
            for k, v in WM_POSITIONS_DICT.items():
                buttons.data_button(('√ ' if k == value else '') + v, f"userset {user_id} gk {key} {k} SET")
            buttons.data_button('Custom Position', f"userset {user_id} gk {key} edit")
                
            #elif key == 'SAMPLE_IMAGE':
                
                #merge_images, merge_images_exists = await get_value('MERGE_IMAGES', user_id, user_data=user_data)
                #extra_text = f'\n┊ **Merge Images**: {merge_images}'
                #buttons.data_button(('✓ ' if merge_images_exists else '') + pro_dict['MERGE_IMAGES'][0], f'userset {user_id} gk MERGE_IMAGES', 'header')
                    
        key_list = pro_dict[key]
        text = f"""〄 `{key_list[0]}` Setting:\n╭
┊ **{key}**: {value}{extra_text}
╰ **Description**: {key_list[1]}"""

        if need_edit_key:
            if edit_mode:
                text += f"\n\n>☆ {key_list[2]}\n**Timeout**: {TIMEOUT} Sec."
                buttons.data_button('Stop Edit', f'userset {user_id} gk {key}')
            else:
                if value_exists:
                    buttons.data_button('Change', f'userset {user_id} gk {key} edit')
                    buttons.data_button('Delete', f'userset {user_id} gk {key} del')
                else:   
                    buttons.data_button(f"Set {key_list[0]}", f"userset {user_id} gk {key} edit")
                if key == 'SESSION':
                    buttons.data_button('Login', f'userset {user_id} gk {key} login')
    elif stype == "main":
        text = f"""<b><u>〄 User Settings:</u></b>
╭ Name: <b>{user_name}</b>
┊ User ID: <b>{user_id}</b>
┊ DC ID: <b>{from_user.dc_id}</b>
"""
        def_up = user_dict.get(user_id, {}).get('DEFAULT_UPLOAD', Config.DEFAULT_UPLOAD)
        def_up = default_upload_details[def_up]
        buttons.data_button(f"Default Upload: {def_up}", f"userset {user_id} gk DEFAULT_UPLOAD", position="header")
        buttons.data_button("General Settings", f"userset {user_id} general")
        buttons.data_button("Mirror Settings", f"userset {user_id} mirror")
        buttons.data_button("Leech Settings", f"userset {user_id} leech")
        buttons.data_button("FF Media Settings", f"userset {user_id} ffset")
        buttons.data_button("Watermark Settings", f"userset {user_id} wmark")
        buttons.data_button("Mics Settings", f"userset {user_id} advanced")
        for key in uset_list:
            value, value_exists = await get_value(key, user_id, True, user_data=user_data)
            value = "ENABLED" if value is True else ("DISABLED" if value is False else ('ADDED' if value_exists and key not in bool_dict else value))
            if key == 'DEFAULT_UPLOAD':
                value = default_upload_details[value]
            symbol = '╰' if key == uset_list[-1] else '┊'
            text += f"{symbol} {pro_dict[key][0]}: <b>{value}</b>\n"
            if key != 'DEFAULT_UPLOAD':
                buttons.data_button(('✓ ' if value_exists else '') + pro_dict[key][0], f'userset {user_id} gk {key}')
                
             
        if user_data and any(
            key in user_data
            for key in list(user_settings_text.keys())
            + [
                "USER_TOKENS",
                "AS_DOCUMENT",
                "EQUAL_SPLITS",
                "MEDIA_GROUP",
                "STOP_DUPLICATE",
                "DEFAULT_UPLOAD",
            ]
        ):
            buttons.data_button("Reset All", f"userset {user_id} confirm_reset_all")
    elif stype == "general":
        if user_data.get("DEFAULT_UPLOAD", ""):
            default_upload = user_data["DEFAULT_UPLOAD"]
        elif "DEFAULT_UPLOAD" not in user_data:
            default_upload = Config.DEFAULT_UPLOAD
        du = default_upload_details[default_upload]
        next_key = list(default_upload_details)[(list(default_upload_details).index(default_upload) + 1) % len(default_upload_details)]
        buttons.data_button(
            f"Swap to: {default_upload_details.get(next_key)} Mode", f"userset {user_id} {default_upload}", 'header'
        )

        user_tokens = user_data.get("USER_TOKENS", False)
        tr = "USER" if user_tokens else "OWNER"
        trr = "OWNER" if user_tokens else "USER"
        buttons.data_button(
            f"Swap to {trr} token/config",
            f"userset {user_id} tog USER_TOKENS {'f' if user_tokens else 't'}",
        )

        def_cookies = user_data.get("USE_DEFAULT_COOKIE", False)
        cookie_mode = "Owner's Cookie" if def_cookies else "User's Cookie"
        buttons.data_button(
            f"Swap to {'OWNER' if not def_cookies else 'USER'}'s Cookie File",
            f"userset {user_id} tog USE_DEFAULT_COOKIE {'f' if def_cookies else 't'}",
        )
        text = f"""⌬ <b>General Settings :</b>
╭ <b>Name</b>: {user_name}
┊
┊ <b>Default Upload Package</b>: <b>{du}</b>
┊ <b>Default Usage Mode</b>: <b>{tr}'s</b> token/config
╰ <b>yt Cookies Mode</b>: <b>{cookie_mode}</b>
"""

    elif stype == "leech":
        buttons.data_button(
            "Leech Split Size", f"userset {user_id} menu LEECH_SPLIT_SIZE"
        )
        if user_data.get("LEECH_SPLIT_SIZE", False):
            split_size = user_data["LEECH_SPLIT_SIZE"]
        else:
            split_size = Config.LEECH_SPLIT_SIZE
        if (
            user_data.get("AS_DOCUMENT", False)
            or "AS_DOCUMENT" not in user_data
            and Config.AS_DOCUMENT
        ):
            ltype = "DOCUMENT"
            buttons.data_button("Send As Media", f"userset {user_id} tog AS_DOCUMENT f")
        else:
            ltype = "MEDIA"
            buttons.data_button(
                "Send As Document", f"userset {user_id} tog AS_DOCUMENT t"
            )
        if (
            user_data.get("EQUAL_SPLITS", False)
            or "EQUAL_SPLITS" not in user_data
            and Config.EQUAL_SPLITS
        ):
            buttons.data_button(
                "Disable Equal Splits", f"userset {user_id} tog EQUAL_SPLITS f"
            )
            equal_splits = "Enabled"
        else:
            buttons.data_button(
                "Enable Equal Splits", f"userset {user_id} tog EQUAL_SPLITS t"
            )
            equal_splits = "Disabled"
        if (
            user_data.get("MEDIA_GROUP", False)
            or "MEDIA_GROUP" not in user_data
            and Config.MEDIA_GROUP
        ):
            buttons.data_button(
                "Disable Media Group", f"userset {user_id} tog MEDIA_GROUP f"
            )
            media_group = "Enabled"
        else:
            buttons.data_button(
                "Enable Media Group", f"userset {user_id} tog MEDIA_GROUP t"
            )
            media_group = "Disabled"
        
        buttons.data_button(
            "Thumbnail Layout", f"userset {user_id} menu THUMBNAIL_LAYOUT"
        )
        if user_data.get("THUMBNAIL_LAYOUT", False):
            thumb_layout = user_data["THUMBNAIL_LAYOUT"]
        elif "THUMBNAIL_LAYOUT" not in user_data and Config.THUMBNAIL_LAYOUT:
            thumb_layout = Config.THUMBNAIL_LAYOUT
        else:
            thumb_layout = "None"

        text = f"""⌬ <b>Leech Settings :</b>
╭ <b>Name</b>: {user_name}
┊
┊ Leech Type: <b>{ltype}</b>
┊ Leech Split Size: <b>{get_readable_file_size(split_size)}</b>
┊ Equal Splits: <b>{equal_splits}</b>
┊ Media Group: <b>{media_group}</b>
╰ Thumbnail Layout: <b>{thumb_layout}</b>
"""

    elif stype == "rclone":
        buttons.data_button("Rclone Config", f"userset {user_id} menu RCLONE_CONFIG")
        buttons.data_button(
            "Default Rclone Path", f"userset {user_id} menu RCLONE_PATH"
        )
        buttons.data_button("Rclone Flags", f"userset {user_id} menu RCLONE_FLAGS")

        rccmsg = "Exists" if await aiopath.exists(rclone_conf) else "Not Exists"
        if user_data.get("RCLONE_PATH", False):
            rccpath = user_data["RCLONE_PATH"]
        elif Config.RCLONE_PATH:
            rccpath = Config.RCLONE_PATH
        else:
            rccpath = "None"
        if user_data.get("RCLONE_FLAGS", False):
            rcflags = user_data["RCLONE_FLAGS"]
        elif "RCLONE_FLAGS" not in user_data and Config.RCLONE_FLAGS:
            rcflags = Config.RCLONE_FLAGS
        else:
            rcflags = "None"

        text = f"""⌬ <b>RClone Settings :</b>
╭ <b>Name</b>: {user_name}
┊
┊ <b>Rclone Config</b>: <b>{rccmsg}</b>
┊ <b>Rclone Flags</b>: <code>{rcflags}</code>
╰ <b>Rclone Path</b>: <code>{rccpath}</code>"""

    elif stype == "gofile":
        gf_token, _ = await get_value('GOFILE_TOKEN', user_id, True, user_data, is_private=is_private)
        gf_folder, _ = await get_value('GOFILE_FOLDER', user_id, True, user_data, is_private=is_private)
        text = f"""<b><u>〄 GoFile Tools Settings:</u></b>
\n╭ <b>GoFile Token</b>: {gf_token}
╰ <b>GoFile Folder</b>: {gf_folder}"""
        buttons.data_button("GoFile API", f"userset {user_id} gk GOFILE_TOKEN")
        buttons.data_button("GOFile Folder", f"userset {user_id} gk GOFILE_FOLDER")
    
    elif stype == "gdrive":
        buttons.data_button("token.pickle", f"userset {user_id} menu TOKEN_PICKLE")
        buttons.data_button("Default Gdrive ID", f"userset {user_id} menu GDRIVE_ID")
        buttons.data_button("Index URL", f"userset {user_id} menu INDEX_URL")
        if (
            user_data.get("STOP_DUPLICATE", False)
            or "STOP_DUPLICATE" not in user_data
            and Config.STOP_DUPLICATE
        ):
            buttons.data_button(
                "Disable Stop Duplicate", f"userset {user_id} tog STOP_DUPLICATE f"
            )
            sd_msg = "Enabled"
        else:
            buttons.data_button(
                "Enable Stop Duplicate",
                f"userset {user_id} tog STOP_DUPLICATE t",
                "l_body",
            )
            sd_msg = "Disabled"
        tokenmsg = "Exists" if await aiopath.exists(token_pickle) else "Not Exists"
        if user_data.get("GDRIVE_ID", False):
            gdrive_id = user_data["GDRIVE_ID"]
        elif GDID := Config.GDRIVE_ID:
            gdrive_id = GDID
        else:
            gdrive_id = "None"
        index = user_data["INDEX_URL"] if user_data.get("INDEX_URL", False) else "None"
        text = f"""⌬ <b>GDrive Tools Settings :</b>
╭ <b>Name</b>: {user_name}
┊
┊ <b>Gdrive Token</b>: <b>{tokenmsg}</b>
┊ <b>Gdrive ID</b>: <code>{gdrive_id}</code>
┊ <b>Index URL</b>: <code>{index}</code>
╰ <b>Stop Duplicate</b>: <b>{sd_msg}</b>"""
    
    elif stype == "mirror":
        buttons.data_button("RClone Tools", f"userset {user_id} rclone")
        rccmsg = "Exists" if await aiopath.exists(rclone_conf) else "Not Exists"
        if user_data.get("RCLONE_PATH", False):
            rccpath = user_data["RCLONE_PATH"]
        elif RP := Config.RCLONE_PATH:
            rccpath = RP
        else:
            rccpath = "None"

        buttons.data_button("GDrive Tools", f"userset {user_id} gdrive")
        tokenmsg = "Exists" if await aiopath.exists(token_pickle) else "Not Exists"
        if user_data.get("GDRIVE_ID", False):
            gdrive_id = user_data["GDRIVE_ID"]
        elif GI := Config.GDRIVE_ID:
            gdrive_id = GI
        else:
            gdrive_id = "None"
        
        buttons.data_button("GoFile Tools", f"userset {user_id} gofile")
        index = user_data["INDEX_URL"] if user_data.get("INDEX_URL", False) else "None"
        if (
            user_data.get("STOP_DUPLICATE", False)
            or "STOP_DUPLICATE" not in user_data
            and Config.STOP_DUPLICATE
        ):
            sd_msg = "Enabled"
        else:
            sd_msg = "Disabled"

        buttons.data_button("YT Up Tools", f"userset {user_id} yttools")
        text = f"""⌬ <b>Mirror Settings :</b>
╭ <b>Name</b>: {user_name}
┊
┊ <b>Rclone Config</b>: <b>{rccmsg}</b>
┊ <b>Rclone Path</b>: <code>{rccpath}</code>
┊ <b>Gdrive Token</b>: <b>{tokenmsg}</b>
┊ <b>Gdrive ID</b>: <code>{gdrive_id}</code>
┊ <b>Index Link</b>: <code>{index}</code>
╰ <b>Stop Duplicate</b>: <b>{sd_msg}</b>
"""
    elif stype == 'wmark':
        photo = await AddPhotoWatermark("bot/helper/watermark.jpeg", user_id, user_data)
        wmark_type = user_data.get('WM_TYPE', 'text')
        text = f"⌬ <b>Watermark Settings:</b>\n╭ <b>Name</b>: {user_name}\n┊ <b>Watermark Type:</b> {wmark_type}\n"
        wm_set = (text_wm_options if wmark_type == 'text' else image_wm_options) + wmark_options_common
        change_to = 'Photo' if wmark_type == 'text' else 'Text'
        buttons.data_button(f'Change To: {change_to} Watermark', f"userset {user_id} gk WM_TYPE", 'header')
        for key in wm_set:
            value, value_exists = await get_value(key, user_id, user_data=user_data, default_value=wm_dict.get(key))
            value = "ENABLED" if value is True else ("DISABLED" if value is False else ('ADDED' if (value != default_val and key in {'remove', 'session'}) else value))
            if value not in {'ENABLED', 'DISABLED'} and message.chat.type.name != 'PRIVATE' and value_exists:
                value = 'ADDED'
            symbol = '╰' if key == wm_set[-1] else '┊'
            text += f'{symbol} <b>{pro_dict[key][0]}:</b> {value}\n'
            if key == 'WM_POSITION':
                buttons.data_button(pro_dict[key][0], f"userset {user_id} gk {key} MENU")
            else:
                buttons.data_button(('🟢' if value_exists and key in bool_dict else '') + pro_dict[key][0], f"userset {user_id} gk {key}")
        
        
    elif stype == "ffset":
        buttons.data_button(
            "FFmpeg Cmds", f"userset {user_id} menu FFMPEG_CMDS", "header"
        )
        if user_data.get("FFMPEG_CMDS", False):
            ffc = user_data["FFMPEG_CMDS"]
        elif "FFMPEG_CMDS" not in user_data and Config.FFMPEG_CMDS:
            ffc = Config.FFMPEG_CMDS
        else:
            ffc = "<b>Not Exists</b>"

        if isinstance(ffc, dict):
            ffc = "\n" + "\n".join(
                [
                    f"{no}. <b>{key}</b>: <code>{escape(str(value[0]))}</code>"
                    for no, (key, value) in enumerate(ffc.items(), start=1)
                ]
            )

        text = f"""⌬ <b>FF Settings :</b>
╭ <b>Name</b>: {user_name}
┊
╰ <b>FFmpeg CLI Commands</b>: {ffc}"""

    elif stype == "advanced":
        buttons.data_button("YT-DLP Options", f"userset {user_id} menu YT_DLP_OPTIONS")
        if user_data.get("YT_DLP_OPTIONS", False):
            ytopt = user_data["YT_DLP_OPTIONS"]
        elif "YT_DLP_OPTIONS" not in user_data and Config.YT_DLP_OPTIONS:
            ytopt = Config.YT_DLP_OPTIONS
        else:
            ytopt = "None"

        upload_paths = user_data.get("UPLOAD_PATHS", {})
        if not upload_paths and "UPLOAD_PATHS" not in user_data and Config.UPLOAD_PATHS:
            upload_paths = Config.UPLOAD_PATHS
        else:
            upload_paths = "None"
        buttons.data_button("Upload Paths", f"userset {user_id} menu UPLOAD_PATHS")

        yt_cookie_path = f"cookies/{user_id}/cookies.txt"
        user_cookie_msg = (
            "Exists" if await aiopath.exists(yt_cookie_path) else "Not Exists"
        )
        buttons.data_button(
            "YT Cookie File", f"userset {user_id} menu USER_COOKIE_FILE"
        )

        text = f"""⌬ <b>Advanced Settings :</b>
╭ <b>Name</b>: {user_name}
┊
┊ <b>Upload Paths</b>: <b>{upload_paths}</b>
┊ <b>YT-DLP Options</b>: <code>{ytopt}</code>
╰ <b>YT User Cookie File</b>: <b>{user_cookie_msg}</b>"""
    
    elif stype == "yttools":
        buttons.data_button("YT Description", f"userset {user_id} menu YT_DESP")
        yt_desp_val = user_data.get(
            "YT_DESP",
            Config.YT_DESP if hasattr(Config, "YT_DESP") else "Not Set (Uses Default)",
        )

        buttons.data_button("YT Tags", f"userset {user_id} menu YT_TAGS")
        yt_tags_val = user_data.get(
            "YT_TAGS",
            Config.YT_TAGS if hasattr(Config, "YT_TAGS") else "Not Set (Uses Default)",
        )
        if isinstance(yt_tags_val, list):
            yt_tags_val = ",".join(yt_tags_val)

        buttons.data_button("YT Category ID", f"userset {user_id} menu YT_CATEGORY_ID")
        yt_cat_id_val = user_data.get(
            "YT_CATEGORY_ID",
            (
                Config.YT_CATEGORY_ID
                if hasattr(Config, "YT_CATEGORY_ID")
                else "Not Set (Uses Default)"
            ),
        )

        buttons.data_button(
            "YT Privacy Status", f"userset {user_id} menu YT_PRIVACY_STATUS"
        )
        yt_privacy_val = user_data.get(
            "YT_PRIVACY_STATUS",
            (
                Config.YT_PRIVACY_STATUS
                if hasattr(Config, "YT_PRIVACY_STATUS")
                else "Not Set (Uses Default)"
            ),
        )

        text = f"""⌬ <b>YouTube Tools Settings:</b>
╭ <b>Name</b>: {user_name}
┊
┊ <b>YT Description</b>: <code>{escape(str(yt_desp_val))}</code>
┊ <b>YT Tags</b>: <code>{escape(str(yt_tags_val))}</code>
┊ <b>YT Category ID</b>: <code>{escape(str(yt_cat_id_val))}</code>
╰ <b>YT Privacy Status</b>: <code>{escape(str(yt_privacy_val))}</code>"""
    
    if key and (key_path := path_dict.get(key)) and key_path.endswith('.jpg') and await aiopath.exists(key_path):
        photo = key_path
    
    if stype != 'main' or key:
        buttons.data_button('Back', f'userset {user_id} back {return_key}', 'footer')
    buttons.data_button("Close", f"userset {user_id} close", "footer")
    btns = buttons.build_menu(BUTTON_ROW)

    return text, btns, photo
    

async def update_user_settings(query, stype="", key=None, edit_mode=False, show_menu=False):
    handler_dict[query.from_user.id] = False
    msg, button, photo = await get_user_settings(query, stype, key, edit_mode, show_menu=show_menu)
    await edit_message(query, msg, button, photo=photo)

@new_task
async def send_user_settings(_, message):
    try:
        handler_dict[message.from_user.id] = False
        msg, button, photo = await get_user_settings(message, stype='main')
        await send_message(message, msg, button, photo=photo)
    except Exception as e:
        logger.error('Uset', exc_info=True)

@new_task
async def add_one(_, message, key, rfunc):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    user_data = user_dict.get(user_id, {})
    value = message.text
    if value.startswith("{") and value.endswith("}"):
        try:
            value = eval(value)
            if user_data[key]:
                user_data[key].update(value)
            else:
                await update_user_ldata(user_id, key, value)
        except Exception as e:
            await send_message(message, str(e))
            return
    else:
        await send_message(message, "It must be Dict!")
        return
    await delete_message(message)
    await rfunc()

@new_task
async def remove_one(_, message, key, rfunc):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    user_data = user_dict.get(user_id, {})
    names = message.text.split("/")
    for name in names:
        if name in user_data[key]:
            del user_data[key][name]
    await delete_message(message)
    await rfunc()
    await database.update_user_data(user_id)

async def get_menu(option, message, user_id):
    handler_dict[user_id] = False
    user_data = user_dict.get(user_id, {})

    path_dict = get_path_dict(user_dict)
    
    buttons = ButtonBuild()
    if option in ["RCLONE_CONFIG", "TOKEN_PICKLE", "USER_COOKIE_FILE"]:
        key = "file"
    else:
        key = "set"
    buttons.data_button(
        "Change" if user_data.get(option, False) else "Set",
        f"userset {user_id} {key} {option}",
    )
    if user_data.get(option, False):
        if option in ["YT_DLP_OPTIONS", "FFMPEG_CMDS", "UPLOAD_PATHS"]:
            buttons.data_button(
                "Add One", f"userset {user_id} addone {option}", "header"
            )
            buttons.data_button(
                "Remove One", f"userset {user_id} rmone {option}", "header"
            )

        if key != "file":  # TODO: option Default val check
            buttons.data_button("Reset", f"userset {user_id} reset {option}")
        elif await aiopath.exists(path_dict[option]):
            buttons.data_button("Remove", f"userset {user_id} remove {option}")
    back_to = get_return_key(option)
    buttons.data_button("Back", f"userset {user_id} {back_to}", "footer")
    buttons.data_button("Close", f"userset {user_id} close", "footer")
    val = user_data.get(option)
    if option in path_dict and await aiopath.exists(path_dict[option]):
        val = "<b>Exists</b>"
    elif option == "LEECH_SPLIT_SIZE":
        val = get_readable_file_size(val)
    elif option == "METADATA":
        current_meta_val = user_data.get(option)
        if isinstance(current_meta_val, dict) and current_meta_val:
            val = ", ".join(
                f"{k}={escape(str(v))}" for k, v in current_meta_val.items()
            )
            val = f"<code>{val}</code>"
        elif isinstance(current_meta_val, str) and current_meta_val:
            val = (
                f"<code>{escape(current_meta_val)}</code> [<i>Legacy, needs re-set</i>]"
            )
        elif not current_meta_val:
            val = "<b>Not Set</b>"

        if val is None:
            val = "<b>Not Exists</b>"

    if option == "METADATA":
        text = f"""⌬ <b><u>Menu Settings :</u></b>


╭ <b>Option</b>: {option}
┊
┊ <b>Option's Value</b>: {val if val else "<b>Not Exists</b>"}
┊
┊ <b>Default Input Type</b>: {user_settings_text[option][0]}
┊ <b>Description</b>: {user_settings_text[option][1]}
┊
┊ <b>Dynamic Variables:</b>
┊ • <code>{{filename}}</code> - Full filename
┊ • <code>{{basename}}</code> - Filename without extension  
┊ • <code>{{extension}}</code> - File extension
┊
┊ • <code>{{audiolang}}</code> - Audio language
╰ • <code>{{sublang}}</code> - Subtitle language
"""
    else:
        text = f"""⌬ <b><u>Menu Settings :</u></b>
│
╭ <b>Option</b>: {option}
┊
┊ <b>Option's Value</b>: {val if val else "<b>Not Exists</b>"}
┊
┊ <b>Default Input Type</b>: {user_settings_text[option][0]}
╰ <b>Description</b>: {user_settings_text[option][1]}
"""
    await edit_message(message, text, buttons.build_menu(2))

async def event_handler(client, query, pfunc, rfunc, type="text"):
    target_user_id = query.from_user.id
    handler_dict[target_user_id] = True
    start_time = update_time = time()
    
    async def event_filter(_, __, event):
        if type == 'photo':
            mtype = event.photo or event.document
        elif type == 'document':
            mtype = event.document
        elif type == 'video':
            mtype = event.video
        else:
            mtype = event.text

        ev_user = event.from_user or event.sender_chat
        if not ev_user:
            return False

        return (
            ev_user.id == target_user_id
            and event.chat.id == query.message.chat.id
            and bool(mtype)
        )

    handler = client.add_handler(
        MessageHandler(pfunc, filters=create(event_filter)), group=-1
    )

    while handler_dict[target_user_id]:
        await sleep(0.5)
        if time() - start_time > TIMEOUT:
            handler_dict[target_user_id] = False
            await rfunc()
        
    client.remove_handler(*handler)

@new_task
async def get_users_settings(_, message):
    msg = ""
    if auth_chats:
        msg += f"AUTHORIZED_CHATS: {auth_chats}\n"
    if sudo_users:
        msg += f"SUDO_USERS: {sudo_users}\n\n"
    if user_dict:
        for u, d in user_dict.items():
            kmsg = f"\n<b>{u}:</b>\n"
            if vmsg := "".join(
                f"{k}: <code>{v or None}</code>\n" for k, v in d.items()
            ):
                msg += kmsg + vmsg
        if not msg:
            await send_message(message, "No users data!")
            return
        msg_ecd = msg.encode()
        if len(msg_ecd) > 4000:
            with BytesIO(msg_ecd) as ofile:
                ofile.name = "users_settings.txt"
                await send_file(message, ofile)
        else:
            await send_message(message, msg)
    else:
        await send_message(message, "No users data!")
