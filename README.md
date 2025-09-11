100% AI generated code.  Gemini 2.5 Flash.  Consider this (basically) instantly abandoned, do what you want with the code.

Features:
- Configurable line (color, width, 4 styles, time to live, frame interval, sensitivity)
- Configurable background color
- Use PNG images as custom cursor/click indicators
  - basic customizable dots if no custom image (color and size)
  - customize press and release dots/images
- Toggleable automatic re-centering
- Saves window size and location
- Captures raw mouse input
  - Displays movement even when cursor is locked/at screen edge


This program tracks mouse input and displays movement as lines and mouse down and up inputs as dots.  The line/dot size and colors are configurable and save to a text file.  There are 4 different modes, a smooth shrinking/fading line, a basic vanilla vanishing line, and a fading jaggy line that looks a bit different than the smooth fade, and a non-fading version of the jaggy line.



Slightly outdated media:

<img width="768" height="419" alt="image" src="https://github.com/user-attachments/assets/86e46593-7147-458d-8eb7-168aaf5d7e8c" />
<img width="272" height="710" alt="image" src="https://github.com/user-attachments/assets/7066a654-05ca-412e-b907-7bdc93485b7d" />

Usage example with OBS on the directional slasher Swordai (using crop and color-mask filters on the tracker window in OBS)

https://github.com/user-attachments/assets/3e0eceae-b649-4981-8878-dcd9ae051807

