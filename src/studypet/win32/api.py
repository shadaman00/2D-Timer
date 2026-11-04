"""64-bit Windows 전용 안전 ctypes 바인딩 명세 (DEVELOPMENT_PLAN.md 4-2)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

# 모듈 전용 DLL 로드 (공유 windll 객체 사용 금지)
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
shcore = ctypes.WinDLL("shcore", use_last_error=True)
wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
winmm = ctypes.WinDLL("winmm", use_last_error=True)
comdlg32 = ctypes.WinDLL("comdlg32", use_last_error=True)
comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)

# 64-bit 포인터/정수 타입
LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
LONG_PTR = ctypes.c_ssize_t
UINT_PTR = ctypes.c_size_t
ULONG_PTR = ctypes.c_size_t
HRESULT = ctypes.c_long

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, WPARAM, LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), LPARAM)

HWND_TOPMOST = wt.HWND(-1)
INVALID_HANDLE_VALUE = wt.HANDLE(-1).value
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

# --- 상수 정의 (4-2) ---
# 창 스타일
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
WS_BORDER = 0x00800000
WS_MINIMIZEBOX = 0x00020000

# 확장 스타일
WS_EX_DLGMODALFRAME = 0x00000001
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_CONTROLPARENT = 0x00010000
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

# 메시지
WM_NULL = 0x0000
WM_CREATE = 0x0001
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_PAINT = 0x000F
WM_SETTINGCHANGE = 0x001A
WM_MOUSEACTIVATE = 0x0021
WM_SETFONT = 0x0030
WM_NOTIFY = 0x004E
WM_DISPLAYCHANGE = 0x007E
WM_KEYDOWN = 0x0100
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A
WM_CAPTURECHANGED = 0x0215
WM_POWERBROADCAST = 0x0218
WM_MOUSELEAVE = 0x02A3
WM_WTSSESSION_CHANGE = 0x02B1
WM_DPICHANGED = 0x02E0
WM_HOTKEY = 0x0312
WM_APP = 0x8000

TME_LEAVE = 0x00000002

# 앱 전용 메시지
WM_APP_TRAY = WM_APP + 1
WM_APP_SUMMON = WM_APP + 2
WM_APP_POST_START = WM_APP + 3

# 기타 상수
GWL_STYLE = -16
GWL_EXSTYLE = -20
MA_NOACTIVATE = 3
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
MONITOR_DEFAULTTOPRIMARY = 1
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0
NONANTIALIASED_QUALITY = 3
TRANSPARENT = 1
FR_PRIVATE = 0x10

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_MENU = 0x12

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY = 0x0080
TPM_RETURNCMD = 0x0100
MF_STRING = 0x0000
MF_CHECKED = 0x0008
MF_GRAYED = 0x0001
MF_SEPARATOR = 0x0800

PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0

SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NO_CONSOLE = 0x00008000
INFINITE = 0xFFFFFFFF
ERROR_ALREADY_EXISTS = 183
ERROR_CANCELLED = 1223

MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_YESNOCANCEL = 0x00000003
MB_ICONERROR = 0x00000010
MB_ICONQUESTION = 0x00000020
MB_ICONWARNING = 0x00000030
MB_ICONINFORMATION = 0x00000040
MB_TOPMOST = 0x00040000
IDOK = 1
IDCANCEL = 2
IDYES = 6
IDNO = 7

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
IDC_ARROW = 32512

SND_ASYNC = 0x0001
SND_NODEFAULT = 0x0002
SND_MEMORY = 0x0004
SND_FILENAME = 0x00020000

ICC_LISTVIEW_CLASSES = 0x00000001
ICC_BAR_CLASSES = 0x00000004
ICC_TAB_CLASSES = 0x00000008
ICC_HOTKEY_CLASS = 0x00000040
ICC_STANDARD_CLASSES = 0x00004000

OFN_OVERWRITEPROMPT = 0x00000002
OFN_NOCHANGEDIR = 0x00000008
OFN_PATHMUSTEXIST = 0x00000800


# --- 구조체 정의 (4-2) ---
POINT = wt.POINT
SIZE = wt.SIZE
RECT = wt.RECT
MSG = wt.MSG
FILETIME = wt.FILETIME


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm", wt.HICON),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wt.DWORD * 1),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
    ]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("dwTime", wt.DWORD),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", wt.HICON),
        ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64),
        ("dwInfoFlags", wt.DWORD),
        ("guidItem", ctypes.c_ubyte * 16),
        ("hBalloonIcon", wt.HICON),
    ]


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("fMask", wt.ULONG),
        ("hwnd", wt.HWND),
        ("lpVerb", wt.LPCWSTR),
        ("lpFile", wt.LPCWSTR),
        ("lpParameters", wt.LPCWSTR),
        ("lpDirectory", wt.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wt.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wt.LPCWSTR),
        ("hkeyClass", wt.HKEY),
        ("dwHotKey", wt.DWORD),
        ("hIconOrMonitor", wt.HANDLE),
        ("hProcess", wt.HANDLE),
    ]


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wt.DWORD),
        ("hwndOwner", wt.HWND),
        ("hInstance", wt.HINSTANCE),
        ("lpstrFilter", wt.LPCWSTR),
        ("lpstrCustomFilter", wt.LPWSTR),
        ("nMaxCustFilter", wt.DWORD),
        ("nFilterIndex", wt.DWORD),
        ("lpstrFile", wt.LPWSTR),
        ("nMaxFile", wt.DWORD),
        ("lpstrFileTitle", wt.LPWSTR),
        ("nMaxFileTitle", wt.DWORD),
        ("lpstrInitialDir", wt.LPCWSTR),
        ("lpstrTitle", wt.LPCWSTR),
        ("Flags", wt.DWORD),
        ("nFileOffset", wt.WORD),
        ("nFileExtension", wt.WORD),
        ("lpstrDefExt", wt.LPCWSTR),
        ("lCustData", LPARAM),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", wt.LPCWSTR),
        ("pvReserved", ctypes.c_void_p),
        ("dwReserved", wt.DWORD),
        ("FlagsEx", wt.DWORD),
    ]


class CHOOSECOLORW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wt.DWORD),
        ("hwndOwner", wt.HWND),
        ("hInstance", wt.HWND),
        ("rgbResult", wt.DWORD),
        ("lpCustColors", ctypes.POINTER(wt.DWORD)),
        ("Flags", wt.DWORD),
        ("lCustData", LPARAM),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", wt.LPCWSTR),
    ]


class ACTCTXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.ULONG),
        ("dwFlags", wt.DWORD),
        ("lpSource", wt.LPCWSTR),
        ("wProcessorArchitecture", wt.USHORT),
        ("wLangId", wt.USHORT),
        ("lpAssemblyDirectory", wt.LPCWSTR),
        ("lpResourceName", wt.LPCWSTR),
        ("lpApplicationName", wt.LPCWSTR),
        ("hModule", wt.HMODULE),
    ]


class INITCOMMONCONTROLSEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("dwICC", wt.DWORD),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wt.HDC),
        ("fErase", wt.BOOL),
        ("rcPaint", wt.RECT),
        ("fRestore", wt.BOOL),
        ("fIncUpdate", wt.BOOL),
        ("rgbReserved", ctypes.c_ubyte * 32),
    ]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("hwndTrack", wt.HWND),
        ("dwHoverTime", wt.DWORD),
    ]


# --- 함수 원형 선언 (4-2) ---
# user32
user32.TrackMouseEvent.restype = wt.BOOL
user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]

user32.RegisterClassExW.restype = wt.ATOM
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]

user32.UnregisterClassW.restype = wt.BOOL
user32.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]

user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]

user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, WPARAM, LPARAM]

user32.DestroyWindow.restype = wt.BOOL
user32.DestroyWindow.argtypes = [wt.HWND]

user32.ShowWindow.restype = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]

user32.UpdateWindow.restype = wt.BOOL
user32.UpdateWindow.argtypes = [wt.HWND]

user32.GetMessageW.restype = wt.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT]

user32.PeekMessageW.restype = wt.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]

user32.TranslateMessage.restype = wt.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]

user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]

user32.IsDialogMessageW.restype = wt.BOOL
user32.IsDialogMessageW.argtypes = [wt.HWND, ctypes.POINTER(MSG)]

user32.PostMessageW.restype = wt.BOOL
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, WPARAM, LPARAM]

user32.SendMessageW.restype = LRESULT
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, WPARAM, LPARAM]

user32.PostQuitMessage.restype = None
user32.PostQuitMessage.argtypes = [ctypes.c_int]

user32.SetTimer.restype = UINT_PTR
user32.SetTimer.argtypes = [wt.HWND, UINT_PTR, wt.UINT, ctypes.c_void_p]

user32.KillTimer.restype = wt.BOOL
user32.KillTimer.argtypes = [wt.HWND, UINT_PTR]

user32.UpdateLayeredWindow.restype = wt.BOOL
user32.UpdateLayeredWindow.argtypes = [
    wt.HWND, wt.HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE),
    wt.HDC, ctypes.POINTER(POINT), wt.COLORREF, ctypes.POINTER(BLENDFUNCTION), wt.DWORD,
]

user32.SetWindowPos.restype = wt.BOOL
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]

user32.GetWindowLongPtrW.restype = LONG_PTR
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]

user32.SetWindowLongPtrW.restype = LONG_PTR
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, LONG_PTR]

user32.GetCursorPos.restype = wt.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]

user32.SetCapture.restype = wt.HWND
user32.SetCapture.argtypes = [wt.HWND]

user32.ReleaseCapture.restype = wt.BOOL
user32.ReleaseCapture.argtypes = []

user32.GetCapture.restype = wt.HWND
user32.GetCapture.argtypes = []

user32.GetAsyncKeyState.restype = wt.SHORT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

user32.GetKeyState.restype = wt.SHORT
user32.GetKeyState.argtypes = [ctypes.c_int]

user32.MonitorFromPoint.restype = wt.HMONITOR
user32.MonitorFromPoint.argtypes = [POINT, wt.DWORD]

user32.GetMonitorInfoW.restype = wt.BOOL
user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]

user32.EnumDisplayMonitors.restype = wt.BOOL
user32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.POINTER(RECT), MONITORENUMPROC, LPARAM]

user32.SetProcessDpiAwarenessContext.restype = wt.BOOL
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]

user32.GetLastInputInfo.restype = wt.BOOL
user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]

user32.RegisterHotKey.restype = wt.BOOL
user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]

user32.UnregisterHotKey.restype = wt.BOOL
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]

user32.MessageBoxW.restype = ctypes.c_int
user32.MessageBoxW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]

user32.MessageBeep.restype = wt.BOOL
user32.MessageBeep.argtypes = [wt.UINT]

user32.LoadImageW.restype = wt.HANDLE
user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT]

user32.LoadCursorW.restype = wt.HANDLE
user32.LoadCursorW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]

user32.DestroyIcon.restype = wt.BOOL
user32.DestroyIcon.argtypes = [wt.HICON]

user32.CreatePopupMenu.restype = wt.HMENU
user32.CreatePopupMenu.argtypes = []

user32.AppendMenuW.restype = wt.BOOL
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, UINT_PTR, wt.LPCWSTR]

user32.TrackPopupMenu.restype = wt.BOOL
user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, ctypes.c_void_p]

user32.DestroyMenu.restype = wt.BOOL
user32.DestroyMenu.argtypes = [wt.HMENU]

user32.SetForegroundWindow.restype = wt.BOOL
user32.SetForegroundWindow.argtypes = [wt.HWND]

user32.FindWindowW.restype = wt.HWND
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]

user32.RegisterWindowMessageW.restype = wt.UINT
user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]

user32.WindowFromPoint.restype = wt.HWND
user32.WindowFromPoint.argtypes = [POINT]

user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]

user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]

user32.FillRect.restype = ctypes.c_int
user32.FillRect.argtypes = [wt.HDC, ctypes.POINTER(RECT), wt.HBRUSH]

user32.InvalidateRect.restype = wt.BOOL
user32.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(RECT), wt.BOOL]

user32.BeginPaint.restype = wt.HDC
user32.BeginPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]

user32.EndPaint.restype = wt.BOOL
user32.EndPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]

user32.ScreenToClient.restype = wt.BOOL
user32.ScreenToClient.argtypes = [wt.HWND, ctypes.POINTER(POINT)]

user32.GetWindowRect.restype = wt.BOOL
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]

user32.GetClientRect.restype = wt.BOOL
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]

user32.SetWindowTextW.restype = wt.BOOL
user32.SetWindowTextW.argtypes = [wt.HWND, wt.LPCWSTR]

user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]

user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [wt.HWND]

user32.EnableWindow.restype = wt.BOOL
user32.EnableWindow.argtypes = [wt.HWND, wt.BOOL]

user32.SetFocus.restype = wt.HWND
user32.SetFocus.argtypes = [wt.HWND]

user32.GetDlgItem.restype = wt.HWND
user32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]

user32.DrawTextW.restype = ctypes.c_int
user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(RECT), wt.UINT]

# gdi32
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]

gdi32.DeleteDC.restype = wt.BOOL
gdi32.DeleteDC.argtypes = [wt.HDC]

gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
    ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD,
]

gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]

gdi32.BitBlt.restype = wt.BOOL
gdi32.BitBlt.argtypes = [
    wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD,
]

gdi32.CreateSolidBrush.restype = wt.HBRUSH
gdi32.CreateSolidBrush.argtypes = [wt.COLORREF]

gdi32.CreatePen.restype = wt.HPEN
gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wt.COLORREF]

gdi32.MoveToEx.restype = wt.BOOL
gdi32.MoveToEx.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]

gdi32.LineTo.restype = wt.BOOL
gdi32.LineTo.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]

gdi32.GetStockObject.restype = wt.HGDIOBJ
gdi32.GetStockObject.argtypes = [ctypes.c_int]

gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]

gdi32.DeleteObject.restype = wt.BOOL
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]

gdi32.CreateFontW.restype = wt.HFONT
gdi32.CreateFontW.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD,
    wt.LPCWSTR,
]

gdi32.TextOutW.restype = wt.BOOL
gdi32.TextOutW.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, wt.LPCWSTR, ctypes.c_int]

gdi32.GetTextExtentPoint32W.restype = wt.BOOL
gdi32.GetTextExtentPoint32W.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(SIZE)]

gdi32.SetBkMode.restype = ctypes.c_int
gdi32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]

gdi32.SetTextColor.restype = wt.COLORREF
gdi32.SetTextColor.argtypes = [wt.HDC, wt.COLORREF]

gdi32.AddFontResourceExW.restype = ctypes.c_int
gdi32.AddFontResourceExW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.c_void_p]

gdi32.RemoveFontResourceExW.restype = wt.BOOL
gdi32.RemoveFontResourceExW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.c_void_p]

gdi32.GdiFlush.restype = wt.BOOL
gdi32.GdiFlush.argtypes = []

# kernel32
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]

kernel32.CloseHandle.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]

kernel32.QueryUnbiasedInterruptTime.restype = wt.BOOL
kernel32.QueryUnbiasedInterruptTime.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]

kernel32.GetTickCount.restype = wt.DWORD
kernel32.GetTickCount.argtypes = []

kernel32.WaitForSingleObject.restype = wt.DWORD
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]

kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]

kernel32.GetCurrentProcess.restype = wt.HANDLE
kernel32.GetCurrentProcess.argtypes = []

kernel32.GetProcessTimes.restype = wt.BOOL
kernel32.GetProcessTimes.argtypes = [
    wt.HANDLE,
    ctypes.POINTER(FILETIME),
    ctypes.POINTER(FILETIME),
    ctypes.POINTER(FILETIME),
    ctypes.POINTER(FILETIME),
]

kernel32.GetSystemTimeAsFileTime.restype = None
kernel32.GetSystemTimeAsFileTime.argtypes = [ctypes.POINTER(FILETIME)]

kernel32.CreateActCtxW.restype = wt.HANDLE
kernel32.CreateActCtxW.argtypes = [ctypes.POINTER(ACTCTXW)]

kernel32.ActivateActCtx.restype = wt.BOOL
kernel32.ActivateActCtx.argtypes = [wt.HANDLE, ctypes.POINTER(ULONG_PTR)]

kernel32.DeactivateActCtx.restype = wt.BOOL
kernel32.DeactivateActCtx.argtypes = [wt.DWORD, ULONG_PTR]

kernel32.ReleaseActCtx.restype = None
kernel32.ReleaseActCtx.argtypes = [wt.HANDLE]

# shell32
shell32.Shell_NotifyIconW.restype = wt.BOOL
shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]

shell32.ShellExecuteExW.restype = wt.BOOL
shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]

# shcore
shcore.GetDpiForMonitor.restype = HRESULT
shcore.GetDpiForMonitor.argtypes = [wt.HMONITOR, ctypes.c_int, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT)]

shcore.SetProcessDpiAwareness.restype = HRESULT
shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]

# wtsapi32
wtsapi32.WTSRegisterSessionNotification.restype = wt.BOOL
wtsapi32.WTSRegisterSessionNotification.argtypes = [wt.HWND, wt.DWORD]

wtsapi32.WTSUnRegisterSessionNotification.restype = wt.BOOL
wtsapi32.WTSUnRegisterSessionNotification.argtypes = [wt.HWND]

# winmm
winmm.PlaySoundW.restype = wt.BOOL
winmm.PlaySoundW.argtypes = [ctypes.c_void_p, wt.HMODULE, wt.DWORD]

# comdlg32
comdlg32.GetSaveFileNameW.restype = wt.BOOL
comdlg32.GetSaveFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]

comdlg32.ChooseColorW.restype = wt.BOOL
comdlg32.ChooseColorW.argtypes = [ctypes.POINTER(CHOOSECOLORW)]

# comctl32
comctl32.InitCommonControlsEx.restype = wt.BOOL
comctl32.InitCommonControlsEx.argtypes = [ctypes.POINTER(INITCOMMONCONTROLSEX)]


def filetime_to_100ns(ft: FILETIME) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


def get_cold_start_ms() -> float:
    """프로세스 생성 시각(GetProcessTimes)부터 현재까지의 경과 시간(ms)을 계산한다."""
    creation = FILETIME()
    exit_t = FILETIME()
    kernel_t = FILETIME()
    user_t = FILETIME()
    now_ft = FILETIME()
    kernel32.GetSystemTimeAsFileTime(ctypes.byref(now_ft))
    if not kernel32.GetProcessTimes(
        kernel32.GetCurrentProcess(),
        ctypes.byref(creation),
        ctypes.byref(exit_t),
        ctypes.byref(kernel_t),
        ctypes.byref(user_t),
    ):
        return -1.0
    diff_100ns = filetime_to_100ns(now_ft) - filetime_to_100ns(creation)
    return max(0.0, diff_100ns / 10_000.0)

