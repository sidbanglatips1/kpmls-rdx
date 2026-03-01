import re
import unicodedata
from os import path as ospath

from bot import logger
from bot.helper.utils import MediaInfo

def extract_filename(text):
    exts = r"(?:mkv|mp4|mov|avi|m4v|webm|flv|wmv)"
    matches = re.findall(rf'(?i)\S.*?\.{exts}', text)
    return max(matches, key=len).strip() if matches else ""
    
def sanitize_filename(name, clean=False, default_extension=""):
    if not name:
        return "default_filename" + default_extension
    
    # Clean first if requested
    if clean:
        name = clean_name(name, remove_emoji=False)
    
    # Extract first line as filename (most captions have filename on first line)
    lines = [line.strip() for line in name.splitlines() if line.strip()]
    if not lines:
        return "default_filename" + default_extension
    
    # Get the first non-empty line as the filename
    filename_line = lines[0]
    
    # Extract extension from the first line
    base, ext = ospath.splitext(filename_line)
    base = base.strip()
    
    # If no extension in first line, search other lines for extension
    if not ext or len(ext) > 5:
        for line in lines[1:]:
            _, line_ext = ospath.splitext(line)
            if line_ext and len(line_ext) <= 5:
                ext = line_ext
                break
    
    # Clean the base name
    # Remove HTML/XML tags
    base = re.sub(r'<[^>]+>', '', base)
    
    # Remove Markdown links [text](url) -> text
    base = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', base)
    
    # Remove illegal filename characters for Windows/Unix
    base = re.sub(r'[<>:"|?*\0/\\]', '', base)
    
    # Normalize multiple spaces/tabs to single space
    base = re.sub(r'\s+', ' ', base).strip()
    
    # Remove trailing dots and spaces (Windows compatibility)
    base = base.rstrip('. ')
    
    # Remove leading dots (hidden files on Unix)
    base = base.lstrip('.')
    
    # Limit filename length (255 is typical max, leave room for extension)
    max_length = 250
    if len(base) > max_length:
        base = base[:max_length].rstrip('. ')
    
    # Use default extension if none found
    if not ext:
        ext = default_extension
    
    # Fallback to default if base is empty after cleaning
    if not base:
        base = "default_filename"
    
    return base + ext

def clean_name(filename, remove_emoji=True):
    if not isinstance(filename, str) or not filename:
        return ""

    original = filename.strip()

    if '.' in original:
        name_part, ext = original.rsplit('.', 1)
        ext = '.' + ext
    else:
        name_part = original
        ext = ''

    def remove_emojis(text):
        try:
            text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        except Exception:
            return text
        return text

    if remove_emoji:
        name_part = remove_emojis(name_part)

    patterns_to_remove = [
        r'@\w+',
        r'https?://\S+|t\.me/\S+|www\.\S+',
        r'#\w+',
        r'\b(?:HDHub4u|MoviesVerse|FilmyZilla|KatMovieHD|Worldfree4u|9xmovies|ExtraFlix|PrimeFix|mkvCinemas|Pw|Toonworld4all)\b',
    ]
    combined_pattern = '|'.join(f'(?:{p})' for p in patterns_to_remove)
    name_part = re.sub(combined_pattern, '', name_part, flags=re.IGNORECASE)

    name_part = name_part.replace('_', ' ')
    name_part = name_part.replace('+', ' ')
    name_part = re.sub(r'\.+', ' ', name_part)

    name_part = re.sub(r'[\[\]\(\)\{\}]', '', name_part)
    name_part = re.sub(r'\s+', ' ', name_part).strip()

    if not name_part:
        return original

    return f"{name_part}{ext}"


def fetch_extra_info(filename):
    if not filename:
        return MediaInfo(AutoRename=False, Name='', Year='', Quality='', Season='', Start_Episode='', End_Episode='', Part='', Audio='', Lib='', Ott='', Resolution='', Languages='', Subtitle='')
    filename = re.sub(r'[\_\s+\(\)]', ' ', filename)
    file_name = clean_name(filename)
    
    # Audio Match
    audio_pattern = re.compile(
    r'\b(?:AAC|DD|DDP|Opus|AC3)\s?(?:\d{1,2}(?:\.\d+)?)?(?:\s?Atmos)?\b|\b(?:\d+CH)\b',
    re.IGNORECASE
    )
    part_pattern = re.compile(r'\.part(\d{1,3})\b', re.IGNORECASE)
    # RESOLUTION MATCH
    resolutions = [r'\b360p\b', r'\b480p\b', r'\b720p\b', r'\b1080p\b', r'\b4K\b', r'\b2K\b', r'\b144p\b', r'\b240p\b', r'\b2160p\b', r'\b576p']
    resolution_patterns = [re.compile(r, re.IGNORECASE) for r in resolutions]
    detected_resolutions = []
    for pattern, original in zip(resolution_patterns, resolutions):
        if pattern.search(file_name):
            cleaned_original = original.replace(r'\b', '')
            detected_resolutions.append(cleaned_original)
    Resolution = ' '.join(detected_resolutions)
    
    filename = filename.replace('_', '.')
    audio_match = audio_pattern.findall(filename)
    Audio = ' '.join(audio_match) if audio_match else ' AAC'
    
    # LANGUAGES MATCH 
    languages = ['Hindi', 'English', 'Tamil', 'Telugu', 'Malayalam', 'Kannada', 'Marathi', 'Bengali', 'Gujarati', 'Bhojpuri', 'Odia', 'Spanish', 'French', 'German', 'Chinese', 'Japanese', 'Korean', 'Italian', 'Portuguese', 'Russian']   
    language_patterns = [re.compile(r'\b' + re.escape(lang) + r'\b', re.IGNORECASE) for lang in languages]
    Languages = [original for pattern, original in zip(language_patterns, languages) if pattern.search(file_name)]
    
    year_pattern = r'\b(19[0-9]{2}|20[0-9]{2})\b'
    lib_pattern = re.compile(r'(x264|x265)', re.IGNORECASE)
    # Part Match
    Part = ''
    if part_match := part_pattern.search(file_name):
        Part = part_match.group(1) 
    
    Season, Start_Episode, End_Episode = extract_season_episode_func(file_name)
    
    # Year Match
    year_match = re.search(year_pattern, file_name)
    Year = f"{int(year_match.group(1))}" if year_match else ''
    # Quality Match
    qualities = [
        'SDTV-Rip', 'HDTV-Rip', 'SDTV', 'HDTV', 'SDTVRip', 'HDTVRip', 'DVDScr', 
        'PRE-HD', 'WEBDL', 'WEB-DL', 'WEB DL', 'WEBRip', 'BluRay', 'HDRip', 
        'PreDVD', 'DVDRip', 'YTRip', 'HDTS', 'HDTC', 'CAMRip', 'HQSprint', 
        'HDCAM', 'HDCAMRip', 'TELESYNC', 'TSQRip', 'BRRip', 'HQ SPrint', 'HDTVRip'
    ]
    quality_patterns = [re.compile(r'\b' + re.escape(quality) + r'\b', re.IGNORECASE) for quality in qualities]
    Quality = ''
    for pattern, original in zip(quality_patterns, qualities):
        if pattern.search(file_name):
            Quality = original
            break
    # OTT MATCH
    ott_platforms = [
        'NF', 'AMZN', 'HBO', 'JioHotstar', 'JioHS', 'JHS', 'DSNP', 'HS', 'CR', 'JC', 'Jio', 
        'PF', 'VOD', 'BMS', 'CRAV', 'MX', 'ATVP', 'MAX', 'PCOK', 'SONYLiv', 
        'ZEE5', 'SS', 'APLVTV', 'HULU', 'APL', 'YT', 'STZ', 'STARZ', 'PS', 'AHA'
    ]
    
    ott_patterns = [re.compile(r'\b' + re.escape(platform) + r'\b(?=\s|$)', re.IGNORECASE) for platform in ott_platforms]
    Ott = ''
    for pattern, original in zip(ott_patterns, ott_platforms):
        if pattern.search(file_name) and Quality.lower().strip() != 'bluray':
            Ott = original
            break

    # Subtitle Match 
    subtitle_pattern = r"\b(?:HC-)?(?:[A-Za-z]{1,2}-)?[EeMm]sub\b"
    subtitle_match = re.search(subtitle_pattern, file_name, re.IGNORECASE)
    Subtitle = f" {subtitle_match.group(0)}" if subtitle_match else ''
    #  Lib Match
    lib_pattern = re.compile(r'(x264|x265|H\.264|H\.265)', re.IGNORECASE)
    if lib_match := lib_pattern.search(file_name):
       codec = lib_match.group(0).lower()
       Lib = "x265" if '265' in codec else "x264"
    else:
       Lib = ''
    # Name Match
    name_pattern = r'^(.*?)(?=\s*(?:S\d+E\d+|\d+p|\d{4}\b|$))'
    name_match = re.search(name_pattern, file_name)
    Name = f"{name_match.group(1).rstrip('. ')}" if name_match else f'{file_name}'

    name_pattern = r'^(.*?)(?=\s*(?:S\d+E\d+|S\d+|E\d+|\d{4}(?!\d)|\d+p|$))'
    name_match = re.search(name_pattern, file_name)
    Name = f"{name_match.group(1).rstrip('. ')}" if name_match else f'{file_name}'
    #logger.info(f"Name: {Name} \nYear: {Year}\nQuality: {Quality}\nSeason: {Season}\nEpisode: {Start_Episode}-{End_Episode}\nPart: {Part}\nAudio: {Audio}\nLib: {Lib}\nOtt: {Ott}")
    return MediaInfo(AutoRename=True, Name=Name, Year=Year, Quality=Quality, Season=Season, Start_Episode=Start_Episode, End_Episode=End_Episode, Part=Part, Audio=Audio, Lib=Lib, Ott=Ott, Resolution=Resolution, Languages=Languages, Subtitle=Subtitle)


def extract_season_episode_func(filename):
    file_name = clean_name(filename)
    Season = Start_Episode = End_Episode = ''

    # Primary regex: SxxExx, SxxExx-Exx, SxxExx.Eyy, SxxExx_Eyy
    combined_match = re.search(r'\bS(\d{1,2})E(\d{1,3})(?:[-._]E?(\d{1,3}))?\b', file_name, flags=re.IGNORECASE)
    if combined_match:
        Season = f"S{int(combined_match.group(1)):02d}"
        Start_Episode = f"E{int(combined_match.group(2)):02d}"
        if combined_match.group(3):
            End_Episode = f"E{int(combined_match.group(3)):02d}"
        return Season, Start_Episode, End_Episode

    # Fallback for separate season and episode
    season_match = re.search(r'\b(?:S|Season)\s*(\d{1,2})\b', file_name, flags=re.IGNORECASE)
    if season_match:
        Season = f"S{int(season_match.group(1)):02d}"

    ep_pattern = re.compile(
        r'\b(?:E|EP|Episode)\s*(\d{1,3})'
        r'(?:\s*(?:to|-|T|\.|_)\s*(?:E)?(\d{1,3}))?'
        r'|E(\d{1,3})E(\d{1,3})\b',  # Handle ExxEyy pattern
        flags=re.IGNORECASE
    )

    ep_match = ep_pattern.search(file_name)
    if ep_match:
        if ep_match.group(1):  # Standard episode or range
            Start_Episode = f"E{int(ep_match.group(1)):02d}"
            if ep_match.group(2):
                End_Episode = f"E{int(ep_match.group(2)):02d}"
        elif ep_match.group(3):  # ExxEyy pattern
            Start_Episode = f"E{int(ep_match.group(3)):02d}"
            End_Episode = f"E{int(ep_match.group(4)):02d}"

    return Season, Start_Episode, End_Episode

