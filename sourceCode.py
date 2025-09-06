import tkinter as tk
import time
import os
import ctypes
from ctypes import wintypes, c_longlong
from tkinter import colorchooser, StringVar, IntVar, DoubleVar, Toplevel, Frame, Label, Entry, Button, BooleanVar, OptionMenu
import threading
from pynput import mouse as pynput_mouse
from typing import List, Tuple, Any, Dict

# --- ctypes Structures and Constants for Windows Raw Input API ---
# These are necessary for capturing mouse movement deltas outside the app's window.

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ('usUsagePage', wintypes.USHORT),
        ('usUsage', wintypes.USHORT),
        ('dwFlags', wintypes.DWORD),
        ('hwndTarget', wintypes.HWND),
    ]

class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ('dwType', wintypes.DWORD),
        ('dwSize', wintypes.DWORD),
        ('hDevice', wintypes.HANDLE),
        ('wParam', wintypes.WPARAM),
    ]

class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ('usFlags', wintypes.USHORT),
        ('usButtonFlags', wintypes.USHORT),
        ('usButtonData', wintypes.USHORT),
        ('ulRawButtons', wintypes.ULONG),
        ('lLastX', wintypes.LONG),
        ('lLastY', wintypes.LONG),
        ('ulExtraInformation', wintypes.ULONG),
    ]

class RAWINPUT_DATA(ctypes.Union):
    _fields_ = [('mouse', RAWMOUSE)]

class RAWINPUT(ctypes.Structure):
    _fields_ = [
        ('header', RAWINPUTHEADER),
        ('data', RAWINPUT_DATA),
    ]

HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_GENERIC_MOUSE = 0x02
RIDEV_INPUTSINK = 0x00000100
WM_INPUT = 0x00FF

SUBCLASSPROC = ctypes.WINFUNCTYPE(c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.WPARAM, wintypes.WPARAM)

DefSubclassProc = ctypes.windll.comctl32.DefSubclassProc
DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.WPARAM, wintypes.WPARAM]
DefSubclassProc.restype = c_longlong

# --- Application Components ---

class SettingsManager:
    def __init__(self, default_config: Dict[str, Any]):
        self.config = default_config
        self._load_settings()

    def _load_settings(self) -> None:
        """Loads settings from a text file if it exists."""
        if not os.path.exists("settings.txt"):
            return
        
        with open("settings.txt", "r") as f:
            for line in f:
                try:
                    key, value = line.strip().split("=", 1)
                    if key in self.config:
                        default_type = type(self.config[key])
                        if default_type is bool:
                            self.config[key] = value.lower() == 'true'
                        elif default_type is float:
                            self.config[key] = float(value)
                        elif default_type is int:
                            self.config[key] = int(value)
                        else:
                            self.config[key] = value
                except (ValueError, IndexError):
                    print(f"Skipping malformed line in settings.txt: {line.strip()}")

    def save_settings(self) -> None:
        """Saves current settings to a text file."""
        with open("settings.txt", "w") as f:
            for key, value in self.config.items():
                f.write(f"{key}={value}\n")

    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Updates the configuration and saves the changes."""
        self.config.update(new_config)
        self.save_settings()

class MouseEventHandler:
    def __init__(self, settings_manager: SettingsManager):
        self.settings = settings_manager
        self.points: List[Tuple[float, float, float]] = []
        self.clicks: List[Tuple[float, float, str, float, bool]] = []
        self.current_pos: List[float] = [0, 0]

    def on_delta_move(self, dx: int, dy: int) -> None:
        """Handles a change in mouse position using Raw Input deltas."""
        now = time.time()
        multiplier = self.settings.config["coordinate_multiplier"]
        self.current_pos[0] += dx * multiplier
        self.current_pos[1] += dy * multiplier
        self.points.append((self.current_pos[0], self.current_pos[1], now))

    def on_click(self, x: int, y: int, button: Any, pressed: bool) -> None:
        """Handles a mouse button click or release event using pynput."""
        button_name = str(button).split('.')[-1]
        rel_x, rel_y = self.current_pos
        self.clicks.append((rel_x, rel_y, button_name, time.time(), pressed))

class MouseTrackerUI:
    def __init__(self, root: tk.Tk, settings_manager: SettingsManager, event_handler: MouseEventHandler):
        self.root = root
        self.settings = settings_manager
        self.events = event_handler
        self.settings_window = None
        self._new_wndproc_ptr = None
        self.pynput_listener = None
        self._setup_main_window()
        self._setup_bindings()
        self._register_raw_input()
        self._start_pynput_listener()

    def _setup_main_window(self) -> None:
        """Initializes the main application window and canvas."""
        self.root.title("Mouse Tracker")
        width = self.settings.config.get("window_width")
        height = self.settings.config.get("window_height")
        x_pos = self.settings.config.get("window_x")
        y_pos = self.settings.config.get("window_y")
        
        if all(v is not None for v in [width, height, x_pos, y_pos]):
            self.root.geometry(f"{width}x{height}+{x_pos}+{y_pos}")
        else:
            self.root.geometry("800x600")
        self.root.minsize(400, 300)

        self.canvas = tk.Canvas(self.root, bg=self.settings.config["canvas_bg_color"])
        self.canvas.pack(fill="both", expand=True)
        
        self.settings_button = Button(self.root, text="Settings", command=self.open_settings)
        self.settings_button.place_forget()

    def _setup_bindings(self) -> None:
        """Binds events to the main window."""
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Enter>", self._show_settings_button)
        self.root.bind("<Leave>", self._hide_settings_button)

    def _show_settings_button(self, event: Any = None) -> None:
        """Makes the settings button visible."""
        self.settings_button.place(relx=1.0, rely=0.0, x=-5, y=5, anchor='ne')

    def _hide_settings_button(self, event: Any = None) -> None:
        """Hides the settings button."""
        self.settings_button.place_forget()

    def _new_wndproc(self, hwnd: int, msg: int, wParam: int, lParam: int, uIdSubclass: int, dwRefData: int) -> int:
        """Subclass procedure to handle Raw Input messages for movement."""
        if msg == WM_INPUT:
            self._process_raw_input(lParam)
        return DefSubclassProc(hwnd, msg, wParam, lParam, uIdSubclass, dwRefData)

    def _register_raw_input(self) -> None:
        """Registers the application to receive Raw Input for movement tracking."""
        hwnd = self.root.winfo_id()
        rid = RAWINPUTDEVICE(usUsagePage=HID_USAGE_PAGE_GENERIC, usUsage=HID_USAGE_GENERIC_MOUSE, dwFlags=RIDEV_INPUTSINK, hwndTarget=hwnd)
        ctypes.windll.user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
        self._new_wndproc_ptr = SUBCLASSPROC(self._new_wndproc)
        ctypes.windll.comctl32.SetWindowSubclass(hwnd, self._new_wndproc_ptr, 1, 0)

    def _process_raw_input(self, hRawInput: int) -> None:
        """Processes Raw Input data to get mouse movement deltas."""
        size = wintypes.UINT()
        ctypes.windll.user32.GetRawInputData(hRawInput, 0x10000003, None, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        
        if size.value > 0:
            buf = ctypes.create_string_buffer(size.value)
            ctypes.windll.user32.GetRawInputData(hRawInput, 0x10000003, buf, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            
            raw = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
            if raw.header.dwType == 0:  # RIM_TYPEMOUSE
                mouse_data = raw.data.mouse
                if mouse_data.lLastX != 0 or mouse_data.lLastY != 0:
                    self.events.on_delta_move(mouse_data.lLastX, mouse_data.lLastY)

    def _start_pynput_listener(self) -> None:
        """Starts the pynput listener in a separate thread for click detection."""
        self.pynput_listener = pynput_mouse.Listener(on_click=self.events.on_click)
        self.pynput_listener.start()

    def open_settings(self) -> None:
        """Opens the settings panel window."""
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        self.settings_window = SettingsPanel(self.root, self.settings.config, self.apply_settings).get_toplevel_window()

    def apply_settings(self, new_config: Dict[str, Any]) -> None:
        """Applies new settings to the application."""
        self.settings.update_config(new_config)
        self.canvas.config(bg=self.settings.config["canvas_bg_color"])

    def close(self) -> None:
        """Saves window position and closes the application."""
        if self.root.winfo_exists() and self._new_wndproc_ptr:
            hwnd = self.root.winfo_id()
            ctypes.windll.comctl32.RemoveWindowSubclass(hwnd, self._new_wndproc_ptr, 1)
        
        if self.pynput_listener and self.pynput_listener.running:
            self.pynput_listener.stop()

        current_geometry = self.root.winfo_geometry().split('+')
        width, height = map(int, current_geometry[0].split('x'))
        x_pos, y_pos = map(int, current_geometry[1:])
        self.settings.update_config({
            "window_width": width,
            "window_height": height,
            "window_x": x_pos,
            "window_y": y_pos
        })
        self.root.destroy()

    def update_canvas(self) -> None:
        """Redraws the canvas with current mouse trail and clicks."""
        self.canvas.delete("all")
        now = time.time()
        lifespan = self.settings.config["line_lifespan"]
        
        try:
            cx, cy = self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2
        except tk.TclError:
            cx, cy = 400, 300

        window_width, window_height = self.canvas.winfo_width(), self.canvas.winfo_height()

        if abs(self.events.current_pos[0]) > window_width / 2 or abs(self.events.current_pos[1]) > window_height / 2:
            self.events.current_pos = [0, 0]
            self.events.points.append(None)

        self.events.points = [p for p in self.events.points if p is None or now - p[2] <= lifespan]
        self.events.clicks = [c for c in self.events.clicks if now - c[3] <= lifespan]

        coords_tuples = [(cx + p[0], cy + p[1]) if p is not None else None for p in self.events.points]
        
        for i in range(len(coords_tuples) - 1):
            p1 = coords_tuples[i]
            p2 = coords_tuples[i+1]
            if p1 is not None and p2 is not None:
                self._draw_line_segment(p1, p2, now, lifespan, self.events.points[i])

        for x, y, button, _, pressed in self.events.clicks:
            is_left_click = button == "left"
            if is_left_click:
                color = self.settings.config["left_click_color"] if pressed else self.settings.config["left_click_release_color"]
                r = self.settings.config["left_click_radius"] if pressed else self.settings.config["left_click_release_radius"]
            else:
                color = self.settings.config["right_click_color"] if pressed else self.settings.config["right_click_release_color"]
                r = self.settings.config["right_click_radius"] if pressed else self.settings.config["right_click_release_radius"]
            self.canvas.create_oval(cx + x - r, cy + y - r, cx + x + r, cy + y + r, fill=color, outline=color)
        
        self.root.after(self.settings.config["frame_interval"], self.update_canvas)

    def _draw_line_segment(self, p1: Tuple[float, float], p2: Tuple[float, float], now: float, lifespan: float, point_data: Any) -> None:
        """Handles drawing a single line segment based on the configured style."""
        line_style = self.settings.config["line_style"]
        width = self.settings.config["line_width"]

        if "fade" in line_style:
            age = now - point_data[2]
            fade_factor = max(0.0, 1.0 - (age / lifespan))
            width *= fade_factor
        
        if "smooth" in line_style or line_style == "original":
            num_steps = 10
            interpolated_points = []
            for i in range(num_steps + 1):
                t = i / num_steps
                x = p1[0] + (p2[0] - p1[0]) * t
                y = p1[1] + (p2[1] - p1[1]) * t
                interpolated_points.append(x)
                interpolated_points.append(y)
            self.canvas.create_line(interpolated_points, fill=self.settings.config["line_color"], width=width, smooth=True)
        elif "jagged" in line_style:
            self.canvas.create_line(p1, p2, fill=self.settings.config["line_color"], width=width)

class SettingsPanel:
    TK_VAR_TYPES = {
        bool: BooleanVar,
        int: IntVar,
        float: DoubleVar,
        str: StringVar
    }
    
    def __init__(self, parent: tk.Tk, config: Dict[str, Any], apply_callback: Any):
        self.parent = parent
        self.config = config
        self.apply_callback = apply_callback
        self.settings_window = Toplevel(parent)
        self.settings_vars: Dict[str, Any] = {}
        self._setup_window()
        self._create_ui()

    def _setup_window(self) -> None:
        self.settings_window.title("Settings")
        self.settings_window.transient(self.parent)
        self.settings_window.grab_set()
        self.settings_window.protocol("WM_DELETE_WINDOW", self.close_window)

    def get_toplevel_window(self) -> Toplevel:
        return self.settings_window

    def _create_ui(self) -> None:
        main_frame = Frame(self.settings_window, padx=10, pady=10)
        main_frame.pack(fill="both", expand=True)
        
        sections = [
            ("General Settings", ["line_lifespan", "frame_interval", "canvas_bg_color", "coordinate_multiplier"]),
            ("Line Appearance", ["line_width", "line_color", "line_style"]),
            ("Click Dots", ["left_click_radius", "left_click_color", "right_click_radius", "right_click_color"]),
            ("Release Dots", ["left_click_release_radius", "left_click_release_color", "right_click_release_radius", "right_click_release_color"])
        ]
        
        row = 0
        for title, keys in sections:
            Label(main_frame, text=title, font=("TkDefaultFont", 12, "bold")).grid(row=row, column=0, columnspan=2, pady=(15, 10))
            row += 1
            for key in keys:
                label_text = key.replace('_', ' ').title() + ":"
                self._create_setting_field(main_frame, label_text, key, row)
                row += 1
        
        button_frame = Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=(20, 0))
        Button(button_frame, text="Apply", command=self.apply_and_close).pack(side="left", padx=5)
        Button(button_frame, text="Cancel", command=self.close_window).pack(side="left", padx=5)

    def _create_setting_field(self, parent_frame: Frame, label_text: str, key: str, row: int) -> None:
        is_color = "color" in key
        var_type = self.TK_VAR_TYPES.get(type(self.config[key]), StringVar)
        var = var_type(value=self.config[key])
        self.settings_vars[key] = var
        
        Label(parent_frame, text=label_text).grid(row=row, column=0, sticky="w", padx=5, pady=2)
        
        if is_color:
            Button(parent_frame, text="Choose", command=lambda: self._choose_color(var)).grid(row=row, column=1, padx=5, pady=2)
        elif key == "line_style":
            choices = ["original", "jagged", "smooth_fade", "jagged_fade"]
            var.set(self.config[key])
            OptionMenu(parent_frame, var, *choices).grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        else:
            Entry(parent_frame, textvariable=var, width=10).grid(row=row, column=1, padx=5, pady=2)

    def _choose_color(self, color_var: StringVar) -> None:
        color_code = colorchooser.askcolor(title="Choose Color")[1]
        if color_code:
            color_var.set(color_code)

    def apply_and_close(self) -> None:
        new_config = {key: var.get() for key, var in self.settings_vars.items()}
        self.apply_callback(new_config)
        self.close_window()

    def close_window(self) -> None:
        self.settings_window.destroy()

class Application:
    def __init__(self, root: tk.Tk):
        self.default_config = {
            "line_lifespan": 0.66,
            "frame_interval": 30,
            "line_width": 4,
            "line_color": "white",
            "canvas_bg_color": "black",
            "left_click_color": "red",
            "right_click_color": "blue",
            "left_click_radius": 5,
            "right_click_radius": 5,
            "left_click_release_color": "lime green",
            "right_click_release_color": "light sky blue",
            "left_click_release_radius": 3,
            "right_click_release_radius": 3,
            "coordinate_multiplier": 1.0,
            "line_style": "original",
            "window_width": 800,
            "window_height": 600,
            "window_x": None,
            "window_y": None
        }
        self.root = root
        self.settings_manager = SettingsManager(self.default_config)
        self.event_handler = MouseEventHandler(self.settings_manager)
        self.ui_manager = MouseTrackerUI(self.root, self.settings_manager, self.event_handler)
    
    def run(self) -> None:
        self.ui_manager.update_canvas()
        self.root.mainloop()

if __name__ == "__main__":
    root_instance = tk.Tk()
    app = Application(root_instance)
    app.run()