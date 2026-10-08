# Video Subtitle

A local Windows desktop application that turns MP4 speech into timestamped text and subtitles, with optional speaker labels and individual subtitle colors.

Transcribe a video, review the SRT text, and export plain subtitles, burned-in MP4 subtitles, or a selectable color subtitle track in MKV. The interface and documentation are in English. Speech is transcribed in its original language; it is not translated.

## Features

- Local transcription with faster-whisper, running on CPU in the desktop app.
- Timestamped TXT and SRT output, with an editable SRT review area.
- Optional speaker count from 1 to 26; leave it blank for ordinary subtitles.
- A color picker for each speaker, labeled Sound A, Sound B, and so on in order of first appearance.
- Speaker colors in burned-in MP4 and ASS subtitles in MKV. The rendered captions contain only the spoken text, without Sound A/B prefixes.
- Separate output folders for every save or transcription, preserving earlier results.
- A command-line interface for transcription and export.

## Requirements

The desktop application and launch scripts target **Windows 10/11, x64**. The existing working installation uses standard **64-bit CPython 3.14** with Tcl/Tk. Other platforms and Python variants have not been validated for the complete desktop workflow.

Internet access is needed to install dependencies and download models on first use. Transcription and speaker analysis run locally. The application does not upload your video or transcript. Model requests go to Hugging Face and GitHub; those services receive normal download requests.

## Install and run

If you already have a working installation, keep its environment, models, and `runtime.json`. Updating the English source files does not require reinstalling dependencies.

For a fresh checkout:

1. Install standard 64-bit [Python](https://www.python.org/downloads/windows/) with Tcl/Tk and the Python launcher.
2. Download this repository using **Code → Download ZIP** and extract it, or clone it with Git.
3. Open PowerShell in the extracted project folder, where `app.py` and `requirements.txt` are located.
4. Run these commands one line at a time. Stop if any command fails:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.bat
```

No environment activation or PowerShell execution-policy change is required. After installation, double-click `start.bat` to launch the application.

The requirements pin the direct dependencies to versions from the working installation; they are not a complete lock of all transitive dependencies. In particular, PyAV 18.1.0 avoids the `metadata_errors` compatibility problem with faster-whisper 1.2.1, and the two Sherpa packages use matching versions.

### Runtime selection

With no `runtime.json`, `start.bat` uses `.venv\Scripts\python.exe`, and speaker models are cached under `models/speakers`. Existing installations may have a local `runtime.json` that selects a verified environment in `.runtimes` and a speaker cache inside it. Whisper models remain under `models`.

`runtime.json`, environments, and downloaded models are local files and are deliberately excluded from Git. A fresh checkout does not need another user's runtime configuration.

## Use the desktop app

1. Select a video and an output folder. The video can be anywhere; it does not need to be beside the program.
2. Choose a model: `tiny`, `base`, `small`, `medium`, or `large-v3`. Larger models generally require more memory and processing time. The default is `small`.
3. Choose `zh` for Chinese, `en` for English, or `auto` for language detection. The default remains `zh`.
4. Leave **Speakers (optional)** blank for plain subtitles. To label voices, enter the expected speaker count and choose each color. A count of 1 labels all speech as Sound A without loading the diarization model.
5. Click **Transcribe**, then review the editor. Correct words, timestamps, and speaker labels as needed. Keep a blank line between SRT cues.
6. Click **Save edits**, or choose a video export format.

For example, the editor may contain:

```srt
1
00:00:01,000 --> 00:00:03,000
[Sound A] Hello, welcome to the video.

2
00:00:03,200 --> 00:00:05,000
[Sound B] Thank you for having me.
```

The speaker labels remain in TXT/SRT to make assignments editable. Color video exports display only the dialogue text, using each speaker's color. `[Sound ?]` marks an uncertain assignment and defaults to white. It does not identify a real person's name.

## Output formats

| Output | Contents | Speaker colors |
| --- | --- | --- |
| `transcript.txt` | Readable text with start/end timestamps | No; speaker labels are retained |
| `subtitles.srt` | Editable subtitle cues | No; speaker labels are retained |
| `subtitles.ass` | Styled subtitles; generated when speakers are labeled | Yes; no visible speaker prefixes |
| `speakers.json` | Speaker-to-color mapping saved beside the SRT | Used when reopening or exporting |
| Plain soft subtitles (MP4) | A selectable `mov_text` subtitle track | For unlabeled subtitles only |
| Burned-in subtitles (MP4, color) | Captions rendered permanently into the video | Yes; video is re-encoded |
| Color soft subtitles (MKV) | A selectable ASS subtitle track | Yes; requires a player with ASS support |

Soft subtitle exports copy the video and audio streams, so they must be compatible with the output container. Export refuses to overwrite an existing file. Saves create a new folder inside `results` by default. On a failed export, an incomplete video file may remain; choose a new output name for a retry.

## Command line

These examples use a fresh `.venv` installation. For an existing custom runtime, replace the Python path with the interpreter inside the environment selected by `runtime.json`.

```powershell
# Ordinary transcription
.\.venv\Scripts\python.exe subtitle_core.py transcribe "C:\Videos\input.mp4" --language en --model small --out results

# Transcription with three speakers
.\.venv\Scripts\python.exe subtitle_core.py transcribe "C:\Videos\input.mp4" --language auto --speakers 3 --out results

# Replace results\RUN_FOLDER with the folder printed by transcription
.\.venv\Scripts\python.exe subtitle_core.py export "C:\Videos\input.mp4" "results\RUN_FOLDER\subtitles.srt" "captioned.mp4" --mode hard
.\.venv\Scripts\python.exe subtitle_core.py export "C:\Videos\input.mp4" "results\RUN_FOLDER\subtitles.srt" "captioned.mkv" --mode soft-color
```

Use `--colors colors.json` on either command to override the mapping. Without an override, export loads `speakers.json` beside the SRT, if present. A colors file can contain:

```json
{
  "A": "#FF0000",
  "B": "#0080FF",
  "C": "#FFFF00"
}
```

`python subtitle_core.py --help` lists commands. The CLI also exposes `--device cuda`; GPU setup is outside the validated CPU workflow and is not configured automatically.

## Accuracy and limitations

Review all generated subtitles. Background noise, music, overlapping speech, short utterances, and similar voices can reduce transcription and speaker accuracy. The speaker count is supplied by the user; the app does not estimate it automatically. Speaker labels are local to a transcription and are not persistent identities across videos.

The app transcribes the first audio track. It compensates for an initial audio offset, but synchronization should still be reviewed. The editor accepts chronological, non-overlapping cues with at least 1 ms duration. Speaker colors repeat after the default palette runs out; use the color pickers to change them. Burned subtitles use Microsoft YaHei to support Chinese and English text.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Python or Tcl/Tk is missing | Install standard x64 Python with Tcl/Tk and the launcher, then reopen the terminal. |
| The configured runtime is missing | On an existing installation, check the environment selected in `runtime.json`. On a fresh checkout, finish the `.venv` installation above. |
| `metadata_errors` error | Use the pinned PyAV version in the selected runtime; do not upgrade it independently to 19. |
| Missing Sherpa diarization interfaces | Confirm both Sherpa packages match `requirements.txt`, and that no local `sherpa_onnx.py` or unrelated folder shadows the installed package. |
| Model download fails | Check access to Hugging Face for Whisper and GitHub release downloads for speaker models, then retry. |
| FFmpeg or a subtitle filter is missing | Export uses FFmpeg on PATH first, then imageio-ffmpeg. Ensure the selected FFmpeg supports the subtitles/libass filter and libx264. |
| Speaker labels are inaccurate | Check the requested count and edit the `[Sound A]` labels. Leave the count blank when attribution is unnecessary. |

Close the app before maintaining its environment. Keep the working environment and model cache while diagnosing installation problems.

## Development and publishing

Run the focused regression suite without downloading models:

```powershell
py -3.14 -B -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the code map and manual checks, [CHANGELOG.md](CHANGELOG.md) for release notes, and [docs/PUBLISHING.md](docs/PUBLISHING.md) for the GitHub upload procedure.

GitHub Actions runs regression tests and a Windows dependency smoke check. These checks do not measure transcription accuracy or exercise a complete model download and video export.

## License and acknowledgments

Project source is provided under the [MIT License](LICENSE). Dependencies, FFmpeg, and model weights have their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md). No model weights, Python environments, or user media are distributed with the repository.
