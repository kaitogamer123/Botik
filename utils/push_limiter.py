"""
Утилита для проверки лимита времени (48 часов) на изменение цели пуша.
"""

from datetime import datetime, timedelta
from database import get_push_goals

DEADLINE_HOURS = 48


def is_locked(chosen_at: str) -> bool:
    """
    Проверяет, прошло ли 48 часов с момента выбора цели.
    """
    if not chosen_at:
        return False

    try:
        chosen_time = datetime.strptime(chosen_at, "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            chosen_time = datetime.fromisoformat(chosen_at)
        except Exception:
            return False

    return datetime.now() - chosen_time > timedelta(hours=DEADLINE_HOURS)


async def get_locked_users(season_id: str = "current") -> list[int]:
    """
    Возвращает список user_id игроков, у которых истёк лимит изменения выбора.
    """
    rows = await get_push_goals()

    locked = []
    for r in rows:
        if is_locked(r.get("chosen_at", "")):
            locked.append(r["user_id"])

    return locked
