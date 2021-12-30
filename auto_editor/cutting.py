'''cutting.py'''

import numpy as np

from auto_editor.utils.types import split_num_str

def combine_audio_motion(audio_list, motion_list, based, log):
    # type: (np.ndarray, np.ndarray, str, Any) -> np.ndarray

    if(based == 'audio' or based == 'not_audio'):
        if(max(audio_list) == 0):
            log.error('There was no place where audio exceeded the threshold.')
    if(based == 'motion' or based == 'not_motion'):
        if(max(motion_list) == 0):
            log.error('There was no place where motion exceeded the threshold.')

    if(audio_list is not None and max(audio_list) == 0):
        log.warning('There was no place where audio exceeded the threshold.')
    if(motion_list is not None and max(motion_list) == 0):
        log.warning('There was no place where motion exceeded the threshold.')

    if(based == 'audio'):
        return audio_list

    if(based == 'motion'):
        return motion_list

    if(based == 'not_audio'):
        return np.invert(audio_list)

    if(based == 'not_motion'):
        return np.invert(motion_list)

    if(based == 'audio_and_motion'):
        return audio_list & motion_list

    if(based == 'audio_or_motion'):
        return audio_list | motion_list

    if(based == 'audio_xor_motion'):
        return np.bitwise_xor(audio_list, motion_list)

    if(based == 'audio_and_not_motion'):
        return audio_list & np.invert(motion_list)

    if(based == 'not_audio_and_motion'):
        return np.invert(audio_list) & motion_list

    if(based == 'not_audio_and_not_motion'):
        return np.invert(audio_list) & np.invert(motion_list)
    return None


def combine_segment(has_loud, segment, fps):
    for item in segment:
        start, end = item['segment']
        start = int(start * fps)
        end = int(end * fps)
        has_loud[start:end] = False
    return has_loud


def remove_small(has_loud, lim, replace, with_):
    # type: (np.ndarray, int, int, int) -> np.ndarray
    startP = 0
    active = False
    for j, item in enumerate(has_loud):
        if(item == replace):
            if(not active):
                startP = j
                active = True
            # Special case for end.
            if(j == len(has_loud) - 1):
                if(j - startP < lim):
                    has_loud[startP:j+1] = with_
        else:
            if(active):
                if(j - startP < lim):
                    has_loud[startP:j] = with_
                active = False
    return has_loud


def str_is_number(val):
    # type: (str) -> bool
    return val.replace('.', '', 1).replace('-', '', 1).isdigit()


def str_starts_with_number(val):
    # type: (str) -> bool
    if(val.startswith('-')):
        val = val[1:]
    val = val.replace('.', '', 1)
    return val[0].isdigit()


def set_range(has_loud, range_syntax, fps, with_, log):
    # type: (...) -> np.ndarray

    def replace_variables_to_values(item, fps, log):
        # type: (str, float | int, Any) -> int
        if(str_is_number(item)):
            return int(item)
        if(str_starts_with_number(item)):
            value, unit = split_num_str(item, log.error)
            if(unit in ['', 'f', 'frame', 'frames']):
                if(isinstance(value, float)):
                    log.error('float type cannot be used with frame unit')
                return value
            if(unit in ['s', 'sec', 'secs', 'second', 'seconds']):
                return round(value * fps)
            log.error('Unknown unit: {}'.format(unit))
        if(item == 'start'):
            return 0
        if(item == 'end'):
            return len(has_loud)
        log.error("variable '{}' not available.".format(item))

    def var_val_to_frames(val, fps, log):
        # type: (str, float | int, Any) -> int
        num = replace_variables_to_values(val, fps, log)
        if(num < 0):
            num += len(has_loud)
        return num

    for item in range_syntax:
        pair = []
        for val in item:
            pair.append(var_val_to_frames(val, fps, log))
        has_loud[pair[0]:pair[1]] = with_
    return has_loud


def seconds_to_frames(value, fps):
    # type: (int | str, float) -> int
    if(isinstance(value, str)):
        return int(float(value) * fps)
    return value

def cook(has_loud, min_clip, min_cut):
    # type: (np.ndarray, int, int) -> np.ndarray
    has_loud = remove_small(has_loud, min_clip, replace=1, with_=0)
    has_loud = remove_small(has_loud, min_cut, replace=0, with_=1)
    return has_loud


# Turn long silent/loud array to formatted chunk list.
# Example: [1, 1, 1, 0, 0] => [[0, 3, 1], [3, 5, 0]]
def chunkify(arr, arr_length=None):
    # type: (np.ndarray, int | None) -> list[tuple[float]]
    if(arr_length is None):
        arr_length = len(arr)

    chunks = []
    start = 0
    for j in range(1, arr_length):
        if(arr[j] != arr[j - 1]):
            chunks.append((start, j, arr[j - 1]))
            start = j
    chunks.append((start, arr_length, arr[j]))
    return chunks


# Turn chunk list into silent/loud like array.
# Example: [(0, 3, 1), (3, 5, 2)] => [1, 1, 1, 2, 2]

def chunks_to_has_loud(chunks):
    # type: (list[tuple[float]]) -> np.ndarray
    has_loud = np.zeros((chunks[-1][1]), dtype=float)

    for chunk in chunks:
        if(chunk[2] != 0):
            has_loud[chunk[0]:chunk[1]] = chunk[2]
    return has_loud


def apply_frame_margin(has_loud, has_loud_length, frame_margin):
    # type: (np.ndarray, int, int) -> np.ndarray
    new = np.zeros((has_loud_length), dtype=float)
    for i in range(has_loud_length):
        start = int(max(0, i - frame_margin))
        end = int(min(has_loud_length, i+1+frame_margin))
        new[i] = min(1, np.max(has_loud[start:end]))
    return new


def apply_mark_as(has_loud, has_loud_length, fps, args, log):
    # type: (...) -> np.ndarray
    if(args.mark_as_loud != []):
        has_loud = set_range(has_loud, args.mark_as_loud, fps, args.video_speed, log)

    if(args.mark_as_silent != []):
        has_loud = set_range(has_loud, args.mark_as_silent, fps, args.silent_speed, log)
    return has_loud


def apply_spacing_rules(speed_list, arr_length, min_clip, min_cut, fps, args, log):
    # type: (...) -> list[tuple[float]]

    speed_list[speed_list == 0] = args.silent_speed
    speed_list[speed_list == 1] = args.video_speed

    if(args.cut_out != []):
        speed_list = set_range(speed_list, args.cut_out, fps, 99999, log)

    if(args.add_in != []):
        speed_list = set_range(speed_list, args.add_in, fps, args.video_speed, log)

    if(args.set_speed_for_range != []):
        for item in args.set_speed_for_range:
            speed_list = set_range(speed_list, [item[1:]], fps, item[0], log)

    return chunkify(speed_list, arr_length)


def merge(start_list, end_list):
    # type: (np.ndarray, np.ndarray) -> np.ndarray
    merge = np.zeros((len(start_list)), dtype=np.bool_)

    startP = 0
    for item in start_list:
        if(item == True):
            where_list = np.where(end_list[startP:])[0]
            if(len(where_list) > 0):
                merge[startP:where_list[0]] = True
        startP += 1
    return merge

