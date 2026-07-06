"""
Генератор HTML-форматированных списков участников кланов без пингов.
"""

from config import CLAN_DISPLAY, CLAN_HEADER_EMOJI, ROLE_LABELS


def format_clan_roster(clan_key: str, members: list[dict]) -> str:
    """
    Форматирует список участников клана в красивый HTML вид.
    Использует структуру из ТЗ. Заменяет пинги на текстовые HTML-ссылки.
    """
    clan_name = CLAN_DISPLAY.get(clan_key, clan_key.capitalize())
    emoji = CLAN_HEADER_EMOJI.get(clan_key, "⭐")

    # Шапка списка
    lines = [
        f"{emoji}<b>{clan_name}</b>{emoji}\n"
    ]

    # Группируем пользователей по ролям
    roles_groups = {
        "president": [],
        "grand_vice": [],
        "vice": [],
        "veteran": [],
        "helper": [],
        "member": []
    }

    for m in members:
        role = m.get("role", "member")
        if role in roles_groups:
            roles_groups[role].append(m)

    # Порядковый номер для сквозного списка (как в ТЗ)
    counter = 1

    # Отрезки иерархии
    role_order = ["president", "grand_vice", "vice", "veteran", "helper", "member"]

    for role in role_order:
        group_members = roles_groups[role]
        if not group_members:
            continue

        # Добавляем разделитель и название роли
        if role == "president":
            lines.append("† ★★★ Лидер клана ★★★ †")
        elif role == "grand_vice":
            lines.append("╭━──━─≪✠≫─━──━╮")
            lines.append("Гранд Вице Президент")
        elif role == "vice":
            lines.append("╭━──━─≪✠≫─━──━╮")
            lines.append("Вице Президент")
        elif role == "member":
            lines.append("╭━──━─≪✠≫─━──━╮")
            lines.append("Участники клана:")
        else:
            lines.append("╭━──━─≪✠≫─━──━╮")
            lines.append(ROLE_LABELS.get(role, role.capitalize()))

        # Заполняем людей в текущей роли
        for m in group_members:
            display_name = m.get("game_nick") or m.get("username") or m.get("first_name") or "Игрок"
            uid = m.get("user_id")

            # ИСПРАВЛЕНО: Теперь проверка ID идет ПЕРВОЙ.
            # Если бот знает цифровой ID, ссылка ВСЕГДА будет вечной (tg://user?id=)
            if uid and int(uid) > 0:
                profile_url = f"tg://user?id={uid}"
            elif m.get("username"):
                profile_url = f"https://t.me/{m['username']}"
            else:
                # Если нет ни ID, ни Username, выводим просто текст без битых ссылок
                lines.append(f"{counter}) {display_name}")
                counter += 1
                continue

            lines.append(f"{counter}) <a href='{profile_url}'>{display_name}</a>")
            counter += 1

    return "\n".join(lines)
