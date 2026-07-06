"""
Система прав доступа для ViGarik Squad Bot
"""

from config import ROLES, EDIT_LIST_MIN_ROLE, APPOINT_ADMIN_MIN_ROLE


# ─── Базовый уровень роли ─────────────────────────────────────────────────────

def _lvl(role: str) -> int:
    """Чем меньше число — тем выше роль."""
    if not role:
        return 999
    # ЗАЩИТА: подменяем длинное название роли на короткий ключ из config.py
    if role == "grand_vice_president":
        role = "grand_vice"
    elif role == "vice_president":
        role = "vice"
    return ROLES.get(role, 999)


def has_role(member: dict, required_role: str) -> bool:
    """
    Проверка: роль пользователя >= требуемой роли.
    (по уровню иерархии)
    """
    if not member:
        return False
    return _lvl(member.get("role")) <= _lvl(required_role)


# ─── Основные проверки ────────────────────────────────────────────────────────

def is_any_admin(member: dict) -> bool:
    """
    Любой админ (вся иерархия выше member, кроме обычного участника)
    """
    if not member:
        return False
    role = member.get("role")
    if role == "grand_vice_president":
        role = "grand_vice"
    elif role == "vice_president":
        role = "vice"
    return role in ROLES and role != "member"


def is_top_admin(member: dict) -> bool:
    """
    Самые высокие роли (Президент / Гранд Вице)
    """
    if not member:
        return False
    return member.get("role") in ("president", "grand_vice", "grand_vice_president")


def can_edit_list(member: dict) -> bool:
    """
    Редактирование списков клана
    """
    return has_role(member, EDIT_LIST_MIN_ROLE)


def can_appoint_admins(member: dict) -> bool:
    """
    Назначение ролей (модерации)
    """
    return has_role(member, APPOINT_ADMIN_MIN_ROLE)


def can_read_proposals(member: dict) -> bool:
    """
    Доступ к предложкам (президенты и гранд-вице)
    """
    if not member:
        return False
    return member.get("role") in ("president", "grand_vice", "grand_vice_president")


def can_launch_push_goal(member: dict) -> bool:
    """
    Запуск голосования цели сезона (Только Президент)
    """
    if not member:
        return False
    return member.get("role") == "president"


def can_view_push_stats(member: dict) -> bool:
    """
    Просмотр статистики пуша
    """
    return has_role(member, "grand_vice")


def can_notify_users(member: dict) -> bool:
    """
    Оповещения через новости клана
    """
    return has_role(member, "grand_vice")


# ─── Утилиты ──────────────────────────────────────────────────────────────────

def role_name(member: dict) -> str:
    """Возвращает роль пользователя."""
    if not member:
        return "member"
    return member.get("role", "member")


def is_president(member: dict) -> bool:
    if not member:
        return False
    return member.get("role") == "president"


def is_grand_vice(member: dict) -> bool:
    if not member:
        return False
    return member.get("role") in ("grand_vice", "grand_vice_president")
