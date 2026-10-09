import ctypes
import os
from ctypes import POINTER, Structure, byref, c_char_p, c_size_t, c_uint32, c_void_p
from urllib.parse import quote, urlencode


class _MapiRecipDesc(Structure):
    _fields_ = [
        ("ulReserved", c_uint32),
        ("ulRecipClass", c_uint32),
        ("lpszName", c_char_p),
        ("lpszAddress", c_char_p),
        ("ulEIDSize", c_uint32),
        ("lpEntryID", c_void_p),
    ]


class _MapiFileDesc(Structure):
    _fields_ = [
        ("ulReserved", c_uint32),
        ("flFlags", c_uint32),
        ("nPosition", c_uint32),
        ("lpszPathName", c_char_p),
        ("lpszFileName", c_char_p),
        ("lpFileType", c_void_p),
    ]


class _MapiMessage(Structure):
    _fields_ = [
        ("ulReserved", c_uint32),
        ("lpszSubject", c_char_p),
        ("lpszNoteText", c_char_p),
        ("lpszMessageType", c_char_p),
        ("lpszDateReceived", c_char_p),
        ("lpszConversationID", c_char_p),
        ("flFlags", c_uint32),
        ("lpOriginator", POINTER(_MapiRecipDesc)),
        ("nRecipCount", c_uint32),
        ("lpRecips", POINTER(_MapiRecipDesc)),
        ("nFileCount", c_uint32),
        ("lpFiles", POINTER(_MapiFileDesc)),
    ]


class EmailService:
    @staticmethod
    def open_compose_window(recipient, subject, body, attachment_path):
        if os.name != "nt":
            raise RuntimeError("Opening the default Windows email account is only supported on Windows.")
        if not os.path.isfile(attachment_path):
            raise RuntimeError(f"Email attachment not found: {attachment_path}")

        try:
            win_dll = ctypes.WinDLL
            mapi = win_dll("MAPI32.DLL")
            send_mail = mapi.MAPISendMail
        except (AttributeError, OSError):
            return EmailService._open_mailto(recipient, subject, body)

        recipient_desc = None
        try:
            if recipient:
                recipient_address = ("SMTP:" + recipient).encode("mbcs", errors="replace")
                recipient_desc = _MapiRecipDesc(
                    0,
                    1,
                    recipient_address,
                    recipient_address,
                    0,
                    None,
                )
            subject_bytes = subject.encode("mbcs", errors="replace")
            body_bytes = body.encode("mbcs", errors="replace")
            path_bytes = os.path.abspath(attachment_path).encode("mbcs", errors="replace")
            name_bytes = os.path.basename(attachment_path).encode("mbcs", errors="replace")
        except LookupError as exc:
            raise RuntimeError("The Windows system text encoding is unavailable.") from exc

        file_desc = _MapiFileDesc(
            0,
            0,
            0xFFFFFFFF,
            path_bytes,
            name_bytes,
            None,
        )
        message = _MapiMessage(
            0,
            subject_bytes,
            body_bytes,
            None,
            None,
            None,
            0,
            None,
            1 if recipient_desc else 0,
            ctypes.pointer(recipient_desc) if recipient_desc else None,
            1,
            ctypes.pointer(file_desc),
        )

        send_mail.argtypes = [
            c_void_p,
            c_size_t,
            POINTER(_MapiMessage),
            c_uint32,
            c_size_t,
        ]
        send_mail.restype = c_uint32

        result = send_mail(None, 0, byref(message), 0x00000009, 0)
        if result == 1:
            return None
        if result != 0:
            return EmailService._open_mailto(recipient, subject, body)
        return True

    @staticmethod
    def _open_mailto(recipient, subject, body):
        mailto_url = "mailto:" + quote(recipient, safe="@.+-_") + "?" + urlencode({
            "subject": subject,
            "body": body,
        })
        try:
            os.startfile(mailto_url)
        except (AttributeError, OSError) as exc:
            raise RuntimeError(
                "Windows could not open the default email application. Set a default "
                "email app under Windows Settings > Apps > Default apps, then try again."
            ) from exc
        return False
