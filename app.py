"""Desktop interface; all long-running operations use a worker thread."""
from pathlib import Path
import queue
import re
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, scrolledtext, ttk

from subtitle_core import export_video, parse_srt, recognize, save_result, to_srt
from speaker_tools import default_colors, parse_speaker_count, read_colors


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video Subtitle")
        self.geometry("980x900")
        self.minsize(820, 720)
        self.events = queue.Queue()
        self.busy = False
        self.source = None
        self.video = tk.StringVar()
        self.destination = tk.StringVar(value=str(Path(__file__).resolve().parent / "results"))
        self.model = tk.StringVar(value="small")
        self.language = tk.StringVar(value="zh")
        self.speaker_count = tk.StringVar(value="")
        self.speaker_colors = default_colors(26)
        self.color_buttons = []
        self.highlight_pending = None
        self.status = tk.StringVar(value="Select a video. The first transcription requires internet access to download a model.")
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Video Subtitle", font=("Microsoft YaHei", 20, "bold")).pack(anchor="w")
        ttk.Label(body, text="Select MP4 → Transcribe → Review subtitles → Save TXT / SRT or export video").pack(anchor="w", pady=(6, 14))
        self.controls = []
        for label, variable, picker in [("Video file", self.video, self.pick_video),
                                         ("Output folder", self.destination, self.pick_destination)]:
            row = ttk.Frame(body)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, width=13).pack(side="left")
            entry = ttk.Entry(row, textvariable=variable)
            entry.pack(side="left", fill="x", expand=True)
            button = ttk.Button(row, text="Browse…", command=picker)
            button.pack(side="left", padx=(8, 0))
            self.controls += [entry, button]
        row = ttk.Frame(body)
        row.pack(fill="x", pady=10)
        ttk.Label(row, text="Model").pack(side="left")
        self.model_box = ttk.Combobox(row, textvariable=self.model, values=["tiny", "base", "small", "medium", "large-v3"], width=12, state="readonly")
        self.model_box.pack(side="left", padx=8)
        ttk.Label(row, text="Language").pack(side="left")
        self.language_box = ttk.Combobox(row, textvariable=self.language, values=["zh", "en", "auto"], width=8, state="readonly")
        self.language_box.pack(side="left", padx=8)
        ttk.Label(row, text="zh: Chinese / en: English / auto: detect; runs on CPU", wraplength=330).pack(side="left")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="Speakers (optional)").pack(side="left")
        count_entry = ttk.Entry(row, textvariable=self.speaker_count, width=6)
        count_entry.pack(side="left", padx=8)
        self.controls.append(count_entry)
        ttk.Label(row, text="Leave blank for plain subtitles; enter 1–26 for speaker labels and colors", wraplength=450).pack(side="left")
        self.color_panel = ttk.LabelFrame(body, text="Speaker colors · A/B assigned in order of first appearance")
        self.color_panel.pack(fill="x", pady=4)
        self.color_canvas = tk.Canvas(self.color_panel, height=106, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.color_panel, orient="vertical", command=self.color_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.color_canvas.pack(side="left", fill="both", expand=True)
        self.color_canvas.configure(yscrollcommand=scrollbar.set)
        self.color_rows = ttk.Frame(self.color_canvas)
        self.color_window = self.color_canvas.create_window((0, 0), window=self.color_rows, anchor="nw")
        self.color_rows.bind("<Configure>", lambda event: self.color_canvas.configure(scrollregion=self.color_canvas.bbox("all")))
        self.color_canvas.bind("<Configure>", lambda event: self.color_canvas.itemconfigure(self.color_window, width=event.width))
        self.speaker_count.trace_add("write", self.refresh_speakers)
        row = ttk.Frame(body)
        row.pack(fill="x", pady=6)
        for column in range(3):
            row.columnconfigure(column, weight=1, uniform="actions")
        for index, (label, action) in enumerate([("Transcribe", self.transcribe), ("Open SRT", self.load_srt),
                              ("Save edits", self.save), ("Plain soft subtitles (MP4)", lambda: self.export("soft")),
                              ("Burned-in subtitles (MP4, color)", lambda: self.export("hard")),
                              ("Color soft subtitles (MKV)", lambda: self.export("soft-color"))]):
            button = ttk.Button(row, text=label, command=action)
            button.grid(row=index // 3, column=index % 3, sticky="ew", padx=(0, 6), pady=3)
            self.controls.append(button)
        ttk.Label(body, text="Editor: change [Sound A] to correct a speaker; [Sound ?] means unknown. Keep a blank line between cues.", wraplength=740).pack(anchor="w", pady=(12, 4))
        self.editor = scrolledtext.ScrolledText(body, wrap="word", font=("Microsoft YaHei", 11), height=16, undo=True)
        self.editor.pack(fill="both", expand=True)
        self.editor.bind("<KeyRelease>", self.schedule_highlight)
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.pack(fill="x", pady=(12, 4))
        ttk.Label(body, textvariable=self.status, wraplength=820).pack(anchor="w")
        self.log = scrolledtext.ScrolledText(body, height=5, state="disabled", wrap="word")
        self.log.pack(fill="x", pady=(8, 0))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_speakers()
        self.after(150, self.poll)

    def refresh_speakers(self, *args):
        for child in self.color_rows.winfo_children():
            child.destroy()
        self.color_buttons = []
        try:
            count = parse_speaker_count(self.speaker_count.get())
        except ValueError:
            ttk.Label(self.color_rows, text="Enter an integer from 1 to 26, or leave blank.").pack(anchor="w", padx=8, pady=8)
            return
        if count is None:
            ttk.Label(self.color_rows, text="Speaker labels are off. Enter a speaker count to choose a color for each voice.").pack(anchor="w", padx=8, pady=8)
        else:
            for index in range(count):
                speaker = chr(65 + index)
                row = ttk.Frame(self.color_rows)
                row.pack(fill="x", padx=8, pady=3)
                ttk.Label(row, text=f"Sound {speaker}", width=12).pack(side="left")
                color = self.speaker_colors[speaker]
                button = tk.Button(row, text=f"{color}  Choose color…", bg=color, fg=self.color_foreground(color),
                                   command=lambda s=speaker: self.choose_color(s), width=22,
                                   state="disabled" if self.busy else "normal")
                button.pack(side="left")
                self.color_buttons.append(button)
        if hasattr(self, "editor"):
            self.highlight()

    @staticmethod
    def color_foreground(color):
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        return "#000000" if .299 * r + .587 * g + .114 * b > 150 else "#FFFFFF"

    def choose_color(self, speaker):
        if self.busy:
            return
        _, color = colorchooser.askcolor(color=self.speaker_colors[speaker], title=f"Subtitle color for Sound {speaker}", parent=self)
        if color:
            self.speaker_colors[speaker] = color.upper()
            self.refresh_speakers()

    def selected_colors(self, cues=()):
        count = parse_speaker_count(self.speaker_count.get())
        used = {c.speaker for c in cues if c.speaker not in {None, "?"}}
        keys = set(default_colors(count or 0)) | used
        return {key: self.speaker_colors[key] for key in sorted(keys)}

    def schedule_highlight(self, event=None):
        if self.highlight_pending:
            self.after_cancel(self.highlight_pending)
        self.highlight_pending = self.after(250, self.highlight)

    def highlight(self):
        self.highlight_pending = None
        text = self.editor.get("1.0", "end")
        for key in list(self.speaker_colors) + ["?"]:
            tag = "speaker_" + key
            self.editor.tag_remove(tag, "1.0", "end")
            color = self.speaker_colors.get(key, "#FFFFFF")
            self.editor.tag_configure(tag, foreground=color, background="#202630")
        for match in re.finditer(r"(?m)^\[Sound ([A-Z]|\?)\][^\n]*(?:\n(?!\s*\n)[^\n]+)*", text):
            # End at the blank separator; time and index lines remain unstyled.
            self.editor.tag_add("speaker_" + match.group(1), f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def pick_video(self):
        value = filedialog.askopenfilename(filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")])
        if value:
            self.video.set(value)

    def pick_destination(self):
        value = filedialog.askdirectory()
        if value:
            self.destination.set(value)

    def set_busy(self, busy):
        self.busy = busy
        for control in self.controls:
            control.configure(state="disabled" if busy else "normal")
        for control in [self.model_box, self.language_box]:
            control.configure(state="disabled" if busy else "readonly")
        self.editor.configure(state="disabled" if busy else "normal")
        for control in self.color_buttons:
            control.configure(state="disabled" if busy else "normal")
        self.progress.start(15) if busy else self.progress.stop()

    def worker(self, action):
        if self.busy:
            return
        self.set_busy(True)
        def run():
            try:
                action()
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("idle", None))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "idle":
                    self.set_busy(False)
                elif kind == "result":
                    self.editor.configure(state="normal")
                    self.editor.delete("1.0", "end")
                    self.editor.insert("1.0", value[0])
                    self.highlight()
                    self.editor.configure(state="disabled")
                    self.source = value[1]
                else:
                    self.status.set(value)
                    self.log.configure(state="normal")
                    self.log.insert("end", value + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                    if kind == "error":
                        messagebox.showerror("Operation failed", value)
        except queue.Empty:
            pass
        self.after(150, self.poll)

    def transcribe(self):
        try:
            count = parse_speaker_count(self.speaker_count.get())
            colors = self.selected_colors()
        except ValueError as exc:
            messagebox.showerror("Invalid speaker count", str(exc))
            return
        video, destination = Path(self.video.get()), Path(self.destination.get())
        if not video.is_file():
            messagebox.showerror("Select a video", "The video file does not exist")
            return
        if self.editor.get("1.0", "end").strip() and not messagebox.askyesno("New transcription", "This will replace the editor contents. Save any edits you want to keep first. Continue?"):
            return
        model, language = self.model.get(), self.language.get()
        def action():
            cues = recognize(video, model, language, report=lambda m: self.events.put(("log", m)), num_speakers=count)
            folder = save_result(video, destination, cues, colors)
            self.events.put(("result", (to_srt(cues), video.resolve())))
            self.events.put(("log", f"Transcription complete: {len(cues)} subtitle cues. Saved to: {folder}"))
        self.worker(action)

    def load_srt(self):
        if self.editor.get("1.0", "end").strip() and not messagebox.askyesno("Open subtitles", "The editor contents will be replaced. Continue?"):
            return
        path = filedialog.askopenfilename(filetypes=[("SRT subtitles", "*.srt")])
        if path:
            try:
                cues = parse_srt(Path(path).read_text(encoding="utf-8-sig"))
                content = to_srt(cues)
                sidecar = Path(path).parent / "speakers.json"
                stored_colors = read_colors(sidecar) if sidecar.is_file() else {}
                known = {c.speaker for c in cues if c.speaker not in {None, "?"}}
                known.update(s for s in stored_colors if s != "?")
                self.speaker_colors = default_colors(26)
                self.speaker_colors.update(stored_colors)
                self.speaker_count.set(str(max(ord(s) - 64 for s in known)) if known else "")
                self.editor.delete("1.0", "end")
                self.editor.insert("1.0", content)
                self.highlight()
                self.source = None
                self.status.set("Subtitles loaded. Select the matching video before exporting.")
            except Exception as exc:
                messagebox.showerror("Could not open file", str(exc))

    def save(self):
        try:
            cues = parse_srt(self.editor.get("1.0", "end"))
            colors = self.selected_colors(cues)
            folder = save_result(self.source or Path(self.video.get() or "edited"), Path(self.destination.get()), cues, colors)
            self.status.set(f"Edits saved (including ASS and color settings when speakers are labeled): {folder}")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def export(self, mode):
        try:
            video = Path(self.video.get()).resolve()
            if not video.is_file():
                raise ValueError("Select the video that matches these subtitles first")
            if self.source and video != self.source:
                raise ValueError("The selected video has changed. Transcribe it again or open its matching SRT file")
            cues = parse_srt(self.editor.get("1.0", "end"))
            colors = self.selected_colors(cues)
            if mode == "soft" and any(c.speaker is not None for c in cues):
                raise ValueError("To retain speaker colors, choose Burned-in subtitles (MP4, color) or Color soft subtitles (MKV).")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        extension = ".mkv" if mode == "soft-color" else ".mp4"
        output = filedialog.asksaveasfilename(defaultextension=extension, initialfile=f"{video.stem}_{mode}{extension}", filetypes=[("Video", "*" + extension)])
        if not output:
            return
        destination = Path(self.destination.get())
        def action():
            folder = save_result(video, destination, cues, colors)
            self.events.put(("log", f"Edits saved to: {folder}. Exporting video…"))
            export_video(video, folder / "subtitles.srt", Path(output), mode, colors)
            self.events.put(("log", f"Video exported to: {output}"))
        self.worker(action)

    def close(self):
        if self.busy:
            messagebox.showinfo("Task in progress", "Wait for the current transcription or export to finish before closing the window.")
            return
        if self.editor.get("1.0", "end").strip() and not messagebox.askyesno("Close", "Make sure your edits are saved. Close now?"):
            return
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
