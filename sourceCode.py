import tkinter as tk
import time
import os
import ctypes
from ctypes import wintypes, c_longlong
from tkinter import colorchooser, StringVar, IntVar, DoubleVar, Toplevel, Frame, Label, Entry, Button, BooleanVar, OptionMenu, filedialog, Checkbutton
import tkinter.ttk as ttk
import threading
from pynput import mouse as pynput_mouse
from typing import List, Tuple, Any, Dict
import PIL.Image, PIL.ImageTk

# --- ctypes Structures and Constants for Windows Raw Input API ---
# These are necessary for capturing mouse movement deltas outside the app's window.
# They are a robust way to get global mouse input, not just when the mouse is over the app.

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
    """Handles loading, saving, and managing application settings."""
    def __init__(self, default_config: Dict[str, Any]):
        self.config = default_config
        self._load_settings()

    def _load_settings(self) -> None:
        """Loads settings from a text file if it exists, with robust error handling."""
        try:
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
        except Exception as e:
            print(f"Failed to load settings from 'settings.txt'. Using default configuration. Error: {e}")
            # The self.config is already initialized with defaults, so no action needed.

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
    """Manages mouse movement and click events."""
    def __init__(self, settings_manager: SettingsManager):
        self.settings = settings_manager
        # List of (x, y, timestamp) for mouse trail
        self.points: List[Tuple[float, float, float]] = []
        # List of (rel_x, rel_y, button, timestamp, pressed) for clicks
        self.clicks: List[Tuple[float, float, str, float, bool]] = []
        # Current relative position from the canvas center
        self.current_pos: List[float] = [0, 0]
        # Timestamp of the last mouse movement
        self.last_movement_time: float = time.time()

    def on_delta_move(self, dx: int, dy: int) -> None:
        """Handles a change in mouse position using Raw Input deltas."""
        now = time.time()
        self.last_movement_time = now
        multiplier = self.settings.config["coordinate_multiplier"]
        self.current_pos[0] += dx * multiplier
        self.current_pos[1] += dy * multiplier
        self.points.append((self.current_pos[0], self.current_pos[1], now))

    def on_click(self, x: int, y: int, button: Any, pressed: bool) -> None:
        """Handles a mouse button click or release event using pynput."""
        self.last_movement_time = time.time()
        button_name = str(button).split('.')[-1]
        rel_x, rel_y = self.current_pos
        self.clicks.append((rel_x, rel_y, button_name, time.time(), pressed))

class MouseTrackerUI:
    """Manages the main GUI and canvas rendering."""
    def __init__(self, root: tk.Tk, settings_manager: SettingsManager, event_handler: MouseEventHandler):
        self.root = root
        self.settings = settings_manager
        self.events = event_handler
        self.settings_window = None
        self._new_wndproc_ptr = None
        self.pynput_listener = None
        
        # Image references to prevent garbage collection
        self.cursor_photo_image = None
        self.left_click_photo_image = None
        self.left_click_release_photo_image = None
        self.right_click_photo_image = None
        self.right_click_release_photo_image = None
        
        self.cursor_image_id = None
        self._setup_main_window()
        self._setup_bindings()
        self._register_raw_input()
        self._start_pynput_listener()
        self._update_images()
        self.anchor_map = {
            "Center": tk.CENTER,
            "Top-Left": tk.NW,
            "Top-Right": tk.NE,
            "Bottom-Left": tk.SW,
            "Bottom-Right": tk.SE
        }

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
        self._update_images()

    def _load_and_resize_image(self, path: str, scale: float) -> PIL.ImageTk.PhotoImage | None:
        """Helper to load and resize an image from a given path."""
        if path and os.path.exists(path):
            try:
                original_image = PIL.Image.open(path).convert("RGBA")
                if scale != 1.0:
                    new_size = (int(original_image.width * scale), int(original_image.height * scale))
                    resized_image = original_image.resize(new_size, PIL.Image.Resampling.LANCZOS)
                else:
                    resized_image = original_image
                return PIL.ImageTk.PhotoImage(resized_image)
            except Exception as e:
                print(f"Failed to load image from {path}: {e}")
                return None
        return None

    def _update_images(self):
        """Loads and resizes all images based on settings."""
        self.cursor_photo_image = self._load_and_resize_image(self.settings.config.get("cursor_image_path"), self.settings.config.get("cursor_scale", 1.0)) if self.settings.config.get("cursor_image_enabled", False) else None
        
        if self.settings.config.get("click_images_enabled", False):
            self.left_click_photo_image = self._load_and_resize_image(self.settings.config.get("left_click_image_path"), self.settings.config.get("left_click_image_scale", 1.0))
            self.left_click_release_photo_image = self._load_and_resize_image(self.settings.config.get("left_click_release_image_path"), self.settings.config.get("left_click_release_image_scale", 1.0))
            self.right_click_photo_image = self._load_and_resize_image(self.settings.config.get("right_click_image_path"), self.settings.config.get("right_click_image_scale", 1.0))
            self.right_click_release_photo_image = self._load_and_resize_image(self.settings.config.get("right_click_release_image_path"), self.settings.config.get("right_click_release_image_scale", 1.0))
        else:
            self.left_click_photo_image = None
            self.left_click_release_photo_image = None
            self.right_click_photo_image = None
            self.right_click_release_photo_image = None

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
        
        # Auto-recenter logic
        if self.settings.config["auto_recenter_enabled"] and (now - self.events.last_movement_time) > self.settings.config["recenter_timeout_seconds"]:
            self.events.current_pos = [0, 0]
            self.events.points.append(None)
            self.events.last_movement_time = now

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

        # Drawing order logic: cursor on top of clicks or vice versa
        if self.settings.config["cursor_on_top"]:
            self._draw_clicks(cx, cy)
            self._draw_cursor(cx, cy)
        else:
            self._draw_cursor(cx, cy)
            self._draw_clicks(cx, cy)
        
        self.root.after(self.settings.config["frame_interval"], self.update_canvas)

    def _draw_cursor(self, cx, cy):
        """Draws the custom cursor."""
        if self.cursor_photo_image:
            anchor = self.anchor_map.get(self.settings.config.get("cursor_alignment", "Center"), tk.CENTER)
            self.canvas.create_image(cx + self.events.current_pos[0], cy + self.events.current_pos[1], image=self.cursor_photo_image, anchor=anchor)

    def _draw_clicks(self, cx, cy):
        """Draws the custom click dots or fallback dots."""
        for x, y, button, _, pressed in self.events.clicks:
            is_left_click = button == "left"
            
            if is_left_click and pressed:
                if self.left_click_photo_image:
                    self.canvas.create_image(cx + x, cy + y, image=self.left_click_photo_image)
                else:
                    color = self.settings.config["left_click_color"]
                    r = self.settings.config["left_click_radius"]
                    self.canvas.create_oval(cx + x - r, cy + y - r, cx + x + r, cy + y + r, fill=color, outline=color)
            elif is_left_click and not pressed:
                if self.left_click_release_photo_image:
                    self.canvas.create_image(cx + x, cy + y, image=self.left_click_release_photo_image)
                else:
                    color = self.settings.config["left_click_release_color"]
                    r = self.settings.config["left_click_release_radius"]
                    self.canvas.create_oval(cx + x - r, cy + y - r, cx + x + r, cy + y + r, fill=color, outline=color)
            elif not is_left_click and pressed:
                if self.right_click_photo_image:
                    self.canvas.create_image(cx + x, cy + y, image=self.right_click_photo_image)
                else:
                    color = self.settings.config["right_click_color"]
                    r = self.settings.config["right_click_radius"]
                    self.canvas.create_oval(cx + x - r, cy + y - r, cx + x + r, cy + y + r, fill=color, outline=color)
            elif not is_left_click and not pressed:
                if self.right_click_release_photo_image:
                    self.canvas.create_image(cx + x, cy + y, image=self.right_click_release_photo_image)
                else:
                    color = self.settings.config["right_click_release_color"]
                    r = self.settings.config["right_click_release_radius"]
                    self.canvas.create_oval(cx + x - r, cy + y - r, cx + x + r, cy + y + r, fill=color, outline=color)
    
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
    """Manages the settings window and its UI components."""
    
    # Map of Python types to Tkinter variable types
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
        
        # A dictionary to hold all Tkinter variables, allowing for easy access and updates.
        self.settings_vars: Dict[str, Any] = {}
        self._setup_window()
        self._create_ui()

    def _setup_window(self) -> None:
        """Initializes the settings window properties."""
        self.settings_window.title("Settings")
        self.settings_window.transient(self.parent)
        self.settings_window.grab_set()
        self.settings_window.protocol("WM_DELETE_WINDOW", self.close_window)
        self.settings_window.minsize(300, 400)

    def get_toplevel_window(self) -> Toplevel:
        """Returns the main toplevel window for external access."""
        return self.settings_window

    def _create_ui(self) -> None:
        """Builds the main UI for the settings window with multiple tabs."""
        notebook = ttk.Notebook(self.settings_window)
        notebook.pack(padx=10, pady=10, fill="both", expand=True)

        click_images_enabled_var = BooleanVar(value=self.config.get("click_images_enabled", False))
        self.settings_vars["click_images_enabled"] = click_images_enabled_var

        # --- General Settings Tab ---
        general_tab = Frame(notebook, padx=10, pady=10)
        notebook.add(general_tab, text="General Settings")
        
        general_settings_keys = ["line_lifespan", "frame_interval", "canvas_bg_color", "coordinate_multiplier"]
        for row, key in enumerate(general_settings_keys):
            self._create_setting_field(general_tab, key, row)
            
        self._create_recenter_group(general_tab, len(general_settings_keys))

        # --- Line Appearance Tab ---
        line_tab = Frame(notebook, padx=10, pady=10)
        notebook.add(line_tab, text="Line Appearance")
        line_settings_keys = ["line_width", "line_color", "line_style"]
        for row, key in enumerate(line_settings_keys):
            self._create_setting_field(line_tab, key, row)

        # --- Click Dot Appearance Tab ---
        click_tab = Frame(notebook, padx=10, pady=10)
        notebook.add(click_tab, text="Click Dot Appearance")
        self._create_click_dot_group(click_tab, click_images_enabled_var)
        
        # --- Custom Cursor Tab ---
        cursor_tab = Frame(notebook, padx=10, pady=10)
        notebook.add(cursor_tab, text="Custom Cursor")

        cursor_image_enabled_var = BooleanVar(value=self.config.get("cursor_image_enabled", False))
        self.settings_vars["cursor_image_enabled"] = cursor_image_enabled_var

        self._create_toggled_image_group(
            cursor_tab,
            "Enable Custom Cursor",
            cursor_image_enabled_var,
            [("Cursor Image Path:", "cursor_image_path")],
            [("Cursor Scale:", "cursor_scale")],
            is_cursor_tab=True
        )
        
        # --- Custom Click Images Tab ---
        clicks_tab = Frame(notebook, padx=10, pady=10)
        notebook.add(clicks_tab, text="Custom Clicks")
        self._create_toggled_image_group(
            clicks_tab,
            "Enable Custom Clicks",
            click_images_enabled_var,
            [
                ("Left Click (Press):", "left_click_image_path"),
                ("Left Click (Release):", "left_click_release_image_path"),
                ("Right Click (Press):", "right_click_image_path"),
                ("Right Click (Release):", "right_click_release_image_path")
            ],
            [
                ("Left Click Scale:", "left_click_image_scale"),
                ("Left Click Release Scale:", "left_click_release_image_scale"),
                ("Right Click Scale:", "right_click_image_scale"),
                ("Right Click Release Scale:", "right_click_release_image_scale")
            ],
            is_cursor_tab=False
        )
        
        # --- Control Buttons ---
        button_frame = Frame(self.settings_window)
        button_frame.pack(pady=(0, 10))
        Button(button_frame, text="Okay", command=self.apply_and_close).pack(side="left", padx=5)
        Button(button_frame, text="Apply", command=self._apply_only).pack(side="left", padx=5)
        Button(button_frame, text="Cancel", command=self.close_window).pack(side="left", padx=5)

    def _create_recenter_group(self, parent_frame: Frame, start_row: int) -> None:
        """Creates the widgets for the auto-recenter setting."""
        recenter_enabled_var = BooleanVar(value=self.config.get("auto_recenter_enabled", False))
        self.settings_vars["auto_recenter_enabled"] = recenter_enabled_var
        
        recenter_entry_var = DoubleVar(value=self.config.get("recenter_timeout_seconds", 10.0))
        self.settings_vars["recenter_timeout_seconds"] = recenter_entry_var

        recenter_checkbutton = Checkbutton(parent_frame, text="Enable Auto-Recenter", variable=recenter_enabled_var)
        recenter_checkbutton.grid(row=start_row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        
        recenter_label = Label(parent_frame, text="Inactivity Timeout (seconds):")
        recenter_label.grid(row=start_row + 1, column=0, sticky="w", padx=5, pady=2)
        recenter_entry = Entry(parent_frame, textvariable=recenter_entry_var, width=10)
        recenter_entry.grid(row=start_row + 1, column=1, padx=5, pady=2)
        
        def toggle_recenter_state(*args):
            state = tk.NORMAL if recenter_enabled_var.get() else tk.DISABLED
            recenter_label.config(state=state)
            recenter_entry.config(state=state)
        
        recenter_enabled_var.trace_add("write", toggle_recenter_state)
        toggle_recenter_state()

    def _create_click_dot_group(self, parent_frame: Frame, enabled_var: BooleanVar) -> None:
        """
        Creates the widgets for the "Click Dot Appearance" tab.
        These widgets are disabled when custom clicks are enabled.
        """
        widgets = []
        tooltip = Tooltip(parent_frame, "These settings are disabled because 'Custom Clicks' is enabled.")
        
        click_settings_keys = ["left_click_radius", "left_click_color", "right_click_radius", "right_click_color", "left_click_release_radius", "left_click_release_color", "right_click_release_radius", "right_click_release_color"]
        
        for i, key in enumerate(click_settings_keys):
            label_text = key.replace('_', ' ').title() + ":"
            is_color = "color" in key
            var_type = self.TK_VAR_TYPES.get(type(self.config[key]), StringVar)
            var = var_type(value=self.config[key])
            self.settings_vars[key] = var
            
            label = Label(parent_frame, text=label_text)
            label.grid(row=i, column=0, sticky="w", padx=5, pady=2)
            
            if is_color:
                button = Button(parent_frame, text="Choose", command=lambda v=var: self._choose_color(v))
                button.grid(row=i, column=1, padx=5, pady=2)
                widgets.extend([label, button])
            else:
                entry = Entry(parent_frame, textvariable=var, width=10)
                entry.grid(row=i, column=1, padx=5, pady=2)
                widgets.extend([label, entry])

        def toggle_state(*args):
            state = tk.DISABLED if enabled_var.get() else tk.NORMAL
            for widget in widgets:
                widget.config(state=state)
                if state == tk.DISABLED:
                    widget.bind("<Enter>", lambda e, w=widget: tooltip.show_tooltip(w))
                    widget.bind("<Leave>", lambda e: tooltip.hide_tooltip())
                else:
                    widget.unbind("<Enter>")
                    widget.unbind("<Leave>")

        enabled_var.trace_add("write", toggle_state)
        toggle_state()

    def _create_toggled_image_group(self, parent_frame: Frame, toggle_text: str, enabled_var: BooleanVar, path_fields: List[Tuple[str, str]], scale_fields: List[Tuple[str, str]], is_cursor_tab: bool) -> None:
        """
        Creates a group of widgets that can be enabled or disabled by a single checkbox.
        Used for both custom cursors and custom clicks.
        """
        widgets = []
        
        toggle_checkbutton = Checkbutton(parent_frame, text=toggle_text, variable=enabled_var)
        toggle_checkbutton.grid(row=0, column=0, columnspan=3, sticky="w", padx=5, pady=5)
        
        row = 1
        for label_text, path_key in path_fields:
            path_var = StringVar(value=self.config.get(path_key, ""))
            self.settings_vars[path_key] = path_var
            
            label = Label(parent_frame, text=label_text)
            label.grid(row=row, column=0, sticky="w", padx=5, pady=2)
            
            entry = Entry(parent_frame, textvariable=path_var, width=20)
            entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
            
            browse_button = Button(parent_frame, text="Browse", command=lambda v=path_var: self._choose_image_file(v))
            browse_button.grid(row=row, column=2, padx=5, pady=2)
            
            widgets.extend([label, entry, browse_button])
            row += 1
            
        for label_text, scale_key in scale_fields:
            scale_var = DoubleVar(value=self.config.get(scale_key, 1.0))
            self.settings_vars[scale_key] = scale_var
            
            label = Label(parent_frame, text=label_text)
            label.grid(row=row, column=0, sticky="w", padx=5, pady=2)
            
            entry = Entry(parent_frame, textvariable=scale_var, width=10)
            entry.grid(row=row, column=1, padx=5, pady=2)
            
            widgets.extend([label, entry])
            row += 1
            
        if is_cursor_tab:
            cursor_on_top_var = BooleanVar(value=self.config.get("cursor_on_top", False))
            self.settings_vars["cursor_on_top"] = cursor_on_top_var
            cursor_on_top_checkbutton = Checkbutton(parent_frame, text="Draw Cursor Over Clicks", variable=cursor_on_top_var)
            cursor_on_top_checkbutton.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
            widgets.append(cursor_on_top_checkbutton)
            row += 1

            alignment_label = Label(parent_frame, text="Cursor Alignment:")
            alignment_label.grid(row=row, column=0, sticky="w", padx=5, pady=2)
            alignment_options = ["Center", "Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"]
            alignment_var = StringVar(value=self.config.get("cursor_alignment", "Center"))
            self.settings_vars["cursor_alignment"] = alignment_var
            alignment_menu = OptionMenu(parent_frame, alignment_var, *alignment_options)
            alignment_menu.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
            widgets.extend([alignment_label, alignment_menu])

        def toggle_state(*args):
            state = tk.NORMAL if enabled_var.get() else tk.DISABLED
            for widget in widgets:
                widget.config(state=state)
        
        enabled_var.trace_add("write", toggle_state)
        toggle_state()

    def _create_setting_field(self, parent_frame: Frame, key: str, row: int) -> None:
        """Creates a single setting row with a label and an input widget."""
        label_text = key.replace('_', ' ').title() + ":"
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
        """Opens a color chooser dialog and updates the linked variable."""
        color_code = colorchooser.askcolor(title="Choose Color")[1]
        if color_code:
            color_var.set(color_code)

    def _choose_image_file(self, path_var: StringVar) -> None:
        """Opens a file dialog and updates the linked path variable."""
        file_path = filedialog.askopenfilename(
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
            title="Select an Image"
        )
        if file_path:
            path_var.set(file_path)

    def _apply_only(self) -> None:
        """Applies the settings without closing the window."""
        new_config = {key: var.get() for key, var in self.settings_vars.items()}
        self.apply_callback(new_config)

    def apply_and_close(self) -> None:
        """Applies settings and then closes the window."""
        new_config = {key: var.get() for key, var in self.settings_vars.items()}
        self.apply_callback(new_config)
        self.close_window()

    def close_window(self) -> None:
        """Destroys the settings window."""
        self.settings_window.destroy()

class Tooltip:
    """A simple tooltip class for providing information on hover."""
    def __init__(self, parent, text):
        self.parent = parent
        self.text = text
        self.tooltip_window = None

    def show_tooltip(self, widget):
        x, y, _, _ = widget.bbox("insert")
        x += widget.winfo_rootx() + 25
        y += widget.winfo_rooty() + 20
        
        self.tooltip_window = Toplevel(self.parent)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        
        label = Label(self.tooltip_window, text=self.text, background="#ffffe0", relief="solid", borderwidth=1,
                      font=("Helvetica", 8))
        label.pack(ipadx=1)

    def hide_tooltip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

class Application:
    """Main application class to tie all components together."""
    def __init__(self, root: tk.Tk):
        self.default_config = {
            "line_lifespan": 0.66,
            "frame_interval": 30,
            "line_width": 20,
            "line_color": "white",
            "canvas_bg_color": "black",
            "left_click_color": "#ff0000",
            "right_click_color": "#0000ff",
            "left_click_radius": 15,
            "right_click_radius": 15,
            "left_click_release_color": "#ff8080",
            "right_click_release_color": "light sky blue",
            "left_click_release_radius": 10,
            "right_click_release_radius": 10,
            "coordinate_multiplier": 1.0,
            "line_style": "smooth_fade",
            "cursor_image_path": "",
            "cursor_image_enabled": False,
            "cursor_scale": 1.0,
            "cursor_alignment": "Center",
            "left_click_image_path": "",
            "click_images_enabled": False,
            "left_click_image_scale": 1.0,
            "left_click_release_image_path": "",
            "left_click_release_image_scale": 1.0,
            "right_click_image_path": "",
            "right_click_image_scale": 1.0,
            "right_click_release_image_path": "",
            "right_click_release_image_scale": 1.0,
            "auto_recenter_enabled": False,
            "recenter_timeout_seconds": 10.0,
            "cursor_on_top": False,
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
        """Starts the main application loop."""
        self.ui_manager.update_canvas()
        self.root.mainloop()

if __name__ == "__main__":
    root_instance = tk.Tk()
    app = Application(root_instance)
    app.run()
