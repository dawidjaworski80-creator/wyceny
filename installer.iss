[Setup]
AppName=MSQuotes
AppVersion=1.0
AppPublisher=247 Machining Services
DefaultDirName={localappdata}\MSQuotes
DefaultGroupName=MSQuotes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=MSQuotes_Setup
Compression=lzma2
SolidCompression=yes
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\MSQuotes.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\MSQuotes\*"; DestDir: "{app}"; Excludes: "*.json"; Flags: recursesubdirs ignoreversion
; Data and settings are only installed once so upgrades never overwrite user data.
Source: "cnc_settings.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "quotes_data.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "customers_data.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "suppliers_data.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\MSQuotes"; Filename: "{app}\MSQuotes.exe"
Name: "{autodesktop}\MSQuotes"; Filename: "{app}\MSQuotes.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MSQuotes.exe"; Description: "Launch MSQuotes"; Flags: nowait postinstall skipifsilent
