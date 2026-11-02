"""Small cross-platform launcher Control Center (D004)."""

from __future__ import annotations

import threading
from collections.abc import Callable

from runmal.launcher import core
from runmal.launcher.integrations import autostart_enabled, set_autostart


def run_control_center(port: int = core.DEFAULT_PORT) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        from tkinter.scrolledtext import ScrolledText
    except ImportError as exc:
        raise core.LauncherError(
            "The graphical Control Center is unavailable because Tk is not installed. "
            "The normal Rúnmál launcher still works."
        ) from exc

    root = tk.Tk()
    root.title("Rúnmál Control Center")
    root.minsize(520, 360)

    heading = tk.Label(root, text="Rúnmál", font=("TkDefaultFont", 20, "bold"))
    heading.pack(pady=(18, 2))
    subtitle = tk.Label(root, text="Local AI launcher and service control")
    subtitle.pack(pady=(0, 12))

    status_var = tk.StringVar(value="Checking status…")
    status_label = tk.Label(root, textvariable=status_var)
    status_label.pack(pady=(0, 12))

    buttons = tk.Frame(root)
    buttons.pack(pady=4)

    def refresh() -> None:
        current = core.status(port)
        if current.running:
            ownership = "launcher managed" if current.managed else "already running"
            status_var.set(f"Rúnmál is running on this computer ({ownership}).")
        else:
            status_var.set("Rúnmál is stopped.")

    def run_async(action: Callable[[], object], success: str | None = None) -> None:
        for child in buttons.winfo_children():
            child.configure(state="disabled")
        status_var.set("Working…")

        def worker() -> None:
            try:
                action()
            except Exception as exc:
                message = str(exc)
                root.after(
                    0,
                    lambda message=message: messagebox.showerror(
                        "Rúnmál", message, parent=root
                    ),
                )
            else:
                if success:
                    root.after(0, lambda: status_var.set(success))
            finally:
                root.after(0, finish)

        def finish() -> None:
            for child in buttons.winfo_children():
                child.configure(state="normal")
            refresh()

        threading.Thread(target=worker, daemon=True).start()

    tk.Button(
        buttons,
        text="Open Rúnmál",
        width=16,
        command=lambda: run_async(lambda: core.open_runmal(port)),
    ).grid(row=0, column=0, padx=4, pady=4)
    tk.Button(
        buttons,
        text="Start",
        width=12,
        command=lambda: run_async(lambda: core.start_server(port)),
    ).grid(row=0, column=1, padx=4, pady=4)
    tk.Button(
        buttons,
        text="Stop",
        width=12,
        command=lambda: run_async(lambda: core.stop_server(port)),
    ).grid(row=0, column=2, padx=4, pady=4)
    tk.Button(
        buttons,
        text="Restart",
        width=12,
        command=lambda: run_async(lambda: core.restart_server(port)),
    ).grid(row=1, column=1, padx=4, pady=4)

    auto_var = tk.BooleanVar(value=autostart_enabled())

    def toggle_autostart() -> None:
        try:
            set_autostart(auto_var.get())
        except Exception as exc:
            auto_var.set(autostart_enabled())
            messagebox.showerror("Rúnmál", str(exc), parent=root)

    tk.Checkbutton(
        root,
        text="Start Rúnmál automatically when I sign in",
        variable=auto_var,
        command=toggle_autostart,
    ).pack(pady=(12, 8))

    details = ScrolledText(root, height=7, wrap="word")
    details.pack(fill="both", expand=True, padx=16, pady=(4, 8))
    details.insert("1.0", "Diagnostics appear here when requested.")
    details.configure(state="disabled")

    def show_diagnostics() -> None:
        text = core.diagnostics_text(port)
        details.configure(state="normal")
        details.delete("1.0", "end")
        details.insert("1.0", text)
        details.configure(state="disabled")

    tk.Button(root, text="Show Diagnostics", command=show_diagnostics).pack(pady=(0, 14))

    refresh()
    root.mainloop()
