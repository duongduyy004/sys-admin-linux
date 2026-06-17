import tkinter as tk
from tkinter import ttk

from gui.i18n import tr


COLORS = {
    "bg": "#f5f7fb",
    "sidebar": "#263238",
    "sidebar_active": "#3a4a53",
    "sidebar_text": "#ffffff",
    "text": "#1f2933",
    "muted": "#52606d",
    "border": "#d9e2ec",
    "accent": "#2563eb",
    "danger": "#b91c1c",
}


def configure_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=COLORS["bg"])
    install_text_input_shortcuts(root)

    default_font = ("DejaVu Sans", 10)
    title_font = ("DejaVu Sans", 18, "bold")
    subtitle_font = ("DejaVu Sans", 10)
    button_font = ("DejaVu Sans", 10)

    root.option_add("*Font", default_font)
    style.configure(".", font=default_font, background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Page.TFrame", background=COLORS["bg"])
    style.configure("Header.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=title_font)
    style.configure("Subtitle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=subtitle_font)
    style.configure("Status.TLabel", background="#e8eef7", foreground=COLORS["muted"], padding=(10, 6))
    style.configure("TButton", font=button_font, padding=(10, 7))
    style.configure("Accent.TButton", font=button_font, padding=(10, 7), foreground="#ffffff", background=COLORS["accent"])
    style.configure("Danger.TButton", font=button_font, padding=(10, 7), foreground="#ffffff", background=COLORS["danger"])
    style.configure("Card.TFrame", background="#ffffff", borderwidth=1, relief="solid")
    style.configure("Treeview", rowheight=26, fieldbackground="#ffffff", background="#ffffff", foreground=COLORS["text"])
    style.configure("Treeview.Heading", font=("DejaVu Sans", 10, "bold"), background="#e8eef7")
    style.map("TButton", background=[("active", "#e2e8f0")])
    style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#94a3b8")])
    style.map("Danger.TButton", background=[("active", "#991b1b"), ("disabled", "#cbd5e1")])


def install_text_input_shortcuts(root: tk.Tk) -> None:
    """Make Tk/ttk text inputs behave like normal desktop fields."""

    def select_all(widget: tk.Widget) -> str:
        try:
            if isinstance(widget, tk.Text):
                widget.tag_remove("sel", "1.0", "end")
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "end-1c")
            else:
                widget.selection_range(0, "end")
                widget.icursor("end")
        except tk.TclError:
            pass
        return "break"

    def select_all_event(event: tk.Event) -> str:
        return select_all(event.widget)

    def is_editable(widget: tk.Widget) -> bool:
        try:
            state = str(widget.cget("state"))
        except tk.TclError:
            return True
        return state not in {"disabled", "readonly"}

    def popup_menu(widget: tk.Widget, x_root: int, y_root: int) -> str:
        try:
            widget.focus_set()
        except tk.TclError:
            pass

        editable = is_editable(widget)
        edit_state = "normal" if editable else "disabled"
        menu = tk.Menu(widget, tearoff=False)
        menu.add_command(label=tr("Cut"), command=lambda: widget.event_generate("<<Cut>>"), state=edit_state)
        menu.add_command(label=tr("Copy"), command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label=tr("Paste"), command=lambda: widget.event_generate("<<Paste>>"), state=edit_state)
        menu.add_separator()
        menu.add_command(label=tr("Select All"), command=lambda: select_all(widget))
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()
        return "break"

    def pointer_menu_event(event: tk.Event) -> str:
        return popup_menu(event.widget, event.x_root, event.y_root)

    def keyboard_menu_event(event: tk.Event) -> str:
        widget = event.widget
        x_root = widget.winfo_rootx() + 12
        y_root = widget.winfo_rooty() + max(widget.winfo_height() // 2, 12)
        return popup_menu(widget, x_root, y_root)

    for widget_class in ("Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox", "Text"):
        root.bind_class(widget_class, "<Control-a>", select_all_event)
        root.bind_class(widget_class, "<Control-A>", select_all_event)
        root.bind_class(widget_class, "<Button-3>", pointer_menu_event)
        root.bind_class(widget_class, "<Shift-F10>", keyboard_menu_event)
        root.bind_class(widget_class, "<Menu>", keyboard_menu_event)


def make_sidebar_button(parent: tk.Widget, text: str, command) -> tk.Button:
    return tk.Button(
        parent,
        text=text,
        command=command,
        anchor="w",
        padx=18,
        pady=12,
        bd=0,
        fg=COLORS["sidebar_text"],
        bg=COLORS["sidebar"],
        activebackground=COLORS["sidebar_active"],
        activeforeground=COLORS["sidebar_text"],
        font=("DejaVu Sans", 11),
        cursor="hand2",
    )
