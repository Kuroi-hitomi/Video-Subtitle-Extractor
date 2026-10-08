"""Local MP4 speech recognition and subtitle export. Python 3.10+."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from speaker_tools import (SpeakerAssigner, default_colors, diarize, parse_speaker_count,
                           read_colors, require_backend, to_ass, validate_colors)


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str
    speaker: str | None = None


def cue_text(cue):
    prefix = f"[Sound {cue.speaker}] " if cue.speaker is not None else ""
    return prefix + cue.text.strip()


def timestamp(seconds: float, separator: str = ",") -> str:
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Time must be a finite, non-negative number")
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}{separator}{milliseconds:03}"


def validate(cues):
    previous_end = 0
    for cue in cues:
        if (not math.isfinite(cue.start) or not math.isfinite(cue.end)
                or cue.start < 0 or round(cue.end * 1000) <= round(cue.start * 1000)):
            raise ValueError("Each subtitle must end at least 1 millisecond after it starts")
        if round(cue.start * 1000) < round(previous_end * 1000):
            raise ValueError("Subtitle cues must be chronological and must not overlap")
        if not cue.text.strip():
            raise ValueError("Subtitle text must not be empty")
        if cue.speaker is not None and not re.fullmatch(r"[A-Z]|\?", cue.speaker):
            raise ValueError("Speaker labels must be A–Z or ?")
        previous_end = cue.end


def to_srt(cues) -> str:
    validate(cues)
    return "\n\n".join(
        f"{i}\n{timestamp(c.start)} --> {timestamp(c.end)}\n{cue_text(c)}"
        for i, c in enumerate(cues, 1)
    ) + ("\n" if cues else "")


def to_txt(cues) -> str:
    validate(cues)
    return "".join(
        f"[{timestamp(c.start, '.')} → {timestamp(c.end, '.')}] {cue_text(c).replace(chr(10), ' ')}\n"
        for c in cues
    )


def parse_srt(content: str) -> list[Cue]:
    content = content.lstrip("\ufeff").replace("\r\n", "\n").strip()
    if not content:
        raise ValueError("The subtitles are empty")
    time_pattern = r"(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})"
    timing = re.compile(rf"^{time_pattern}\s+-->\s+{time_pattern}$")
    cues = []
    for block in re.split(r"\n\s*\n", content):
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].strip().isdigit():
            raise ValueError("Each SRT cue needs an index, a timestamp line, and text, with a blank line between cues")
        match = timing.fullmatch(lines[1].strip())
        if not match:
            raise ValueError(f"Invalid timestamp format: {lines[1]}")
        values = list(map(int, match.groups()))
        def seconds(v):
            return v[0] * 3600 + v[1] * 60 + v[2] + v[3] / 1000
        text = "\n".join(lines[2:]).strip()
        speaker = None
        label = re.match(r"^\[Sound ([A-Z]|\?)\]\s*", text)
        if label:
            speaker, text = label.group(1), text[label.end():]
        elif text.startswith("[Sound "):
            raise ValueError("Invalid speaker label. Use [Sound A] through [Sound Z], or [Sound ?]")
        cues.append(Cue(seconds(values[:4]), seconds(values[4:]), text, speaker))
    validate(cues)
    return cues


def make_cues(segments, max_chars=32, max_seconds=6.0, speaker_for=None) -> list[Cue]:
    """Split at model word boundaries, pauses and punctuation, keeping real timing."""
    cues = []
    for segment in segments:
        words = getattr(segment, "words", None)
        if not words:
            speaker = speaker_for(segment.start, segment.end) if speaker_for else None
            candidates = [Cue(segment.start, segment.end, segment.text.strip(), speaker)]
        else:
            candidates, group = [], []
            group_speaker = None
            def flush():
                if group:
                    candidates.append(Cue(group[0].start, group[-1].end,
                                          "".join(w.word for w in group).strip(), group_speaker))
                    group.clear()
            for word in words:
                speaker = speaker_for(word.start, word.end) if speaker_for else None
                if group and (speaker != group_speaker
                              or len("".join(w.word for w in group) + word.word) > max_chars
                              or word.end - group[0].start > max_seconds
                              or word.start - group[-1].end > 0.65):
                    flush()
                group_speaker = speaker
                group.append(word)
                if re.search(r"[。！？!?；;.]\s*$", word.word):
                    flush()
            flush()
        for cue in candidates:
            # Quantize once and eliminate overlapping / zero-duration model output.
            start = max(round(cue.start * 1000) / 1000, cues[-1].end if cues else 0)
            end = round(cue.end * 1000) / 1000
            if cue.text and end > start:
                cues.append(Cue(start, end, cue.text, cue.speaker))
            elif cue.text and cues:
                last = cues[-1]
                speaker = last.speaker if last.speaker == cue.speaker else "?"
                cues[-1] = Cue(last.start, last.end, last.text + " " + cue.text, speaker)
    return cues


def recognize(video: Path, model_name="small", language="zh", device="cpu",
              report=lambda message: None, num_speakers=None) -> list[Cue]:
    num_speakers = parse_speaker_count(num_speakers)
    if num_speakers and num_speakers > 1:
        require_backend()
    video = Path(video).resolve()
    if not video.is_file():
        raise ValueError("The video file does not exist")
    try:
        import av
        from faster_whisper import WhisperModel
        from faster_whisper.audio import decode_audio
    except ImportError as exc:
        raise RuntimeError("Missing transcription dependencies. Check the configured runtime (runtime.json, or .venv if absent)") from exc
    report("Checking the audio track and reading the video…")
    try:
        with av.open(str(video)) as container:
            if not container.streams.audio:
                raise ValueError("The video has no audio track to transcribe")
            # Preserve a common initial audio offset relative to the video timeline.
            stream = container.streams.audio[0]
            audio_start = float(stream.start_time * stream.time_base) if stream.start_time is not None else 0
            origin = container.start_time / av.time_base if container.start_time is not None else 0
            offset = audio_start - origin
        audio = decode_audio(str(video), sampling_rate=16000)
    except ValueError:
        raise
    except TypeError as exc:
        if "metadata_errors" in str(exc) and "unexpected keyword argument" in str(exc):
            raise RuntimeError(
                "The audio decoder dependencies are incompatible; the video location is not the cause.\n"
                "Check that the runtime uses a PyAV version satisfying av>=11,<19.\n"
                "This faster-whisper version uses the metadata_errors argument removed in PyAV 19."
            ) from exc
        raise RuntimeError(f"Could not read the video audio track: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Could not read the video audio track: {exc}") from exc
    if len(audio) == 0:
        raise ValueError("The audio track is empty")
    if abs(offset) >= 0.05:
        report(f"Audio starts at an offset of {offset:.3f} seconds. Subtitle timing will be adjusted; check synchronization after export.")
    speaker_for = SpeakerAssigner(diarize(audio, num_speakers, report)) if num_speakers else None
    report("Loading the model (the first use downloads it and may take several minutes)…")
    model = WhisperModel(model_name, device=device,
                         compute_type="int8" if device == "cpu" else "float16",
                         download_root=str(Path(__file__).resolve().parent / "models"))
    report("Transcribing, please wait…")
    segments, info = model.transcribe(
        audio, language=None if language == "auto" else language,
        task="transcribe", beam_size=5, word_timestamps=True,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
    )
    report(f"Language: {info.language}; audio duration: approximately {len(audio) / 16000:.1f} seconds")
    def tracked():
        for segment in segments:
            report(f"Transcribed through {timestamp(max(0, segment.end + offset), '.')}: {segment.text.strip()}")
            yield segment
    cues = make_cues(tracked(), speaker_for=speaker_for)
    cues = [Cue(max(0, c.start + offset), c.end + offset, c.text, c.speaker)
            for c in cues if c.end + offset > max(0, c.start + offset)]
    if not cues:
        raise ValueError("No usable speech was detected. Check that the video contains audible speech.")
    validate(cues)
    if num_speakers:
        unknown = sum(c.speaker == "?" for c in cues)
        if unknown:
            report(f"{unknown} cues could not be assigned confidently and are labeled [Sound ?] (white). Review them in the editor.")
    return cues


def save_result(video: Path, destination: Path, cues, colors=None) -> Path:
    """Use a new folder for each run, so an earlier transcript is never overwritten."""
    validate(cues)
    colors = validate_colors(colors or {})
    # Serialize before making the output directory so invalid inputs leave no partial result.
    ass = to_ass(cues, colors) if any(c.speaker is not None for c in cues) else None
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=f"{Path(video).stem}_{datetime.now():%Y%m%d_%H%M%S}_",
                                   dir=destination))
    (folder / "subtitles.srt").write_text(to_srt(cues), encoding="utf-8-sig")
    (folder / "transcript.txt").write_text(to_txt(cues), encoding="utf-8-sig")
    if ass is not None:
        (folder / "subtitles.ass").write_text(ass, encoding="utf-8-sig")
        used_colors = dict(colors)
        for cue in cues:
            if cue.speaker is not None:
                used_colors.setdefault(cue.speaker, "#FFFFFF" if cue.speaker == "?" else default_colors(26)[cue.speaker])
        (folder / "speakers.json").write_text(json.dumps({"version": 1, "colors": used_colors},
                                                        ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


def export_video(video: Path, srt: Path, output: Path, mode="soft", colors=None):
    if mode not in {"soft", "hard", "soft-color"}:
        raise ValueError("Subtitle mode must be soft, hard, or soft-color")
    video, srt, output = (Path(p).resolve() for p in (video, srt, output))
    if not video.is_file() or not srt.is_file():
        raise ValueError("The video or subtitle file does not exist")
    cues = parse_srt(srt.read_text(encoding="utf-8-sig"))
    has_speakers = any(c.speaker is not None for c in cues)
    if colors is None and has_speakers and (srt.parent / "speakers.json").is_file():
        colors = read_colors(srt.parent / "speakers.json")
    colors = validate_colors(colors or {})
    if mode == "soft" and has_speakers:
        raise ValueError("Plain MP4 soft subtitles cannot reliably retain speaker colors. Choose burned-in MP4 or color soft subtitles in MKV")
    if output.exists():
        raise ValueError("The output file already exists. Choose a new filename")
    extension = ".mkv" if mode == "soft-color" else ".mp4"
    if output.suffix.lower() != extension:
        raise ValueError(f"This export mode requires the {extension} file extension")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            pass
    if not ffmpeg:
        raise RuntimeError("Video export requires FFmpeg. Check the imageio-ffmpeg installation or add FFmpeg to PATH.")
    output.parent.mkdir(parents=True, exist_ok=True)
    # ASCII relative filename avoids FFmpeg filter escaping issues on Windows.
    with tempfile.TemporaryDirectory(prefix="subtitle_export_") as temporary:
        shutil.copyfile(srt, Path(temporary) / "captions.srt")
        if has_speakers or mode == "soft-color":
            (Path(temporary) / "captions.ass").write_text(to_ass(cues, colors), encoding="utf-8-sig")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(video)]
        if mode == "soft":
            command += ["-i", "captions.srt", "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
                        "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text", "-disposition:s:0", "default"]
        elif mode == "soft-color":
            command += ["-i", "captions.ass", "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
                        "-c:v", "copy", "-c:a", "copy", "-c:s", "ass", "-disposition:s:0", "default"]
        else:
            subtitle_filter = ("subtitles=filename=captions.ass" if has_speakers else
                               "subtitles=filename=captions.srt:force_style='FontName=Microsoft YaHei,FontSize=22,Outline=1,MarginV=24'")
            command += ["-map", "0:v:0", "-map", "0:a?", "-vf",
                        subtitle_filter,
                        "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "copy"]
        if extension == ".mp4":
            command += ["-movflags", "+faststart"]
        command += [str(output)]
        result = subprocess.run(command, cwd=temporary, capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name == 'nt' else 0)
        if result.returncode:
            raise RuntimeError("Video export failed (an incomplete output file may remain):\n" + result.stderr[-3000:])


def main():
    # Use UTF-8 for redirected output, including multilingual transcripts.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Transcribe MP4 speech into TXT and SRT subtitles")
    commands = parser.add_subparsers(dest="command", required=True)
    transcribe = commands.add_parser("transcribe")
    transcribe.add_argument("video", type=Path)
    transcribe.add_argument("--out", type=Path, default=Path("results"))
    transcribe.add_argument("--model", default="small", help="Model name or local model directory")
    transcribe.add_argument("--language", default="zh", help="zh, en, or auto")
    transcribe.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    transcribe.add_argument("--speakers", type=int, default=None, help="Optional speaker count, 1–26; omit to disable speaker labels")
    transcribe.add_argument("--colors", type=Path, help="Optional JSON file mapping speaker labels (A, B, etc.) to #RRGGBB colors")
    export = commands.add_parser("export")
    export.add_argument("video", type=Path)
    export.add_argument("srt", type=Path)
    export.add_argument("output", type=Path)
    export.add_argument("--mode", choices=["soft", "hard", "soft-color"], default="soft")
    export.add_argument("--colors", type=Path, help="Optional color JSON; defaults to speakers.json beside the SRT file")
    args = parser.parse_args()
    try:
        if args.command == "transcribe":
            colors = read_colors(args.colors) if args.colors else None
            cues = recognize(args.video, args.model, args.language, args.device, print, args.speakers)
            print("Saved to:", save_result(args.video, args.out, cues, colors))
        else:
            export_video(args.video, args.srt, args.output, args.mode,
                         read_colors(args.colors) if args.colors else None)
            print("Exported to:", args.output)
    except Exception as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
