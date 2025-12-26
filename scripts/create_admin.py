from app.database import SessionLocal
from app.core.security import hash_password
from app.models import User

import sys


def ensure_admin(email: str, password: str, name: str = "Admin", nickname: str = "Admin"):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if not u:
            u = User(
                email=email,
                password_hash=hash_password(password),
                name=name,
                nickname=nickname,
                is_admin=True,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            print(f"[OK] Created admin user id={u.id} email={email}")
        else:
            if not getattr(u, "is_admin", False):
                u.is_admin = True
                db.commit()
                print(f"[OK] Promoted existing user to admin: {email}")
            else:
                print(f"[OK] Already admin: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_admin.py <email> <password> [name] [nickname]")
        sys.exit(1)
    email = sys.argv[1]
    password = sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else "Admin"
    nickname = sys.argv[4] if len(sys.argv) > 4 else "Admin"
    ensure_admin(email, password, name, nickname)
