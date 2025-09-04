import tkinter as tk
import time
import os
from pynput import mouse
from tkinter import colorchooser, StringVar, IntVar, DoubleVar, Toplevel, Frame, Label, Entry, Button, BooleanVar, OptionMenu
import math

class SettingsManager:
    """Handles loading, saving, and managing application settings."""
    def __init__(self, default_config: dict):
        self.config = default_config
        self._load_settings()

    def _load_settings(self):
        """Loads configuration from a settings.txt file."""
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

    def save_settings(self):
        """Saves current configuration to a settings.txt file."""
        with open("settings.txt", "w") as f:
            for key, value in self.config.items():
                f.write(f"{key}={value}\n")

    def update_config(self, new_config: dict):
        """Applies a new configuration dictionary."""
        self.config.update(new_config)
        self.save_settings()

class MouseEventHandler:
    """Manages the mouse listener and data collection."""
    def __init__(self, settings_manager: SettingsManager):
        self.settings = settings_manager
        self.points = []
        self.clicks = []
        self.last_pos = None
        self.current_pos = [0, 0]
        self._listener = None

    def start_listener(self):
        """Initializes and starts the pynput mouse listener."""
        self._listener = mouse.Listener(
            on_move=self.on_move,
            on_click=self.on_click
        )
        self._listener.start()

    def stop_listener(self):
        """Stops the mouse listener."""
        if self._listener:
            self._listener.stop()

    def on_move(self, x, y):
        """Callback for mouse movement."""
        now = time.time()
        if self.last_pos:
            dx, dy = x - self.last_pos[0], y - self.last_pos[1]
            multiplier = self.settings.config["coordinate_multiplier"]
            
            self.current_pos[0] += dx * multiplier
            self.current_pos[1] += dy * multiplier
            
            self.points.append((self.current_pos[0], self.current_pos[1], now))
        self.last_pos = (x, y)

    def on_click(self, x, y, button, pressed):
        """Callback for mouse clicks."""
        rel_x, rel_y = self.current_pos
        self.clicks.append((rel_x, rel_y, button, time.time(), pressed))

class MouseTrackerUI:
    """Manages the main Tkinter window and canvas."""
    def __init__(self, root: tk.Tk, settings_manager: SettingsManager, event_handler: MouseEventHandler):
        self.root = root
        self.settings = settings_manager
        self.events = event_handler
        self.settings_window = None
        
        self._setup_main_window()
        self._setup_bindings()

    def _setup_main_window(self):
        """Sets up the main Tkinter window and canvas."""
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

        self.main_frame = Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.main_frame, bg=self.settings.config["canvas_bg_color"])
        self.canvas.pack(fill="both", expand=True)

        self.settings_button = Button(self.main_frame, text="Settings", command=self.open_settings)
        self.hide_settings_button()

    def _setup_bindings(self):
        """Binds window and mouse events."""
        self.root.bind("<Configure>", self.on_resize)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Enter>", self.show_settings_button)
        self.root.bind("<Leave>", self.hide_settings_button)

    def show_settings_button(self, event=None):
        """Shows the settings button when the mouse enters the window."""
        self.settings_button.place(relx=1.0, rely=0, x=-5, y=5, anchor="ne")

    def hide_settings_button(self, event=None):
        """Hides the settings button when the mouse leaves the window."""
        self.settings_button.place_forget()

    def open_settings(self):
        """Creates and displays a new Toplevel window for settings."""
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        self.settings_window = SettingsPanel(
            self.root,
            self.settings.config,
            self.apply_settings
        ).get_toplevel_window()

    def apply_settings(self, new_config):
        """Applies settings from the settings panel."""
        self.settings.update_config(new_config)
        self.canvas.config(bg=self.settings.config["canvas_bg_color"])

    def on_resize(self, event):
        """Updates window dimensions on resize."""
        if event.widget == self.root:
            self.width, self.height = event.width, event.height
            self.center = (self.width // 2, self.height // 2)

    def close(self):
        """Saves window geometry and properly shuts down the application."""
        current_geometry = self.root.winfo_geometry().split('+')
        width, height = map(int, current_geometry[0].split('x'))
        x_pos, y_pos = map(int, current_geometry[1:])
        
        self.settings.update_config({
            "window_width": width,
            "window_height": height,
            "window_x": x_pos,
            "window_y": y_pos
        })
        self.events.stop_listener()
        self.root.destroy()

    def update_canvas(self):
        """Redraws the canvas with current mouse trail and clicks."""
        self.canvas.delete("all")
        now = time.time()
        lifespan = self.settings.config["line_lifespan"]
        
        cx, cy = self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2

        if self.events.points and self.events.points[-1] is not None:
            rel_x, rel_y, _ = self.events.points[-1]
            draw_x, draw_y = cx + rel_x, cy + rel_y
            
            if not (0 <= draw_x <= self.canvas.winfo_width() and 0 <= draw_y <= self.canvas.winfo_height()):
                self.events.points.append(None)
                self.events.current_pos = [0, 0]
                self.events.points.append((0, 0, now))

        self.events.points = [p for p in self.events.points if p is None or now - p[2] <= lifespan]
        self.events.clicks = [c for c in self.events.clicks if now - c[3] <= lifespan]
        
        segments = []
        current_segment = []
        for point in self.events.points:
            if point is None:
                if current_segment:
                    segments.append(current_segment)
                    current_segment = []
            else:
                current_segment.append(point)
        if current_segment:
            segments.append(current_segment)

        # Draw segments based on the selected line style
        for segment in segments:
            if self.settings.config["line_style"] == "original":
                self.draw_original_line(segment, cx, cy)
            elif self.settings.config["line_style"] == "smooth_fade":
                self.draw_smooth_fading_line(segment, cx, cy, now, lifespan)
            elif self.settings.config["line_style"] == "jagged_fade":
                self.draw_jagged_fading_line(segment, cx, cy, now, lifespan)

        for x, y, button, _, pressed in self.events.clicks:
            is_left_click = str(button) == "Button.left"
            
            color = self.settings.config["left_click_color"] if is_left_click and pressed else \
                    self.settings.config["left_click_release_color"] if is_left_click else \
                    self.settings.config["right_click_color"] if pressed else \
                    self.settings.config["right_click_release_color"]
            
            r = self.settings.config["left_click_radius"] if is_left_click and pressed else \
                self.settings.config["left_click_release_radius"] if is_left_click else \
                self.settings.config["right_click_radius"] if pressed else \
                self.settings.config["right_click_release_radius"]
            
            self.canvas.create_oval(cx + x - r, cy + y - r, cx + x + r, cy + y + r, fill=color, outline=color)

        self.root.after(self.settings.config["frame_interval"], self.update_canvas)

    def draw_original_line(self, segment, cx, cy):
        """Draws a non-fading line with a uniform width."""
        if len(segment) > 1:
            coords = [coord for p in segment for coord in (cx + p[0], cy + p[1])]
            self.canvas.create_line(coords, fill=self.settings.config["line_color"], width=self.settings.config["line_width"])

    def draw_smooth_fading_line(self, segment, cx, cy, now, lifespan):
        """Draws a smooth line segment with a width that fades to zero using a single polygon."""
        polygon_points = []
        line_width = self.settings.config["line_width"]

        for i in range(len(segment)):
            p = segment[i]
            age = now - p[2]
            fade_factor = max(0.0, 1.0 - (age / lifespan))
            width = line_width * fade_factor

            if i > 0:
                prev_p = segment[i-1]
                dx = p[0] - prev_p[0]
                dy = p[1] - prev_p[1]
                dist = math.sqrt(dx**2 + dy**2)
                if dist == 0: continue

                perp_dx = -dy / dist * (width / 2)
                perp_dy = dx / dist * (width / 2)
                
                polygon_points.append((cx + p[0] + perp_dx, cy + p[1] + perp_dy))
                polygon_points.insert(0, (cx + p[0] - perp_dx, cy + p[1] - perp_dy))

        if len(polygon_points) > 2:
            self.canvas.create_polygon(polygon_points, fill=self.settings.config["line_color"], smooth=True)

    def draw_jagged_fading_line(self, segment, cx, cy, now, lifespan):
        """Draws a line segment with a width that fades to zero using a series of polygons."""
        line_width = self.settings.config["line_width"]
        
        for i in range(len(segment) - 1):
            p1 = segment[i]
            p2 = segment[i+1]
            
            # Calculate width for each point based on age
            age1 = now - p1[2]
            fade_factor1 = max(0.0, 1.0 - (age1 / lifespan))
            width1 = line_width * fade_factor1

            age2 = now - p2[2]
            fade_factor2 = max(0.0, 1.0 - (age2 / lifespan))
            width2 = line_width * fade_factor2

            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dist = math.sqrt(dx**2 + dy**2)
            if dist == 0: continue

            # Calculate perpendicular vectors for the polygon corners
            perp_dx1 = -dy / dist * (width1 / 2)
            perp_dy1 = dx / dist * (width1 / 2)
            
            perp_dx2 = -dy / dist * (width2 / 2)
            perp_dy2 = dx / dist * (width2 / 2)
            
            # Define polygon points for the current segment
            poly_points = [
                cx + p1[0] - perp_dx1, cy + p1[1] - perp_dy1,
                cx + p1[0] + perp_dx1, cy + p1[1] + perp_dy1,
                cx + p2[0] + perp_dx2, cy + p2[1] + perp_dy2,
                cx + p2[0] - perp_dx2, cy + p2[1] - perp_dy2
            ]

            self.canvas.create_polygon(poly_points, fill=self.settings.config["line_color"], outline='', smooth=True)

class SettingsPanel:
    """A Toplevel window for managing application settings."""
    TK_VAR_TYPES = {
        bool: BooleanVar,
        int: IntVar,
        float: DoubleVar,
        str: StringVar
    }

    def __init__(self, parent, config, apply_callback):
        self.parent = parent
        self.config = config
        self.apply_callback = apply_callback
        self.settings_window = Toplevel(parent)
        self.settings_vars = {}
        self._setup_window()
        self._create_ui()

    def _setup_window(self):
        """Sets up the Toplevel window properties."""
        self.settings_window.title("Settings")
        self.settings_window.transient(self.parent)
        self.settings_window.grab_set()
        self.settings_window.protocol("WM_DELETE_WINDOW", self.close_window)

    def get_toplevel_window(self):
        """Returns the Toplevel window widget."""
        return self.settings_window

    def _create_ui(self):
        """Builds the settings UI using a grid layout."""
        main_frame = Frame(self.settings_window, padx=10, pady=10)
        main_frame.pack(fill="both", expand=True)

        sections = [
            ("General Settings", ["line_lifespan", "frame_interval", "canvas_bg_color", "coordinate_multiplier"]),
            ("Appearance", ["line_width", "line_color", "line_style"]),
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

    def _create_setting_field(self, parent_frame, label_text, key, row):
        """Helper to create a single setting field."""
        is_color = "color" in key
        var_type = self.TK_VAR_TYPES.get(type(self.config[key]), StringVar)
        var = var_type(value=self.config[key])
        self.settings_vars[key] = var

        Label(parent_frame, text=label_text).grid(row=row, column=0, sticky="w", padx=5, pady=2)
        
        if is_color:
            Button(parent_frame, text="Choose", command=lambda: self._choose_color(var)).grid(row=row, column=1, padx=5, pady=2)
        elif key == "line_style":
            choices = ["original", "smooth_fade", "jagged_fade"]
            var.set(self.config[key])
            OptionMenu(parent_frame, var, *choices).grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        else:
            Entry(parent_frame, textvariable=var, width=10).grid(row=row, column=1, padx=5, pady=2)

    def _choose_color(self, color_var):
        """Opens color chooser and updates the color variable."""
        color_code = colorchooser.askcolor(title="Choose Color")[1]
        if color_code:
            color_var.set(color_code)

    def apply_and_close(self):
        """Applies settings and then closes the window."""
        new_config = {}
        for key, var in self.settings_vars.items():
            value = var.get()
            new_config[key] = value
        
        self.apply_callback(new_config)
        self.close_window()
        
    def close_window(self):
        """Destroys the settings Toplevel window."""
        self.settings_window.destroy()

class Application:
    """The main application class that orchestrates all components."""
    def __init__(self):
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
            "left_click_release_color": "green",
            "right_click_release_color": "lime green",
            "left_click_release_radius": 3,
            "right_click_release_radius": 3,
            "coordinate_multiplier": 1.0,
            "line_style": "smooth_fade",
            "window_width": 800,
            "window_height": 600,
            "window_x": None,
            "window_y": None
        }

        self.root = tk.Tk()
        self.settings_manager = SettingsManager(self.default_config)
        self.event_handler = MouseEventHandler(self.settings_manager)
        self.ui_manager = MouseTrackerUI(self.root, self.settings_manager, self.event_handler)

    def run(self):
        """Starts the application main loop."""
        self.event_handler.start_listener()
        self.ui_manager.update_canvas()
        self.root.mainloop()

if __name__ == "__main__":
    app = Application()
    app.run()