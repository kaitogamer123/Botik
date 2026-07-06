"""
Форматирование сообщений и списков участников.
"""

from config import CLAN_DISPLAY, CLAN_HEADER_EMOJI, ROLE_LABELS, ROLES


def tg_link(user_id: int, display: str) -> str:
    """HTML-ссылка на профиль через tg://user?id= (не пингует)."""
    if not user_id:
        return display
    return f'<a href="tg://user?id={user_id}">{display}</a>'


def format_roster(clan: str, members: list[dict]) -> str:
    """
    Форматирует список участников клана в красивый HTML.
    Ссылки через tg://user?id= или @username чтобы не пинговать.
    """
    emoji = CLAN_HEADER_EMOJI.get(clan, "🏰")
    title = CLAN_DISPLAY.get(clan, clan)

    lines = [f"{emoji} <b>{title}</b> {emoji}\n"]

    role_order = sorted(ROLES.keys(), key=lambda r: ROLES[r])
    grouped: dict[str, list] = {r: [] for r in role_order}

    for m in members:
        role = m.get("role", "member")
        grouped.setdefault(role, []).append(m)

    counter = 1
    role_headers = {
        "president":  "† ★★★ Лидер клана ★★★ †",
        "grand_vice": "⊱━━━━━━━━━━━━━━━━━━━━━━⊰\n†★★★ Гранд Вице ★★★†",
        "vice":       "⊱━━━━━━━━━━━━━━━━━━━━━━⊰\n†★★ Вице Президент ★★†",
        "veteran":    "⊱━━━━━━━━━━━━━━━━━━━━━━⊰\n†★Ветераны★†",
        "helper":     "⊱━━━━━━━━━━━━━━━━━━━━━━⊰\n†★Помощники★†",
        "member":     "⊱━━━━━━━━━━━━━━━━━━━━━━⊰\nУчастники клана:",
    }

    for role in role_order:
        group = grouped.get(role, [])
        if not group:
            continue
        lines.append(role_headers.get(role, ""))
        for m in group:
            uid = m.get("user_id")
            nick = m.get("game_nick") or "—"
            uname = m.get("username")

            # ИСПРАВЛЕНО: Безопасная генерация ссылок, защищенная от отсутствия user_id
            if uid and int(uid) > 0:
                name_link = tg_link(uid, nick)
            elif uname:
                name_link = f'<a href="tg://resolve?domain={uname}">{nick}</a>'
            else:
                name_link = nick

            lines.append(f"{counter}. {name_link}")
            counter += 1

    return "\n".join(lines)


def format_push_goal_list(members_by_clan: dict, goals_map: dict) -> str:
    """
    Список «кто что пушит» разбитый по кланам.
    """
    # ИСПРАВЛЕНО: Добавлены пропущенные двоеточия в синтаксис словаря
    goal_emoji = {"trophies": "🏆 Трофеи", "league": "🏅 Лига"}
    lines = ["<b>📊 Список целей на сезон</b>\n"]

    for clan, members in members_by_clan.items():
        clan_title = CLAN_DISPLAY.get(clan, clan)
        lines.append(f"\n{CLAN_HEADER_EMOJI.get(clan,'')} <b>{clan_title}</b>")
        for m in members:
            uid = m.get("user_id")
            nick = m.get("game_nick") or m.get("username") or str(uid)
            goal = goals_map.get(uid) if uid else None
            goal_str = goal_emoji.get(goal, "❓ Не определился")
            lines.append(f"  • {nick} — {goal_str}")

    return "\n".join(lines)


def welcome_text(member: dict, clan: str) -> str:
    role_label = ROLE_LABELS.get(member.get("role", "member"), "Участник")
    clan_title = CLAN_DISPLAY.get(clan, clan)
    uname = member.get("username")
    address = f"@{uname}" if uname else member.get("first_name", "")
    return (
        f"Привет, {address} 👋\n\n"
        f"Ты — <b>{role_label}</b> клана <b>{clan_title}</b>.\n"
        f"Это приветственное сообщение бота ViGarik Squad 🎮"
    )


PUSH_GOAL_TEXT = """🎯 <b>Определи свою цель на этот сезон!</b>

<b>🏆 Вариант 1 — Пуш трофеев:</b>
• Цель: трофеи × 1.2 от топ-1 участника клана
• Лига: минимум <b>Лега 1</b>
• Если не хочешь пушить лигу — пуш трофеев × 1.1 + ранг <b>минимум Мифик</b>
  (штрафа не будет)

<b>🏅 Вариант 2 — Пуш лиги:</b>
• Цель: минимум <b>Лега 3</b> к концу сезона
• Трофеи × 1.3 от топ-1 участника клана
• Если не хочешь пушить кубки — <b>минимум Мастер 1</b> + трофеи × 1.35
  (штрафа не будет)

⏱ Изменить решение можно в течение <b>2 дней</b> после выбора.

Выбери свой вариант 👇"""
