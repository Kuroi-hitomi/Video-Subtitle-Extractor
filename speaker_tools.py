"""Optional local speaker diarization and ASS styling. No heavy imports at startup."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import time
import urllib.request

from runtime_config import speaker_model_root

PALETTE = ("#FF0000", "#0080FF", "#FFFF00", "#00DD88", "#FF66CC", "#FF9900",
           "#AA88FF", "#00DDFF")
MODEL_ROOT = speaker_model_root()
SEGMENT_DIR = "sherpa-onnx-pyannote-segmentation-3-0"
EMBEDDING = "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/"


def parse_speaker_count(value):
    if value is None or str(value).strip() == "":
        return None
    if not re.fullmatch(r"[0-9]+", str(value).strip()) or not 1 <= int(value) <= 26:
        raise ValueError("Leave the speaker count blank, or enter an integer from 1 to 26")
    return int(value)


def default_colors(count):
    return {chr(65 + i): PALETTE[i % len(PALETTE)] for i in range(count)}


def validate_colors(colors):
    if not isinstance(colors, dict):
        raise ValueError("The color configuration must be a JSON object")
    for speaker, color in colors.items():
        if not isinstance(speaker, str) or not re.fullmatch(r"[A-Z]|\?", speaker):
            raise ValueError("Speaker labels must be A–Z or ?")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError(f"The color for Sound {speaker} must use #RRGGBB format")
    return dict(colors)


def read_colors(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return validate_colors(data.get("colors", data))


def ass_color(color):
    validate_colors({"A": color})
    return f"&H00{color[5:7]}{color[3:5]}{color[1:3]}".upper()


def ass_time(seconds):
    ticks = max(0, round(seconds * 100))
    hours, ticks = divmod(ticks, 360000)
    minutes, ticks = divmod(ticks, 6000)
    secs, ticks = divmod(ticks, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{ticks:02}"


def to_ass(cues, colors=None):
    from subtitle_core import validate
    validate(cues)
    colors = validate_colors(colors or {})
    used = {c.speaker for c in cues if c.speaker is not None}
    styles = {"Default": "#FFFFFF"}
    for speaker in sorted(used):
        fallback = "#FFFFFF" if speaker == "?" else PALETTE[(ord(speaker) - 65) % len(PALETTE)]
        styles["Unknown" if speaker == "?" else f"Sound{speaker}"] = colors.get(speaker, fallback)
    header = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080",
              "WrapStyle: 0", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
              "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"]
    for name, color in styles.items():
        header.append(f"Style: {name},Microsoft YaHei,48,{ass_color(color)},&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,60,60,60,1")
    header += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for cue in cues:
        style = "Default" if cue.speaker is None else ("Unknown" if cue.speaker == "?" else f"Sound{cue.speaker}")
        # Render literal user text: prevent ASS override tags and escape sequences.
        # Speaker identity selects the color/style; it is not displayed in the video.
        text = cue.text.replace("\\", "＼").replace("{", "｛").replace("}", "｝")
        text = text.replace("\r", "").replace("\n", "\\N")
        start = round(cue.start * 100) / 100
        end = max(round(cue.end * 100) / 100, start + .01)
        header.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}")
    return "\n".join(header) + "\n"


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


class SpeakerAssigner:
    """Attribute each word by maximum overlap; leave ambiguous/no-match words unknown."""
    def __init__(self, turns):
        self.turns = sorted(turns, key=lambda t: (t.start, t.end, t.speaker))
        self.starts = [t.start for t in self.turns]
        self.prefix_end = []
        for turn in self.turns:
            self.prefix_end.append(max(turn.end, self.prefix_end[-1] if self.prefix_end else 0))

    def __call__(self, start, end):
        end = max(end, start + .001)
        left = bisect_right(self.prefix_end, start)
        right = bisect_left(self.starts, end)
        scores = {}
        for turn in self.turns[left:right]:
            overlap = min(end, turn.end) - max(start, turn.start)
            if overlap > 0:
                scores[turn.speaker] = scores.get(turn.speaker, 0) + overlap
        if not scores:
            return "?"
        ordered = sorted(scores, key=lambda key: (-scores[key], key))
        if len(ordered) > 1 and scores[ordered[1]] >= scores[ordered[0]] * .8:
            return "?"
        return ordered[0]


def require_backend():
    try:
        import sherpa_onnx
    except (ImportError, OSError) as exc:
        raise RuntimeError("Could not load the speaker backend. Check the configured runtime (runtime.json, or .venv if absent). This dependency is not needed when the speaker count is blank.") from exc
    required = ("OfflineSpeakerDiarizationConfig", "OfflineSpeakerDiarization",
                "OfflineSpeakerSegmentationModelConfig", "OfflineSpeakerSegmentationPyannoteModelConfig",
                "SpeakerEmbeddingExtractorConfig", "FastClusteringConfig")
    missing = [name for name in required if not hasattr(sherpa_onnx, name)]
    if missing:
        origin = getattr(sherpa_onnx, "__file__", None) or "No module entry file (the installation may be incomplete or inaccessible)"
        raise RuntimeError(
            "The speaker package is missing required interfaces. It may be incomplete or shadowed by a file with the same name.\n"
            "Check the configured runtime (runtime.json, or .venv if absent), then restart.\n"
            f"Module location: {origin}\nMissing interfaces: {', '.join(missing)}"
        )
    return sherpa_onnx


def download(url, destination, report):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as output:
        partial = Path(output.name)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "VideoSubtitle/2.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                received, last = 0, 0
                total = int(response.headers.get("Content-Length", 0))
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    received += len(chunk)
                    if time.monotonic() - last > 3:
                        report(f"Downloading {destination.name}: {received // 1048576} MB" +
                               (f" / {total // 1048576} MB" if total else ""))
                        last = time.monotonic()
                if received == 0 or (total and received != total):
                    raise RuntimeError("The download is incomplete")
            output.close()
            partial.replace(destination)
        finally:
            output.close()
            partial.unlink(missing_ok=True)


def ensure_models(report=print, root=MODEL_ROOT):
    root = Path(root)
    segmentation, embedding = root / SEGMENT_DIR / "model.onnx", root / EMBEDDING
    try:
        if not segmentation.is_file():
            root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=root) as temporary:
                archive = Path(temporary) / "segmentation.tar.bz2"
                download(RELEASES + "speaker-segmentation-models/" + SEGMENT_DIR + ".tar.bz2", archive, report)
                with tarfile.open(archive, "r:bz2") as bundle:
                    for name in ("LICENSE", "README.md", "model.onnx"):
                        member = bundle.getmember(SEGMENT_DIR + "/" + name)
                        if not member.isfile():
                            raise RuntimeError("The model archive contains an unexpected entry")
                        target = root / SEGMENT_DIR / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        staged = Path(temporary) / name
                        with bundle.extractfile(member) as source, staged.open("wb") as output:
                            shutil.copyfileobj(source, output)
                        staged.replace(target)
        if not embedding.is_file():
            download(RELEASES + "speaker-recongition-models/" + EMBEDDING, embedding, report)
    except Exception as exc:
        raise RuntimeError(f"Speaker model download failed: {exc}\nCheck access to GitHub downloads and retry. Your video is not uploaded.") from exc
    return segmentation, embedding


def create_engine(count, report=print):
    count = parse_speaker_count(count)
    if count is None:
        raise ValueError("Enter the speaker count")
    backend = require_backend()
    segmentation, embedding = ensure_models(report)
    config = backend.OfflineSpeakerDiarizationConfig(
        segmentation=backend.OfflineSpeakerSegmentationModelConfig(
            pyannote=backend.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation)),
            num_threads=2, provider="cpu"),
        embedding=backend.SpeakerEmbeddingExtractorConfig(model=str(embedding), num_threads=2, provider="cpu"),
        clustering=backend.FastClusteringConfig(num_clusters=count, threshold=.5),
        min_duration_on=.3, min_duration_off=.5)
    if not config.validate():
        raise RuntimeError("Invalid speaker model configuration. Check the model files in the configured speaker cache")
    engine = backend.OfflineSpeakerDiarization(config)
    if engine.sample_rate != 16000:
        raise RuntimeError("The speaker model must use a sample rate of 16000 Hz")
    return engine


def diarize(audio, count, report=lambda message: None):
    count = parse_speaker_count(count)
    if count == 1:
        return [SpeakerTurn(0, len(audio) / 16000, "A")]
    report(f"Loading speaker models for {count} speakers (models are downloaded on first use)…")
    engine = create_engine(count, report)
    last = -1
    def progress(done, total):
        nonlocal last
        value = int(done * 100 / max(1, total))
        if value >= last + 5 or value == 100:
            report(f"Identifying speakers: {value}%")
            last = value
        return 0
    results = engine.process(audio, callback=progress).sort_by_start_time()
    labels, turns = {}, []
    for item in results:
        if item.end <= item.start:
            continue
        if item.speaker not in labels:
            if len(labels) >= count:
                raise RuntimeError("The model returned more speakers than requested. Check the speaker count and retry")
            labels[item.speaker] = chr(65 + len(labels))
        turns.append(SpeakerTurn(item.start, item.end, labels[item.speaker]))
    if not turns:
        raise RuntimeError("No usable speaker segments were found. Check the audio or leave the speaker count blank")
    report(f"Requested {count} speakers; found {len(labels)} voice groups. Labels start at Sound A in order of first appearance.")
    if len(labels) != count:
        report("Fewer voice groups were found than requested. Speech may be too short or the count may be incorrect; review the assignments.")
    return turns


if __name__ == "__main__":
    import sys
    try:
        create_engine(2)
        print("Speaker models loaded successfully. Ready for local diarization.")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
