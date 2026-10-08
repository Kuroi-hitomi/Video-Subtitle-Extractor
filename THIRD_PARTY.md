# Third-party software and models

The MIT license in this repository applies to this project's source. It does not relicense dependencies, downloaded model weights, or FFmpeg binaries. They are installed or downloaded separately and are not included in this repository.

| Component | Purpose | Upstream source |
| --- | --- | --- |
| faster-whisper | Whisper transcription | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| CTranslate2 | Inference used by faster-whisper | [OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2) |
| PyAV | Audio decoding | [PyAV-Org/PyAV](https://github.com/PyAV-Org/PyAV) |
| sherpa-onnx and sherpa-onnx-core | Speaker diarization | [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) |
| imageio-ffmpeg | FFmpeg binary discovery and distribution | [imageio/imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) |
| FFmpeg | Subtitle muxing and video rendering | [FFmpeg legal information](https://ffmpeg.org/legal.html) |
| Whisper models | Speech recognition weights | [SYSTRAN on Hugging Face](https://huggingface.co/Systran) |
| Pyannote segmentation 3.0 ONNX | Speaker segmentation | [Sherpa segmentation releases](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models) |
| 3D-Speaker ERes2Net ONNX | Speaker embeddings | [Sherpa speaker recognition releases](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models) |

The speaker downloader retains the segmentation archive's `LICENSE` and `README.md` beside `model.onnx`. Consult the corresponding upstream license and model documentation before redistributing binaries or weights. The exact FFmpeg license depends on its build configuration. Microsoft YaHei is a system font referenced by name; no font files are distributed here.
