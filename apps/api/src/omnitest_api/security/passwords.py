from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# Hash giả dùng khi email không tồn tại, để thời gian phản hồi tương đương (chống dò tài khoản).
_DUMMY_HASH = _hasher.hash("omnitest-dummy-password")

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự")
    if password.lower() == password or password.upper() == password:
        problems.append("Mật khẩu phải có cả chữ hoa và chữ thường")
    if not any(c.isdigit() for c in password):
        problems.append("Mật khẩu phải có ít nhất một chữ số")
    return problems
