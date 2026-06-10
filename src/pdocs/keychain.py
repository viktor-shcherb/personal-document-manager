from __future__ import annotations

import ctypes
import hmac
import secrets
import sys
from pathlib import Path


ERR_SEC_ITEM_NOT_FOUND = -25300
ERR_SEC_DUPLICATE_ITEM = -25299
SECURITY_FRAMEWORK = Path("/System/Library/Frameworks/Security.framework/Security")
CORE_FOUNDATION_FRAMEWORK = Path(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)


class KeychainError(RuntimeError):
    pass


class KeychainItemNotFoundError(KeychainError):
    pass


class KeychainItemExistsError(KeychainError):
    pass


class KeychainConflictError(KeychainError):
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
            error = (
                f"Unable to read Keychain item for service={service!r}, "
                f"account={account!r} (status {status})"
            )
            if status == ERR_SEC_ITEM_NOT_FOUND:
                raise KeychainItemNotFoundError(error)
            raise KeychainError(error)
        try:
            value = ctypes.string_at(password_data, password_length.value)
            return value.decode("utf-8")
        finally:
            self.security.SecKeychainItemFreeContent(None, password_data)

    def create(self, service: str, account: str, value: str) -> None:
        service_bytes, account_bytes = self._names(service, account)
        value_bytes = value.encode("utf-8")
        value_buffer = ctypes.create_string_buffer(value_bytes)
        value_pointer = ctypes.cast(value_buffer, ctypes.c_void_p)
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
        if status == ERR_SEC_DUPLICATE_ITEM:
            raise KeychainItemExistsError(
                f"Keychain item already exists for service={service!r}, "
                f"account={account!r}"
            )
        if status:
            raise KeychainError(
                f"Unable to create macOS Keychain item (status {status})"
            )

    def replace(
        self,
        service: str,
        account: str,
        value: str,
        *,
        expected: str,
    ) -> None:
        current = self.get(service, account)
        if not hmac.compare_digest(current, expected):
            raise KeychainConflictError(
                f"Keychain item changed before replacement for service={service!r}, "
                f"account={account!r}"
            )

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
            raise KeychainConflictError(
                f"Keychain item disappeared before replacement for "
                f"service={service!r}, account={account!r}"
            )
        if status:
            raise KeychainError(f"Unable to find macOS Keychain item (status {status})")
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
            raise KeychainError(
                f"Unable to replace macOS Keychain item (status {status})"
            )

    def delete(self, service: str, account: str, *, expected: str) -> None:
        current = self.get(service, account)
        if not hmac.compare_digest(current, expected):
            raise KeychainConflictError(
                f"Keychain item changed before deletion for service={service!r}, "
                f"account={account!r}"
            )

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
            raise KeychainConflictError(
                f"Keychain item disappeared before deletion for service={service!r}, "
                f"account={account!r}"
            )
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

    def get_optional(self, service: str, account: str) -> str | None:
        try:
            return self.get(service, account)
        except (KeychainItemNotFoundError, KeyError):
            return None

    def create(self, service: str, account: str, value: str) -> None:
        self.backend.create(service, account, value)

    def replace(
        self,
        service: str,
        account: str,
        value: str,
        *,
        expected: str,
    ) -> None:
        self.backend.replace(service, account, value, expected=expected)

    def delete(self, service: str, account: str, *, expected: str) -> None:
        self.backend.delete(service, account, expected=expected)

    def repair_access(self, service: str, account: str) -> None:
        value = self.get(service, account)
        if not value:
            raise KeychainError("Keychain item is empty")

        backup_account = f"{account}.pdocs-repair-backup-{secrets.token_hex(8)}"
        self.create(service, backup_account, value)
        if not hmac.compare_digest(self.get(service, backup_account), value):
            raise KeychainError("Unable to verify temporary Keychain repair backup")

        original_verified = True
        try:
            self.delete(service, account, expected=value)
            original_verified = False
            original_created = False
            try:
                self.create(service, account, value)
                original_created = True
                if not hmac.compare_digest(self.get(service, account), value):
                    raise KeychainError("Recreated Keychain item failed verification")
                original_verified = True
            except Exception as error:
                if not original_created:
                    try:
                        self.create(service, account, value)
                        if not hmac.compare_digest(self.get(service, account), value):
                            raise KeychainError(
                                "Restored Keychain item failed verification"
                            )
                        original_verified = True
                    except Exception as restore_error:
                        raise KeychainError(
                            "Keychain access repair failed and automatic restoration "
                            f"failed; recovery copy remains at service={service!r}, "
                            f"account={backup_account!r}: {restore_error}"
                        ) from error
                if original_verified:
                    raise
                raise KeychainError(
                    "Keychain access repair could not verify the recreated item; "
                    f"recovery copy remains at service={service!r}, "
                    f"account={backup_account!r}"
                ) from error
        finally:
            if original_verified:
                self.delete(service, backup_account, expected=value)
