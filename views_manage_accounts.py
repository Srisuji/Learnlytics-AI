"""Manage Accounts: Admin-only management for user accounts, creation, temporary passwords, and deactivations."""
import streamlit as st

import auth
import components as ui
import data_service as ds


def render(db_path=None, user=None):
    ds.require_role(user, ("admin",))

    ui.page_header(
        "Manage Accounts",
        "Create staff & student logins, generate temporary passwords, and manage access.",
        page_help="Administrator tool to manage user accounts, assign roles, and provide one-time temporary login credentials."
    )

    tab_users, tab_add_staff, tab_add_student = st.tabs([
        "All User Accounts",
        "Create Staff Account",
        "Create Student Account"
    ])

    with tab_users:
        users_list = auth.list_users(db_path=db_path)
        st.caption(f"Total registered user accounts: {len(users_list)}")

        for u in users_list:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
                with c1:
                    st.markdown(f"**{u['display_name']}** (`{u['username']}`)")
                    st.caption(f"Role: **{u['role'].upper()}** | Created: {u['created_at'][:10]}")
                with c2:
                    if u["role"] == "student":
                        st.markdown(f"ID: `{u['student_id']}`")
                    elif u["staff_department"]:
                        st.markdown(f"Dept: {u['staff_department']}")
                    else:
                        st.write("—")
                with c3:
                    if u.get("is_active") == 0:
                        st.error("Deactivated")
                    elif u.get("locked_until"):
                        st.error(f"Locked until {u['locked_until'][:16]}")
                    elif u.get("must_change_password"):
                        st.warning("Must change password")
                    else:
                        st.success("Active")
                with c4:
                    col_r, col_d = st.columns(2)
                    with col_r:
                        if st.button("Reset Pwd", key=f"btn_reset_{u['id']}", help="Generate temporary password"):
                            temp_pwd, errs = auth.reset_password(user, u["id"], db_path=db_path)
                            if temp_pwd:
                                st.session_state[f"temp_pwd_{u['id']}"] = temp_pwd
                                st.rerun()
                            else:
                                ui.show_errors(errs)
                    with col_d:
                        if u["id"] != user["id"]:
                            if u.get("is_active", 1) == 1:
                                if st.button("Deactivate", key=f"btn_deact_{u['id']}", help="Suspend login access"):
                                    ok, err = auth.deactivate_user(user, u["id"], db_path=db_path)
                                    if ok:
                                        ui.flash(f"Account '{u['username']}' was deactivated.")
                                        st.rerun()
                                    else:
                                        st.error(err)
                            else:
                                if st.button("Reactivate", key=f"btn_act_{u['id']}", help="Restore login access"):
                                    ok, err = auth.activate_user(user, u["id"], db_path=db_path)
                                    if ok:
                                        ui.flash(f"Account '{u['username']}' was reactivated.")
                                        st.rerun()
                                    else:
                                        st.error(err)

                # Show one-time temporary password if just generated
                if f"temp_pwd_{u['id']}" in st.session_state:
                    temp_val = st.session_state.pop(f"temp_pwd_{u['id']}")
                    st.success(
                        f"**Temporary Password for '{u['username']}':** `{temp_val}`  \n"
                        f"*(Copy this now and give it to the user. It will not be displayed again. The user will be required to change it on their next login.)*"
                    )

    with tab_add_staff:
        st.markdown("### Create New Staff / Faculty Account")
        with st.form("create_staff_form"):
            c1, c2 = st.columns(2)
            s_uname = c1.text_input("Username *", key="s_uname", help="Login identifier (no spaces)")
            s_name = c2.text_input("Full Display Name *", key="s_name", help="Faculty or Coordinator Name")
            c3, c4 = st.columns(2)
            s_role = c3.selectbox("Role *", ["staff", "admin"], key="s_role", help="Staff or Administrator")
            s_dept = c4.text_input("Department (optional)", key="s_dept", help="e.g. Computer Science")
            s_email = st.text_input("Email (optional)", key="s_email")
            s_temp_check = st.checkbox("Require user to change password on first login", value=True)
            s_pwd = st.text_input("Initial Password * (min 8 chars)", type="password", key="s_pwd")
            s_submit = st.form_submit_button("Create Account", help="Save new staff account")

        if s_submit:
            new_u, errs = auth.create_user(
                username=s_uname,
                password=s_pwd,
                role=s_role,
                display_name=s_name,
                email=s_email,
                staff_department=s_dept,
                must_change_password=s_temp_check,
                db_path=db_path,
            )
            if new_u:
                ui.flash(f"Success: Created {s_role} account for '{s_name}' (`{s_uname}`).")
                st.rerun()
            else:
                ui.show_errors(errs)

    with tab_add_student:
        st.markdown("### Create Student Login Linked to Existing Student ID")
        st.caption("Student logins are restricted to only viewing their own personal academic metrics and goals.")
        all_students = ds.list_students_df(db_path=db_path)
        existing_u_students = {u["student_id"] for u in auth.list_users(db_path=db_path) if u.get("student_id")}
        avail_students = all_students[~all_students["student_id"].isin(existing_u_students)]

        if avail_students.empty:
            st.info("All existing students in the system already have user logins created, or no students exist.")
        else:
            student_choices = list(avail_students["student_id"])
            student_names = dict(zip(avail_students["student_id"], avail_students["name"]))

            with st.form("create_student_login_form"):
                sel_sid = st.selectbox(
                    "Select Student *",
                    student_choices,
                    format_func=lambda sid: f"{sid} - {student_names[sid]}",
                    help="Choose the student record to link this account to"
                )
                suggested_uname = sel_sid.lower().replace(" ", "")
                st_uname = st.text_input("Student Username *", value=suggested_uname,
                                         help="Username the student will use to log in")
                st_email = st.text_input("Email (optional)", value=avail_students.loc[avail_students["student_id"] == sel_sid, "email"].values[0] or "")
                st_require_change = st.checkbox("Require password change on first login", value=True)
                st_pwd = st.text_input("Initial Temporary Password * (min 8 chars)", type="password", key="st_pwd")
                st_submit = st.form_submit_button("Create Student Account")

            if st_submit:
                sel_name = student_names[sel_sid]
                new_u, errs = auth.create_user(
                    username=st_uname,
                    password=st_pwd,
                    role="student",
                    display_name=sel_name,
                    email=st_email,
                    student_id=sel_sid,
                    must_change_password=st_require_change,
                    db_path=db_path,
                )
                if new_u:
                    ui.flash(f"Success: Created student login for '{sel_name}' (`{st_uname}`) linked to ID `{sel_sid}`.")
                    st.rerun()
                else:
                    ui.show_errors(errs)
