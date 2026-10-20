from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import User


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    # Same return (None) for unknown email, wrong password, and inactive user,
    # so the caller cannot tell which one failed.
    user = session.execute(
        select(User).where(User.email == email.lower())
    ).scalar_one_or_none()

    if user is None:
        # Run a dummy hash check so timing is similar to a real user.
        verify_password(password, _DUMMY_HASH)
        return None

    if not verify_password(password, user.password_hash):
        return None

    if not user.is_active:
        return None

    return user


# A valid bcrypt hash of a random string, used only for timing equalisation.
_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO5ODe0uGYyYlHY6kX1r4FzU6cB7UJ8Vi"