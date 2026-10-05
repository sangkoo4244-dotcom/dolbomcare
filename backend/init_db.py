import os

from app import models  # noqa: F401  (registers every table on Base)
from app.api.users import get_password_hash
from app.database import Base, SessionLocal, engine


def main():
    Base.metadata.create_all(bind=engine)

    email = os.getenv("BOOTSTRAP_MANAGER_EMAIL")
    password = os.getenv("BOOTSTRAP_MANAGER_PASSWORD")
    if not email or not password:
        print("init_db: tables ready (no bootstrap manager configured)")
        return

    db = SessionLocal()
    try:
        if db.query(models.User).count() > 0:
            print("init_db: users already exist, skipping bootstrap")
            return
        center = models.Center(name=os.getenv("BOOTSTRAP_CENTER_NAME", "돌봄케어 센터"))
        db.add(center)
        db.flush()
        db.add(models.User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=os.getenv("BOOTSTRAP_MANAGER_NAME", "센터장"),
            role="center_manager",
            center_id=center.id,
            is_active=True,
        ))
        db.commit()
        print("init_db: bootstrap manager created")
    finally:
        db.close()


if __name__ == "__main__":
    main()
