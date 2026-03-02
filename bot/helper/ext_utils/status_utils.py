def get_readable_file_size(size):
    if size is None:
        return "0B"
    power = 2**10
    n = 0
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    while size >= power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{round(size, 2)} {units[n]}"
