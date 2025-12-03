# app.py — Электронный журнал (с темой занятия!)
import streamlit as st
import sqlite3
import pandas as pd
import hashlib
from datetime import date

st.set_page_config(page_title="Электронный журнал", layout="wide")

conn = sqlite3.connect("journal.db", check_same_thread=False)
c = conn.cursor()

# ДОБАВЛЯЕМ ПОЛЕ topic В ТАБЛИЦУ lessons (если ещё нет)
c.execute("PRAGMA table_info(lessons)")
columns = [col[1] for col in c.fetchall()]
if "topic" not in columns:
    c.execute("ALTER TABLE lessons ADD COLUMN topic TEXT")
    conn.commit()

# ======================= АВТОРИЗАЦИЯ =======================
if "user" not in st.session_state:
    st.title("Электронный журнал")
    with st.form("login"):
        username = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        if st.form_submit_button("Войти"):
            h = hashlib.sha256(password.encode()).hexdigest()
            user = c.execute(
                "SELECT id,full_name,role,group_id FROM users WHERE username=? AND password=?",
                (username, h),
            ).fetchone()
            if user:
                st.session_state.user = {
                    "id": user[0],
                    "full_name": user[1],
                    "role": user[2],
                    "group_id": user[3],
                }
                st.rerun()
            else:
                st.error("Неверный логин или пароль")
else:
    user = st.session_state.user
    st.sidebar.header(user["full_name"])
    role_name = {
        "admin": "Администратор",
        "teacher": "Преподаватель",
        "student": "Студент",
    }[user["role"]]
    st.sidebar.caption(f"Роль: {role_name}")
    if st.sidebar.button("Выйти"):
        del st.session_state.user
        st.rerun()

    menu = ["Журнал"]
    if user["role"] == "admin":
        menu += ["Пользователи", "Группы", "Предметы", "Назначение"]
    page = st.sidebar.radio("Меню", menu)

    if page == "Журнал":
        st.header("Журнал")

        # Выбор журнала
        if user["role"] == "student":
            sql, params = "WHERE gd.group_id = ?", (user["group_id"],)
        elif user["role"] == "teacher":
            sql, params = "WHERE gd.teacher_id = ?", (user["id"],)
        else:
            sql, params = "", ()

        assignments = c.execute(
            f"""
            SELECT gd.id, g.name, d.name, u.full_name, gd.group_id
            FROM group_disciplines gd
            JOIN groups g ON g.id = gd.group_id
            JOIN disciplines d ON d.id = gd.discipline_id
            JOIN users u ON u.id = gd.teacher_id
            {sql}
            ORDER BY d.name, g.name
        """,
            params,
        ).fetchall()

        if not assignments:
            st.info("Нет доступных журналов")
        else:
            options = [f"{d} — {g} (преп. {t})" for _, g, d, t, _ in assignments]
            sel = st.selectbox("Выберите журнал", options)
            idx = options.index(sel)
            assignment_id, group_name, disc_name, teacher_name, group_id = assignments[
                idx
            ]

            st.subheader(f"{disc_name} • Группа {group_name}")

            # Уроки с темой
            lessons = c.execute(
                "SELECT id, date, homework, topic FROM lessons WHERE group_discipline_id=? ORDER BY date",
                (assignment_id,),
            ).fetchall()
            if not lessons:
                st.info("Пока нет уроков по этому предмету")
            else:
                dates = [l[1] for l in lessons]
                lesson_map = {l[1]: l[0] for l in lessons}
                hw_map = {l[1]: (l[2] or "—") for l in lessons}
                topic_map = {l[1]: (l[3] or "—") for l in lessons}

                # === ДЛЯ СТУДЕНТА ===
                if user["role"] == "student":
                    st.markdown("### Мои оценки")

                    grades_data = {"Дата": [], "Оценка": []}
                    for d in dates:
                        g = c.execute(
                            "SELECT grade FROM grades WHERE lesson_id=? AND student_id=?",
                            (lesson_map[d], user["id"]),
                        ).fetchone()
                        grade = g[0] if g and g[0] else "—"
                        grades_data["Дата"].append(
                            pd.to_datetime(d).strftime("%d.%m.%Y")
                        )
                        grades_data["Оценка"].append(grade)
                    st.dataframe(
                        pd.DataFrame(grades_data),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.markdown("### Уроки и задания")
                    lesson_data = []
                    for d in dates:
                        lesson_data.append(
                            {
                                "Дата": pd.to_datetime(d).strftime("%d.%m.%Y"),
                                "Тема занятия": topic_map.get(d, "—"),
                                "Домашнее задание": hw_map.get(d, "—"),
                            }
                        )
                    st.dataframe(
                        pd.DataFrame(lesson_data),
                        use_container_width=True,
                        hide_index=True,
                    )

                # === ДЛЯ ПРЕПОДАВАТЕЛЯ И АДМИНА ===
                else:
                    students = c.execute(
                        "SELECT id, full_name FROM users WHERE group_id=? AND role='student' ORDER BY full_name",
                        (group_id,),
                    ).fetchall()

                    columns = ["№", "ФИО студента"] + [
                        pd.to_datetime(d).strftime("%d.%m") for d in dates
                    ]
                    data = []

                    for i, (sid, name) in enumerate(students, 1):
                        row = {"№": i, "ФИО студента": name}
                        for d in dates:
                            g = c.execute(
                                "SELECT grade FROM grades WHERE lesson_id=? AND student_id=?",
                                (lesson_map[d], sid),
                            ).fetchone()
                            row[pd.to_datetime(d).strftime("%d.%m")] = (
                                g[0] if g and g[0] else ""
                            )
                        data.append(row)

                    # Строка "Тема занятия"
                    topic_row = {"№": "", "ФИО студента": "Тема занятия"}
                    for d in dates:
                        topic_row[pd.to_datetime(d).strftime("%d.%m")] = topic_map.get(
                            d, ""
                        )
                    data.append(topic_row)

                    # Строка "Домашнее задание"
                    hw_row = {"№": "", "ФИО студента": "Домашнее задание"}
                    for d in dates:
                        hw_row[pd.to_datetime(d).strftime("%d.%m")] = hw_map.get(d, "")
                    data.append(hw_row)

                    df = pd.DataFrame(data, columns=columns)

                    edited_df = st.data_editor(
                        df,
                        use_container_width=True,
                        hide_index=True,
                        disabled=["№", "ФИО студента"],
                    )

                    with st.expander("Добавить урок"):
                        new_date = st.date_input("Дата урока", date.today())
                        dstr = new_date.strftime("%Y-%m-%d")
                        if dstr in dates:
                            st.warning("Урок на эту дату уже существует")
                        else:
                            topic = st.text_input("Тема занятия")
                            hw = st.text_area("Домашнее задание (необязательно)", "")
                            if st.button("Создать урок"):
                                c.execute(
                                    "INSERT INTO lessons (group_discipline_id, date, homework, topic) VALUES (?,?,?,?)",
                                    (assignment_id, dstr, hw, topic),
                                )
                                conn.commit()
                                st.success("Урок добавлен!")
                                st.rerun()

                    if st.button("Сохранить все изменения"):
                        changed = False

                        # Оценки
                        for i in range(len(students)):
                            sid = students[i][0]
                            for d in dates:
                                col = pd.to_datetime(d).strftime("%d.%m")
                                old = df.iloc[i][col]
                                new = edited_df.iloc[i][col]
                                if str(new).strip() != str(old).strip():
                                    changed = True
                                    if not new or str(new).strip() in ["", "—"]:
                                        c.execute(
                                            "DELETE FROM grades WHERE lesson_id=? AND student_id=?",
                                            (lesson_map[d], sid),
                                        )
                                    else:
                                        c.execute(
                                            "INSERT OR REPLACE INTO grades (lesson_id, student_id, grade) VALUES (?,?,?)",
                                            (lesson_map[d], sid, str(new).strip()),
                                        )

                        # Темы и ДЗ
                        for d in dates:
                            col = pd.to_datetime(d).strftime("%d.%m")
                            # Тема занятия (предпоследняя строка)
                            old_topic = topic_map.get(d, "")
                            new_topic = edited_df.iloc[-2][col]
                            new_topic = (
                                str(new_topic).strip() if pd.notna(new_topic) else ""
                            )
                            if new_topic != old_topic:
                                changed = True
                                c.execute(
                                    "UPDATE lessons SET topic=? WHERE id=?",
                                    (new_topic, lesson_map[d]),
                                )

                            # Домашнее задание (последняя строка)
                            old_hw = hw_map.get(d, "")
                            new_hw = edited_df.iloc[-1][col]
                            new_hw = str(new_hw).strip() if pd.notna(new_hw) else ""
                            if new_hw != old_hw:
                                changed = True
                                c.execute(
                                    "UPDATE lessons SET homework=? WHERE id=?",
                                    (new_hw, lesson_map[d]),
                                )

                        if changed:
                            conn.commit()
                            st.success("Все изменения сохранены!")
                            st.rerun()
                        else:
                            st.info("Изменений нет")

    # ==================== АДМИНКА ====================
    if user["role"] == "admin" and page != "Журнал":
        if page == "Пользователи":
            st.subheader("Создать пользователя")
            username = st.text_input("Логин")
            password = st.text_input("Пароль", type="password")
            full_name = st.text_input("ФИО")
            role = st.selectbox("Роль", ["student", "teacher", "admin"])
            group_id = None
            if role == "student":
                groups = c.execute("SELECT id, name FROM groups").fetchall()
                if groups:
                    gname = st.selectbox("Группа", [g[1] for g in groups])
                    group_id = [g[0] for g in groups if g[1] == gname][0]
            if st.button("Создать"):
                h = hashlib.sha256(password.encode()).hexdigest()
                c.execute(
                    "INSERT INTO users (username,password,full_name,role,group_id) VALUES (?,?,?,?,?)",
                    (username, h, full_name, role, group_id),
                )
                conn.commit()
                st.success("Создано!")

        elif page == "Группы":
            name = st.text_input("Новая группа")
            if st.button("Добавить") and name:
                c.execute("INSERT OR IGNORE INTO groups (name) VALUES (?)", (name,))
                conn.commit()
                st.rerun()

        elif page == "Предметы":
            name = st.text_input("Новый предмет")
            if st.button("Добавить") and name:
                c.execute("INSERT INTO disciplines (name) VALUES (?)", (name,))
                conn.commit()
                st.rerun()

        elif page == "Назначение":
            groups = c.execute("SELECT id, name FROM groups").fetchall()
            discs = c.execute("SELECT id, name FROM disciplines").fetchall()
            teachers = c.execute(
                "SELECT id, full_name FROM users WHERE role='teacher'"
            ).fetchall()
            if groups and discs and teachers:
                g = st.selectbox("Группа", [x[1] for x in groups])
                d = st.selectbox("Предмет", [x[1] for x in discs])
                t = st.selectbox("Преподаватель", [x[1] for x in teachers])
                gid = c.execute("SELECT id FROM groups WHERE name=?", (g,)).fetchone()[
                    0
                ]
                did = c.execute(
                    "SELECT id FROM disciplines WHERE name=?", (d,)
                ).fetchone()[0]
                tid = c.execute(
                    "SELECT id FROM users WHERE full_name=?", (t,)
                ).fetchone()[0]
                if st.button("Назначить"):
                    c.execute(
                        "INSERT OR IGNORE INTO group_disciplines (group_id, discipline_id, teacher_id) VALUES (?,?,?)",
                        (gid, did, tid),
                    )
                    conn.commit()
                    st.success("Назначено!")

conn.close()
