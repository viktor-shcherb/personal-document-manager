from __future__ import annotations

import ctypes
import sys
from pathlib import Path


ERR_SEC_ITEM_NOT_FOUND = -25300
SECURITY_FRAMEWORK = Path("/System/Library/Frameworks/Security.framework/Security")
CORE_FOUNDATION_FRAMEWORK = Path(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)


class KeychainError(RuntimeError):
    pass


class _SecurityFramework:
    def __init__(self):
        if sys.platform != "darwin":
            raise KeychainError("macOS Keychain is available only on macOS")

        self.security = ctypes.CDLL(str(SECURITY_FRAMEWORK))
        self.core_foundation = ctypes.CDLL(str(CORE_FOUNDATION_FRAMEWORK))

        self.security.SecKeychainFindGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
        self.security.SecKeychainAddGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
        self.security.SecKeychainItemModifyAttributesAndData.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        self.security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
        self.security.SecKeychainItemDelete.argtypes = [ctypes.c_void_p]
        self.security.SecKeychainItemDelete.restype = ctypes.c_int32
        self.security.SecKeychainItemFreeContent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self.security.SecKeychainItemFreeContent.restype = ctypes.c_int32
        self.core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        self.core_foundation.CFRelease.restype = None

    @staticmethod
    def _names(service: str, account: str) -> tuple[bytes, bytes]:
        return service.encode("utf-8"), account.encode("utf-8")

    def get(self, service: str, account: str) -> str:
        service_bytes, account_bytes = self._names(service, account)
        password_length = ctypes.c_uint32()
        password_data = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(
            None,
            len(service_bytes),
            service_bytes,
            len(account_bytes),
            account_bytes,
            ctypes.byref(password_length),
            ctypes.byref(password_data),
            None,
        )
        if status:
            raise KeychainError(
                f"Keychain item not found for service={service!r}, "
                f"account={account!r} (status {status})"
            )
        try:
            value = ctypes.string_at(password_data, password_length.value)
            return value.decode("utf-8")
        finally:
            self.security.SecKeychainItemFreeContent(None, password_data)

    def set(self, service: str, account: str, value: str) -> None:
        service_bytes, account_bytes = self._names(service, account)
        value_bytes = value.encode("utf-8")
        value_buffer = ctypes.create_string_buffer(value_bytes)
        value_pointer = ctypes.cast(value_buffer, ctypes.c_void_p)
        item = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(
            None,
            len(service_bytes),
            service_bytes,
            len(account_bytes),
            account_bytes,
            None,
            None,
            ctypes.byref(item),
        )
        if status == ERR_SEC_ITEM_NOT_FOUND:
            status = self.security.SecKeychainAddGenericPassword(
                None,
                len(service_bytes),
                service_bytes,
                len(account_bytes),
                account_bytes,
                len(value_bytes),
                value_pointer,
                None,
            )
        elif status == 0:
            try:
                status = self.security.SecKeychainItemModifyAttributesAndData(
                    item,
                    None,
                    len(value_bytes),
                    value_pointer,
                )
            finally:
                self.core_foundation.CFRelease(item)
        if status:
            raise KeychainError(f"Unable to update macOS Keychain (status {status})")

    def delete(self, service: str, account: str) -> None:
        service_bytes, account_bytes = self._names(service, account)
        item = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(
            None,
            len(service_bytes),
            service_bytes,
            len(account_bytes),
            account_bytes,
            None,
            None,
            ctypes.byref(item),
        )
        if status == ERR_SEC_ITEM_NOT_FOUND:
            return
        if status:
            raise KeychainError(f"Unable to find macOS Keychain item (status {status})")
        try:
            status = self.security.SecKeychainItemDelete(item)
        finally:
            self.core_foundation.CFRelease(item)
        if status:
            raise KeychainError(
                f"Unable to delete macOS Keychain item (status {status})"
            )


class MacOSKeychain:
    def __init__(self, backend=None):
        self.backend = backend or _SecurityFramework()

    def get(self, service: str, account: str) -> str:
        return self.backend.get(service, account)

    def set(self, service: str, account: str, value: str) -> None:
        self.backend.set(service, account, value)

    def delete(self, service: str, account: str) -> None:
        self.backend.delete(service, account)
