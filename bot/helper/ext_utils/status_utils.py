def get_readable_file_size(size):
    if size is None:
        return "0B"
    power = 2**10
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size >= power and n < 4:
        size /= power
        n += 1
    return f"{round(size, 2)} {power_labels[n]}B"
