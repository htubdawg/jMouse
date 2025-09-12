100% AI generated code.  Gemini 2.5 Flash.  Consider this (basically) instantly abandoned, do what you want with the code.

#### Latest revision was being flagged as a trojan by Windows Defender, I uploaded it to microsoft for review and it has been evaluated as non-malicious
>At this time, the submitted files do not meet our criteria for malware or potentially unwanted applications. The detection has been removed. Please follow the steps below to clear cached detections and obtain the latest malware definitions.
>
>1. Open command prompt as administrator and change directory to c:\Program Files\Windows Defender
>2. Run “MpCmdRun.exe -removedefinitions -dynamicsignatures”
>3. Run "MpCmdRun.exe -SignatureUpdate"
>
>Alternatively, the latest definition is available for download here: https://docs.microsoft.com/microsoft-365/security/defender-endpoint/manage-updates-baselines-microsoft-defender-antivirus"

Virus Total: https://www.virustotal.com/gui/file/299066ac8eaa9c1d78319232047f2eaa50ad8088f953ad9f7cf46acd076a644e?nocache=1

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

<img width="785" height="408" alt="image" src="https://github.com/user-attachments/assets/d0c46b21-0447-4e53-b4ea-66c1f43bb0c8" />

<img width="508" height="428" alt="image" src="https://github.com/user-attachments/assets/f539073f-3887-48f7-a886-4b01db614f7c" />




Usage Examples (game: Swordai):
Using the crop and color/chroma key filters, in OBS, to remove the background and window border.

With NohBoard and OBS Input Overlay plugin:

https://github.com/user-attachments/assets/eaf3e47c-722c-44ed-a417-38ab4f89b8a9

jMouse alone with vanilla settings:

https://github.com/user-attachments/assets/3e0eceae-b649-4981-8878-dcd9ae051807

