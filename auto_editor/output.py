from __future__ import annotations

import os.path
from dataclasses import dataclass
from fractions import Fraction

from auto_editor.ffwrapper import FFmpeg, FileInfo
from auto_editor.timeline import v3
from auto_editor.utils.container import Container
from auto_editor.utils.func import append_filename
from auto_editor.utils.log import Log
from auto_editor.utils.types import Args


@dataclass(slots=True)
class Ensure:
    _ffmpeg: FFmpeg
    _sr: int
    temp: str
    log: Log

    def audio(self, path: str, label: str, stream: int) -> str:
        out_path = os.path.join(self.temp, f"{label}-{stream}.wav")

        if not os.path.isfile(out_path):
            self.log.conwrite("Extracting audio")

            cmd = ["-i", path, "-map", f"0:a:{stream}"]
            cmd += ["-ac", "2", "-ar", f"{self._sr}", "-rf64", "always", out_path]
            self._ffmpeg.run(cmd)

        return out_path

    def subtitle(self, path: str, label: str, stream: int) -> str:
        out_path = os.path.join(self.temp, f"{label}-{stream}.vtt")

        if not os.path.isfile(out_path):
            self.log.conwrite("Extracting subtitle")

            cmd = ["-i", path, "-map", f"0:s:{stream}", out_path]
            self._ffmpeg.run(cmd)

        return out_path


def _ffset(option: str, value: str | None) -> list[str]:
    if value is None or value == "unset" or value == "reserved":
        return []
    return [option] + [value]


def video_quality(args: Args, ctr: Container) -> list[str]:
    return (
        _ffset("-b:v", args.video_bitrate)
        + ["-c:v", args.video_codec]
        + _ffset("-qscale:v", args.video_quality_scale)
        + ["-movflags", "faststart"]
    )


def lossless_trim_media(
    ffmpeg: FFmpeg,
    output: str,
    tl: v3,
    src: FileInfo,
    log: Log,
) -> None:
        tb = tl.tb
        clip_num = 0

        if len(tl.v) == 0:
            log.error(f"No clips found")

        for v_seg in tl.v[0]:
            start_frame = v_seg.offset
            dur_frame = v_seg.dur

            start_time = start_frame / (tb.numerator / tb.denominator)
            dur_time = dur_frame / (tb.numerator / tb.denominator)

            log.debug(f"clip {clip_num} start {start_time} dur {dur_time}")

            cmd = [
                "-hide_banner", "-ss", f"{start_time}",
                "-i", f"{src.path}",
                "-t",  f"{dur_time}",
                "-avoid_negative_ts", "disabled",
            ]

            stream: int = 0

            for v_track in tl.v:
                v_stream = v_track[0].stream
                cmd.extend(["-map", f"0:{v_stream}"])
                cmd.extend([f"-c:{v_stream}", "copy"])
                cmd.extend([f"-tag:{v_stream}", "hvc1"])
                stream = v_stream

            for a_track in tl.a:
                a_stream = a_track[0].stream + stream + 1
                cmd.extend(["-map", f"0:{a_stream}"])
                cmd.extend([f"-c:{a_stream}", "copy"])

            cmd.extend([
                "-map_metadata", "0",
            ])

            output_ext = os.path.splitext(output)[1].replace(".", "")
            if output_ext.lower() == "mov":
                cmd.extend([
                    "-movflags", "use_metadata_tags",
                    "-movflags", "+faststart",
                ])

            cmd.extend([
                "-default_mode", "infer_no_subs",
                "-ignore_unknown", "-y",
            ])

            output_seg = output
            if len(tl.v[0]) > 1:
                output_seg = append_filename(output, f"-{clip_num}")
            cmd.append(output_seg)
            ffmpeg.run_check_errors(cmd, log, path=output_seg)

            clip_num += 1

def mux_quality_media(
    ffmpeg: FFmpeg,
    visual_output: list[tuple[bool, str]],
    audio_output: list[str],
    sub_output: list[str],
    apply_v: bool,
    ctr: Container,
    output_path: str,
    tb: Fraction,
    args: Args,
    src: FileInfo,
    temp: str,
    log: Log,
) -> None:
    v_tracks = len(visual_output)
    a_tracks = len(audio_output)
    s_tracks = len(sub_output)

    cmd = ["-hide_banner", "-y", "-i", f"{src.path}"]

    same_container = src.path.suffix == os.path.splitext(output_path)[1]

    for is_video, path in visual_output:
        if is_video or ctr.allow_image:
            cmd.extend(["-i", path])
        else:
            v_tracks -= 1

    if a_tracks > 0:
        if args.keep_tracks_separate and ctr.max_audios is None:
            for path in audio_output:
                cmd.extend(["-i", path])
        else:
            # Merge all the audio a_tracks into one.
            new_a_file = os.path.join(temp, "new_audio.wav")
            if a_tracks > 1:
                new_cmd = []
                for path in audio_output:
                    new_cmd.extend(["-i", path])
                new_cmd.extend(
                    [
                        "-filter_complex",
                        f"amix=inputs={a_tracks}:duration=longest",
                        "-ac",
                        "2",
                        new_a_file,
                    ]
                )
                ffmpeg.run(new_cmd)
                a_tracks = 1
            else:
                new_a_file = audio_output[0]
            cmd.extend(["-i", new_a_file])

    for subfile in sub_output:
        cmd.extend(["-i", subfile])

    for i in range(v_tracks + s_tracks + a_tracks):
        cmd.extend(["-map", f"{i+1}:0"])

    cmd.extend(["-map_metadata", "0"])

    track = 0
    for is_video, path in visual_output:
        if is_video:
            if apply_v:
                cmd += video_quality(args, ctr)
            else:
                # Real video is only allowed on track 0
                cmd += ["-c:v:0", "copy"]

            if float(tb).is_integer():
                cmd += ["-video_track_timescale", f"{tb}"]

        elif ctr.allow_image:
            ext = os.path.splitext(path)[1][1:]
            cmd += [f"-c:v:{track}", ext, f"-disposition:v:{track}", "attached_pic"]

        track += 1
    del track

    for i, vstream in enumerate(src.videos):
        if i > v_tracks:
            break
        if vstream.lang is not None:
            cmd.extend([f"-metadata:s:v:{i}", f"language={vstream.lang}"])
    for i, astream in enumerate(src.audios):
        if i > a_tracks:
            break
        if astream.lang is not None:
            cmd.extend([f"-metadata:s:a:{i}", f"language={astream.lang}"])
    for i, sstream in enumerate(src.subtitles):
        if i > s_tracks:
            break
        if sstream.lang is not None:
            cmd.extend([f"-metadata:s:s:{i}", f"language={sstream.lang}"])

    if s_tracks > 0:
        scodec = src.subtitles[0].codec
        if same_container:
            cmd.extend(["-c:s", scodec])
        elif ctr.scodecs is not None:
            if scodec not in ctr.scodecs:
                scodec = ctr.scodecs[0]
            cmd.extend(["-c:s", scodec])

    if a_tracks > 0:
        cmd += _ffset("-c:a", args.audio_codec) + _ffset("-b:a", args.audio_bitrate)

    if same_container and v_tracks > 0:
        cmd += (
            _ffset("-color_range", src.videos[0].color_range)
            + _ffset("-colorspace", src.videos[0].color_space)
            + _ffset("-color_primaries", src.videos[0].color_primaries)
            + _ffset("-color_trc", src.videos[0].color_transfer)
        )

    if args.extras is not None:
        cmd.extend(args.extras.split(" "))
    cmd.extend(["-strict", "-2"])  # Allow experimental codecs.
    cmd.extend(["-map", "0:t?"])  # Add input attachments to output.

    # This was causing a crash for 'example.mp4 multi-track.mov'
    # cmd.extend(["-map", "0:d?"])

    cmd.append(output_path)
    ffmpeg.run_check_errors(cmd, log, path=output_path)
