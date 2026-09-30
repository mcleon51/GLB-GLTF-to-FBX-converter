"""GUI 3D converter: GLB/GLTF -> FBX via headless Blender, with drag & drop.

Saves the resulting .fbx in the same folder as the source file.
Requires: Python 3 with pip packages tkinterdnd2, and Blender installed.
"""

import json
import os
import shutil
import subprocess
import sys
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    HAS_DND = False

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BLENDER_SCRIPT = os.path.join(APP_DIR, "blender_convert.py")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")

SUPPORTED_EXT = {".glb", ".gltf", ".obj", ".fbx", ".blend"}

BLENDER_CANDIDATES = [
    os.path.expandvars(r"%PROGRAMFILES%\Blender Foundation"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Blender Foundation"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation"),
    r"C:\Blender",
    r"D:\Blender",
    r"E:\Blender",
]


def find_blender():
    seen = set()
    for root in BLENDER_CANDIDATES:
        if not os.path.isdir(root):
            continue
        for ver in sorted(os.listdir(root), key=lambda v: (v[0].isdigit(), v), reverse=True):
            path = os.path.join(root, ver, "blender.exe")
            if os.path.isfile(path) and path not in seen:
                seen.add(path)
    try:
        import winreg
        for key_path in (
            r"SOFTWARE\Classes\blendfile\Shell\Open\Command",
            r"SOFTWARE\Classes\.blend\OpenWithProgids",
        ):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    val, _ = winreg.QueryValueEx(key, "")
                if val:
                    val = val.strip().strip('"')
                    if val.lower().endswith(".exe"):
                        seen.add(val)
            except OSError:
                pass
    except Exception:
        pass
    in_path = shutil.which("blender")
    if in_path:
        seen.add(in_path)
    return sorted(seen)


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
    except Exception:
        pass


class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.files = []          # list of source paths
        self.status = {}         # path -> status text
        self.converting = False
        self._build_ui()
        self._apply_settings()

    # ----------------------------- UI -----------------------------------
    def _build_ui(self):
        root = self.root
        root.title("3D Converter  (GLB / GLTF -> FBX)")
        root.geometry("820x640")
        root.minsize(640, 480)

        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(root)
        top.pack(fill="x", **pad)

        drop_frame = ttk.LabelFrame(root, text="Добавьте файлы (перетащите или через кнопку)")
        drop_frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self.drop_label = ttk.Label(
            drop_frame,
            text="\nПеретащите .glb / .gltf файлы сюда\n\nили нажмите «Добавить файлы»",
            anchor="center",
            justify="center",
            foreground="#888888",
            font=("Segoe UI", 11),
        )
        self.drop_label.pack(fill="x", pady=4)

        self.tree = ttk.Treeview(drop_frame, columns=("status", "out"), show="tree headings")
        self.tree.heading("#0", text="Файл")
        self.tree.heading("status", text="Статус")
        self.tree.heading("out", text="Результат")
        self.tree.column("#0", width=360, anchor="w")
        self.tree.column("status", width=180, anchor="w")
        self.tree.column("out", width=240, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        btn_row = ttk.Frame(drop_frame)
        btn_row.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(btn_row, text="Добавить файлы", command=self.add_files).pack(side="left")
        ttk.Button(btn_row, text="Удалить выбранное", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(btn_row, text="Очистить список", command=self.clear_list).pack(side="left")

        if HAS_DND:
            self.drop_label.drop_target_register(DND_FILES)
            self.tree.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self.on_drop)
            self.tree.dnd_bind("<<Drop>>", self.on_drop)
            self.drop_label.dnd_bind("<<DropEnter>>", lambda e: self.drop_label.config(foreground="#0a0"))
            self.drop_label.dnd_bind("<<DropLeave>>", lambda e: self.drop_label.config(foreground="#888888"))
        else:
            self.drop_label.config(
                text="\nDrag&drop недоступен (нет tkinterdnd2).\n"
                     "Установите:  pip install tkinterdnd2\n"
                     "или добавляйте файлы кнопкой «Добавить файлы»\n"
            )

        settings_frame = ttk.LabelFrame(root, text="Blender")
        settings_frame.pack(fill="x", padx=8, pady=4)

        self.blender_var = tk.StringVar()
        ttk.Label(settings_frame, text="blender.exe:").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(settings_frame, textvariable=self.blender_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(settings_frame, text="Обзор...", command=self.browse_blender).grid(row=0, column=2, padx=2)
        ttk.Button(settings_frame, text="Найти", command=self.detect_blender).grid(row=0, column=3, padx=2)

        scale_frame = ttk.Frame(settings_frame)
        scale_frame.grid(row=1, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 4))
        self.keep_name_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(scale_frame, text="Сохранять имя файла (имя.fbx)", variable=self.keep_name_var).pack(side="left")
        ttk.Label(scale_frame, text="    Результат сохраняется в папке исходника").pack(side="left")
        settings_frame.columnconfigure(1, weight=1)

        action = ttk.Frame(root)
        action.pack(fill="x", padx=8, pady=4)
        self.progress = ttk.Progressbar(action, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.convert_btn = ttk.Button(action, text="Конвертировать", command=self.start_convert)
        self.convert_btn.pack(side="left")

        log_frame = ttk.LabelFrame(root, text="Журнал")
        log_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log = scrolledtext.ScrolledText(
            log_frame, height=8, state="disabled", font=("Consolas", 9), background="#1e1e1e", foreground="#dddddd"
        )
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

    def _apply_settings(self):
        blender = self.settings.get("blender", "")
        if not blender or not os.path.isfile(blender):
            found = find_blender()
            if found:
                blender = found[0]
        self.blender_var.set(blender)

    # --------------------------- actions --------------------------------
    def log_line(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Выберите 3D-файлы",
            filetypes=[("3D модели", "*.glb *.gltf *.obj *.fbx *.blend"), ("Все файлы", "*.*")],
        )
        self._add_paths(list(paths))

    def _add_paths(self, paths):
        added = 0
        for path in paths:
            path = os.path.abspath(path)
            ext = os.path.splitext(path)[1].lower()
            if ext not in SUPPORTED_EXT:
                continue
            if path in self.files:
                continue
            self.files.append(path)
            self.status[path] = "в очереди"
            self._refresh_tree(path)
            added += 1
        self._update_colors()
        if added:
            msg = "добавлено файлов: {}".format(added)
            self.log_line("[+] " + msg)

    def on_drop(self, event):
        raw = event.data
        files = []
        if raw:
            if isinstance(raw, str):
                files = list(self.root.tk.splitlist(raw))
        self._add_paths(files)

    def remove_selected(self):
        sel = self.tree.selection()
        for item in sel:
            path = self.tree.item(item, "text")
            if path and path in self.files:
                self.files.remove(path)
                self.status.pop(path, None)
            self.tree.delete(item)
        self._update_colors()

    def clear_list(self):
        self.files = []
        self.status = {}
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _refresh_tree(self, path, status=None):
        if status:
            self.status[path] = status
        name = os.path.basename(path)
        ext = os.path.splitext(path)[1]
        out = ""
        if ext.lower() in (".glb", ".gltf", ".obj", ".fbx", ".blend"):
            out = os.path.join(os.path.dirname(path), self._out_name(path))
        state = self.status.get(path, "")
        for item in self.tree.get_children():
            if self.tree.item(item, "text") == path:
                self.tree.item(item, values=(state, out))
                return
        self.tree.insert("", "end", text=path, values=(state, out))

    def _out_name(self, path):
        if self.keep_name_var.get():
            return os.path.splitext(os.path.basename(path))[0] + ".fbx"
        return os.path.basename(path) + ".fbx"

    def browse_blender(self):
        path = filedialog.askopenfilename(
            title="Укажите blender.exe",
            filetypes=[("Blender", "blender.exe")],
        )
        if path:
            self.blender_var.set(path)
            self._save_blender_setting()

    def detect_blender(self):
        found = find_blender()
        if not found:
            messagebox.showwarning(
                "Blender не найден",
                "Blender не найден. Укажите путь к blender.exe вручную.",
            )
            return
        self.blender_var.set(found[0])
        self._save_blender_setting()
        messagebox.showinfo(
            "Blender найден",
            "Blender: {}\n\nТакже доступны: {}".format(found[0], ", ".join(found[1:]) if len(found) > 1 else "—"),
        )

    def _save_blender_setting(self):
        self.settings["blender"] = self.blender_var.get()
        save_settings(self.settings)

    def _update_colors(self):
        for item in self.tree.get_children():
            status = self.tree.item(item, "values")[0]
            tags = self.tree.item(item, "tags")
            new_tags = []
            if status == "OK":
                new_tags.append("ok")
            elif status.startswith("ОШИБКА") or status == "не найдено":
                new_tags.append("err")
            self.tree.item(item, tags=new_tags)
        self.tree.tag_configure("ok", foreground="#1a7a1a")
        self.tree.tag_configure("err", foreground="#c03030")

    # -------------------------- conversion ------------------------------
    def start_convert(self):
        if self.converting:
            return
        blender = self.blender_var.get().strip()
        if not blender or not os.path.isfile(blender):
            messagebox.showerror(
                "Blender не найден",
                "Укажите путь к blender.exe в настройках, либо нажмите «Найти».",
            )
            return
        if not self.files:
            messagebox.showwarning("Нет файлов", "Добавьте файлы для конвертации.")
            return
        self._save_blender_setting()
        self.converting = True
        self.convert_btn.config(state="disabled")
        self.progress.config(maximum=len(self.files), value=0)
        for path in self.files:
            self.status[path] = "в очереди"
        self._refresh_all()
        self.log_line("== Начинаю конвертацию: {} файл(ов) ==".format(len(self.files)))
        threading.Thread(target=self._convert_loop, args=(blender,), daemon=True).start()

    def _refresh_all(self):
        for path in self.files:
            self._refresh_tree(path)
        self._update_colors()

    def _convert_loop(self, blender):
        done = 0
        failures = 0
        for path in list(self.files):
            out = self._out_name(path)
            out_path = os.path.join(os.path.dirname(path), out)
            self.root.after(0, lambda p=path: self._refresh_tree(p, "конвертирую..."))
            self.log_line("---- {}".format(os.path.basename(path)))
            ok = self._run_one(blender, path, out_path)
            done += 1
            state = "OK" if ok else "ОШИБКА"
            if not ok:
                failures += 1
            self.root.after(0, lambda p=path, s=state: self._refresh_tree(p, s))
            self.root.after(0, lambda d=done: self.progress.configure(value=d))
        self.converting = False
        summary = "== Готово. Ошибок: {}. Конвертировано: {}/{} ==".format(
            failures, done - failures, len(self.files)
        )
        self.root.after(0, self.log_line, summary)
        self.root.after(0, self.convert_btn.config, {"state": "normal"})
        if failures == 0:
            self.root.after(0, lambda: messagebox.showinfo("Готово", "Все файлы сконвертированы."))
        else:
            self.root.after(
                0,
                lambda: messagebox.showwarning(
                    "Частично", "Файлы с ошибками помечены в списке, детали — в журнале."
                ),
            )

    def _run_one(self, blender, src, dst):
        cmd = [blender, "-b", "--python", BLENDER_SCRIPT, "--", src, dst]
        self.log_line("  blender -b (headless)...")
        try:
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation,
            )
        except Exception as exc:
            self.root.after(0, self.log_line, "  ! не удалось запустить Blender: " + str(exc))
            return False

        result = "ERROR:"
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            if line.startswith("OK:"):
                result = "OK:"
            elif line.startswith("ERROR:"):
                result = "ERROR:" + line[len("ERROR:"):]
            elif line.startswith("MISSING:"):
                result = "MISSING:"
            self.root.after(0, self.log_line, "  " + line)
        proc.wait()

        if result == "OK:":
            self.root.after(0, self.log_line, "  -> " + dst)
            return True
        if result.startswith("MISSING"):
            pass
        self.root.after(0, self.log_line, "  ! конвертация завершилась с ошибкой")
        return False


def main():
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()