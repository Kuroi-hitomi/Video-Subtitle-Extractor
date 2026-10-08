# Contributing

Use an issue to describe a reproducible bug or propose a change. For fixes, explain the observed behavior, expected behavior, Python version, and relevant error message. Share a small media sample only if you have permission to distribute it.

## Development setup

Follow the fresh-install steps in [README.md](README.md). Use a separate checkout and environment for dependency experiments so that a working desktop installation remains usable.

Keep application messages, comments, and documentation in English. Transcription remains multilingual, and the default language stays `zh`. Preserve UTF-8 handling and the existing TXT/SRT speaker markers.

## Code map

| File | Responsibility |
| --- | --- |
| `app.py` | Tkinter interface, background tasks, editor, and color selection |
| `subtitle_core.py` | Transcription, cue validation, TXT/SRT persistence, and FFmpeg export |
| `speaker_tools.py` | Speaker model downloads, diarization, attribution, and ASS styling |
| `runtime_config.py` | Local runtime selection and model cache paths |
| `runtime_launcher.py` | Launch the app with the selected interpreter |
| `start.bat`, `run_python.bat` | Windows launcher entry points |
| `tests/` | Lightweight regression tests; no media or models |

## Validation

Run `python -B -m unittest discover -s tests -v` from the project root. The suite covers subtitle round trips, speaker attribution, timing validation, literal ASS text, saved color settings, export command selection, and runtime configuration containment.

For changes involving recognition, the GUI, dependencies, or FFmpeg, also check manually:

1. Transcribe a short video with the speaker count blank, then save and reopen its SRT.
2. Transcribe speech from multiple people with the expected count supplied.
3. Change a speaker label and color, save, reopen, and verify the color persists.
4. Export hard MP4 and color MKV. Confirm synchronization, text, and colors; the rendered captions must not show Sound A/B prefixes.
5. Export plain soft MP4 from unlabeled subtitles and verify the subtitle track in a compatible player.
6. Check a non-ASCII input path and non-English speech. Resize the GUI to check labels remain readable.

GitHub Actions checks core behavior and native dependency imports on Windows; it does not replace these media checks.

## Pull requests

Keep changes focused. Explain what changed and why, state which checks ran, and document user-visible differences. Do not commit environments, model weights, personal videos, generated subtitles, credentials, or machine-specific runtime settings. Update the changelog when behavior changes.
