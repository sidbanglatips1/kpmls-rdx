from os import path as os_path
import logging
from re import sub as re_sub
from aioshutil import move
from asyncio import create_subprocess_exec
from asyncio.subprocess import PIPE
from bot import LOGGER, bot_cache
from bot.helper.ext_utils.fs_utils import clean_target

LOGGER = logging.getLogger(__name__)

# ================== AUTO SCREENSHOT / THUMBNAIL ==================
async def take_ss(video: str, duration: int | None = None):
    """
    Generate thumbnail screenshot from video (kpmls safe version)
    """
    try:
        if not os_path.exists(video):
            return None

        output = f"{os_path.splitext(video)[0]}.jpg"

        # middle frame logic (better real thumb)
        if duration and isinstance(duration, (int, float)) and duration > 0:
            ss_time = int(duration // 2)
        else:
            ss_time = 10  # fallback 10s

        cmd = [
            bot_cache['pkgs'][2],  # ffmpeg path from bot_cache
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(ss_time),
            "-i", video,
            "-frames:v", "1",
            "-q:v", "2",
            output
        ]

        process = await create_subprocess_exec(*cmd, stderr=PIPE)
        await process.wait()

        if os_path.exists(output):
            return output
        return None

    except Exception as e:
        LOGGER.error(f"Thumbnail Screenshot Error: {e}")
        return None


########-------- Metadata -------------#########
async def edit_metadata(listener, base_dir: str, media_file: str, outfile: str, metadata: str = ''):
    file_name = os_path.basename(media_file)
    basename = os_path.splitext(file_name)[0]
    basenameX = re_sub(r'www\S+', '', basename)
    basenameX = re_sub(r'(^\s*-\s*|(\s*-\s*){2,})', '', basenameX)

    file_ext = os_path.splitext(file_name)[-1].lower()
    if file_ext != '.mkv':
        return

    if basename.strip().lower().startswith("www"):
        title_metadata = f"{metadata} - {basenameX}"
    elif basename.strip().lower().startswith("@"):
        title_metadata = f"{basenameX}"
    else:
        title_metadata = metadata

    cmd = [
        bot_cache['pkgs'][2], '-i', media_file,
        '-map', '0',
        '-metadata', f'title={title_metadata}',
        '-metadata:s:v', f'title={metadata}',
        '-metadata:s:a', f'title={metadata}',
        '-metadata:s:s', f'title={metadata}',
        '-c', 'copy',
        outfile
    ]

    listener.suproc = await create_subprocess_exec(*cmd, stderr=PIPE)
    code = await listener.suproc.wait()

    if code == 0:
        await clean_target(media_file)
        listener.seed = False
        await move(outfile, base_dir)
    else:
        await clean_target(outfile)
        err = await listener.suproc.stderr.read()
        LOGGER.error('%s. Changing metadata failed, Path %s', err.decode(), media_file)


########-------- Attachment -------------#########
async def edit_attachment(listener, base_dir: str, media_file: str, outfile: str, attachment: str = ''):
    file_name = os_path.basename(media_file)
    file_ext = os_path.splitext(file_name)[-1].lower()

    if file_ext != '.mkv':
        return

    omg = "photo"
    attachment_ext = attachment.split(".")[-1].lower()
    mime_type = "application/octet-stream"

    if attachment_ext in ["jpg", "jpeg"]:
        mime_type = "image/jpeg"
    elif attachment_ext == "png":
        mime_type = "image/png"

    cmd = [
        bot_cache['pkgs'][2],
        '-hide_banner', '-loglevel', 'error', '-progress', 'pipe:1',
        '-i', media_file,
        '-attach', attachment,
        '-metadata:s:t', f'mimetype={mime_type}',
        '-metadata:s:t', f'filename={omg}.{attachment_ext}',
        '-disposition:t', 'default',
        '-c', 'copy',
        '-map', '0',
        '-map', '0:t?',
        outfile
    ]

    listener.suproc = await create_subprocess_exec(*cmd, stderr=PIPE)
    code = await listener.suproc.wait()

    if code == 0:
        await clean_target(media_file)
        listener.seed = False
        await move(outfile, base_dir)
    else:
        await clean_target(outfile)
        err = await listener.suproc.stderr.read()
        LOGGER.error('%s. Changing attachment failed, Path %s', err.decode(), media_file)
