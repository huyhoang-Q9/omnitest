"""Lệnh quản trị: tạo quản trị hệ thống đầu tiên, sinh master key.

Mật khẩu đọc từ biến môi trường OMNITEST_ADMIN_PASSWORD hoặc nhập ẩn, không nhận qua tham số dòng lệnh
(tránh lộ trong lịch sử shell và danh sách tiến trình).
"""

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import func, select

from omnitest_api.db import get_sessionmaker
from omnitest_api.models import User
from omnitest_api.schemas import normalize_email
from omnitest_api.security.crypto import generate_master_key
from omnitest_api.security.passwords import hash_password, password_problems


async def _create_admin(email: str, full_name: str, password: str) -> int:
    async with get_sessionmaker()() as db:
        if await db.scalar(select(User.id).where(func.lower(User.email) == email.lower())):
            print(f"Email {email} đã tồn tại, không thay đổi gì.", file=sys.stderr)
            return 1
        db.add(
            User(
                email=email.lower(),
                full_name=full_name,
                password_hash=hash_password(password),
                is_system_admin=True,
            )
        )
        await db.commit()
    print(f"Đã tạo quản trị hệ thống {email}.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="omnitest-api")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ca = sub.add_parser("create-admin", help="Tạo tài khoản quản trị hệ thống")
    ca.add_argument("--email", required=True)
    ca.add_argument("--name", default="Quản trị hệ thống")
    sub.add_parser("gen-master-key", help="Sinh OMNITEST_MASTER_KEY mới (32 byte)")
    args = parser.parse_args()

    if args.cmd == "gen-master-key":
        print(generate_master_key())
        return
    try:
        email = normalize_email(args.email)
    except ValueError as exc:
        sys.exit(str(exc))
    password = os.environ.get("OMNITEST_ADMIN_PASSWORD") or getpass.getpass("Mật khẩu: ")
    if problems := password_problems(password):
        sys.exit("; ".join(problems))
    sys.exit(asyncio.run(_create_admin(email, args.name, password)))


if __name__ == "__main__":
    main()
