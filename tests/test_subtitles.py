"""Regression checks that run without models or native dependencies."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from speaker_tools import (
    SpeakerAssigner, SpeakerTurn, diarize, parse_speaker_count, read_colors, to_ass,
)
from subtitle_core import Cue, export_video, make_cues, parse_srt, save_result, to_srt, validate


class SubtitleTests(unittest.TestCase):
    def test_srt_round_trip_preserves_speakers_multiline_and_unicode(self):
        cues = [Cue(0.125, 2.75, "Hello\n\u4f60\u597d", "A"),
                Cue(3, 5, "Uncertain speaker", "?"), Cue(6, 7, "Plain text")]
        self.assertEqual(parse_srt("\ufeff" + to_srt(cues).replace("\n", "\r\n")), cues)

    def test_plain_srt_has_no_speaker_marker(self):
        self.assertNotIn("[Sound", to_srt([Cue(0, 1, "Hello")]))

    def test_invalid_cues_are_rejected(self):
        cases = [
            [Cue(0, 0, "Empty duration")],
            [Cue(-1, 1, "Negative start")],
            [Cue(0, float("inf"), "Infinite end")],
            [Cue(0, 1, " ")],
            [Cue(0, 1, "Invalid speaker", "AA")],
            [Cue(0, 2, "First"), Cue(1, 3, "Overlap")],
        ]
        for cues in cases:
            with self.subTest(cues=cues), self.assertRaises(ValueError):
                validate(cues)

    def test_invalid_srt_label_and_timestamps_are_rejected(self):
        for content in ("1\n00:00:01,000 --> 00:00:02,000\n[Sound AA] Hello",
                        "1\n00:60:00,000 --> 00:61:00,000\nHello", ""):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_srt(content)

    def test_ass_has_colors_without_visible_speaker_prefixes(self):
        cues = [Cue(0, 1, "First", "A"), Cue(1, 2, "Second", "B"),
                Cue(2, 3, "Unknown", "?")]
        ass = to_ass(cues, {"A": "#FF0000", "B": "#0000FF"})
        styles = {line.split(",")[0]: line for line in ass.splitlines() if line.startswith("Style:")}
        self.assertIn("&H000000FF", styles["Style: SoundA"])
        self.assertIn("&H00FF0000", styles["Style: SoundB"])
        self.assertIn("&H00FFFFFF", styles["Style: Unknown"])
        dialogue = [line.split(",", 9) for line in ass.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual([row[3] for row in dialogue], ["SoundA", "SoundB", "Unknown"])
        self.assertEqual([row[9] for row in dialogue], ["First", "Second", "Unknown"])
        self.assertNotIn("[Sound ", ass)

    def test_ass_treats_override_text_as_literal(self):
        ass = to_ass([Cue(0, 1, "{\\pos(10,10)}Hello\nWorld", "A")])
        line = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))
        text = line.split(",", 9)[9]
        self.assertEqual(text, "\uff5b\uff3cpos(10,10)\uff5dHello\\NWorld")

    def test_save_reload_preserves_colors_and_earlier_results(self):
        with tempfile.TemporaryDirectory() as directory:
            cues = [Cue(1, 2, "Hello", "A")]
            first = save_result(Path("sample.mp4"), Path(directory), cues, {"A": "#112233"})
            second = save_result(Path("sample.mp4"), Path(directory), cues, {"A": "#FF0000"})
            self.assertNotEqual(first, second)
            self.assertEqual(parse_srt((first / "subtitles.srt").read_text(encoding="utf-8-sig")), cues)
            self.assertEqual(read_colors(first / "speakers.json"), {"A": "#112233"})
            self.assertIn("[00:00:01.000", (first / "transcript.txt").read_text(encoding="utf-8-sig"))
            self.assertNotIn("[Sound A]", (first / "subtitles.ass").read_text(encoding="utf-8-sig"))

    def test_plain_save_does_not_create_speaker_sidecars(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = save_result(Path("sample.mp4"), Path(directory), [Cue(0, 1, "Hello")])
            self.assertEqual({p.name for p in folder.iterdir()}, {"subtitles.srt", "transcript.txt"})

    def test_word_groups_split_when_speaker_changes(self):
        words = [SimpleNamespace(start=0, end=1, word="Hello"),
                 SimpleNamespace(start=1, end=2, word=" there")]
        segment = SimpleNamespace(words=words)
        assign = SpeakerAssigner([SpeakerTurn(0, 1, "A"), SpeakerTurn(1, 2, "B")])
        self.assertEqual(make_cues([segment], speaker_for=assign),
                         [Cue(0, 1, "Hello", "A"), Cue(1, 2, "there", "B")])

    def test_speaker_assignment_handles_overlap_and_gaps(self):
        assign = SpeakerAssigner([SpeakerTurn(0, 2, "A"), SpeakerTurn(1, 3, "B")])
        self.assertEqual(assign(0, 1), "A")
        self.assertEqual(assign(1, 2), "?")
        self.assertEqual(assign(2, 3), "B")
        self.assertEqual(assign(4, 5), "?")

    def test_speaker_count_is_optional_and_bounded(self):
        self.assertIsNone(parse_speaker_count(" "))
        self.assertIsNone(parse_speaker_count(None))
        self.assertEqual(parse_speaker_count("26"), 26)
        for count in (0, 27, -1, "two", "1.5"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                parse_speaker_count(count)

    def test_one_speaker_does_not_load_backend(self):
        with patch("speaker_tools.create_engine", side_effect=AssertionError("Unexpected model load")):
            self.assertEqual(diarize([0] * 16000, 1), [SpeakerTurn(0, 1, "A")])


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.video = self.root / "input.mp4"
        self.video.touch()
        self.srt = self.root / "subtitles.srt"

    def test_all_export_modes_choose_expected_codec_and_subtitle_type(self):
        for mode, extension, speaker in (("soft", ".mp4", None), ("hard", ".mp4", "A"),
                                         ("soft-color", ".mkv", "A")):
            self.srt.write_text(to_srt([Cue(0, 1, "Hello", speaker)]), encoding="utf-8")
            captured = {}

            def run(command, **kwargs):
                captured["command"] = command
                temporary = Path(kwargs["cwd"])
                if (temporary / "captions.ass").exists():
                    captured["ass"] = (temporary / "captions.ass").read_text(encoding="utf-8-sig")
                return SimpleNamespace(returncode=0, stderr="")

            with self.subTest(mode=mode), patch("subtitle_core.shutil.which", return_value="ffmpeg"), \
                    patch("subtitle_core.subprocess.run", side_effect=run):
                export_video(self.video, self.srt, self.root / (mode + extension), mode, {"A": "#FF0000"})
                command = captured["command"]
                self.assertIn("-n", command)
                if mode == "hard":
                    self.assertEqual(command[command.index("-c:v") + 1], "libx264")
                    self.assertEqual(command[command.index("-vf") + 1], "subtitles=filename=captions.ass")
                else:
                    self.assertEqual(command[command.index("-c:v") + 1], "copy")
                    self.assertEqual(command[command.index("-c:s") + 1], "mov_text" if mode == "soft" else "ass")
                if speaker:
                    self.assertNotIn("[Sound A]", captured["ass"])

    def test_plain_soft_export_rejects_speaker_labels(self):
        self.srt.write_text(to_srt([Cue(0, 1, "Hello", "A")]), encoding="utf-8")
        with patch("subtitle_core.subprocess.run") as run, self.assertRaises(ValueError):
            export_video(self.video, self.srt, self.root / "output.mp4", "soft")
        run.assert_not_called()

    def test_existing_output_is_preserved(self):
        self.srt.write_text(to_srt([Cue(0, 1, "Hello")]), encoding="utf-8")
        output = self.root / "output.mp4"
        output.write_bytes(b"existing output")
        with patch("subtitle_core.subprocess.run") as run, self.assertRaises(ValueError):
            export_video(self.video, self.srt, output)
        run.assert_not_called()
        self.assertEqual(output.read_bytes(), b"existing output")


if __name__ == "__main__":
    unittest.main()
