"""Views AI Tutor: Interactive, supportive chat for authenticated students.

Theme: Dark Navy (#071426, #081A30, #0B2342), Electric Blue (#00A6FF), Neon Cyan (#00E5FF).
Zero emojis, clean typography, responsive layout.
"""
import streamlit as st

import ai_tutor_service as tutor_svc
import components as ui
import data_service as ds

SUGGESTED_PROMPTS = [
    "Explain this concept in simple words.",
    "Give me a hint before the answer.",
    "Create five K1 recall questions.",
    "Help me understand K2 concepts.",
    "Give me a K3 application problem.",
    "Help me revise a subject.",
]


def render(db_path=None, user=None):
    """Render the AI Tutor interface strictly for authenticated students."""
    ds.require_role(user, ("student",))
    student_id = user.get("student_id")
    if not student_id:
        st.error("No student record is linked to your account. Please contact your administrator.")
        return

    ui.page_header(
        "Learnlytics AI Tutor",
        "Ask questions, understand concepts, and practise at your own pace.",
        page_help="Your friendly academic guide. Ask questions, request step-by-step explanations, get hints before full solutions, or practice K1-K3 questions."
    )

    # 1. State Initialization
    if "tutor_conv_id" not in st.session_state:
        st.session_state["tutor_conv_id"] = None
    if "tutor_messages" not in st.session_state:
        st.session_state["tutor_messages"] = []
    if "tutor_prompt_input" not in st.session_state:
        st.session_state["tutor_prompt_input"] = ""
    if "tutor_confirm_new" not in st.session_state:
        st.session_state["tutor_confirm_new"] = False
    if "tutor_confirm_delete_all" not in st.session_state:
        st.session_state["tutor_confirm_delete_all"] = False

    # 2. Top Action & Language Controls Bar
    c_top1, c_top2, c_top3 = st.columns([1.5, 1.2, 1.3])
    with c_top1:
        lang_choice = st.selectbox(
            "Tutor Language",
            ["English", "Tamil", "Tanglish"],
            key="tutor_language_select",
            help="Choose the language for explanations"
        )
    with c_top2:
        st.write("")
        st.write("")
        if st.button("New Chat", key="btn_new_chat", help="Start a new chat conversation"):
            if st.session_state["tutor_messages"]:
                st.session_state["tutor_confirm_new"] = True
            else:
                # Direct reset
                st.session_state["tutor_conv_id"] = None
                st.session_state["tutor_messages"] = []
                st.rerun()

    with c_top3:
        st.write("")
        st.write("")
        if st.button("Clear History", key="btn_clear_history", help="Delete all saved conversations"):
            st.session_state["tutor_confirm_delete_all"] = True

    # Confirmation Dialogs
    if st.session_state.get("tutor_confirm_new"):
        with st.container(border=True):
            st.warning("Start a new chat session? Your current conversation is automatically saved in your history.")
            c_yes, c_no = st.columns(2)
            if c_yes.button("Confirm New Chat", key="btn_confirm_new"):
                st.session_state["tutor_conv_id"] = None
                st.session_state["tutor_messages"] = []
                st.session_state["tutor_confirm_new"] = False
                st.rerun()
            if c_no.button("Cancel", key="btn_cancel_new"):
                st.session_state["tutor_confirm_new"] = False
                st.rerun()

    if st.session_state.get("tutor_confirm_delete_all"):
        with st.container(border=True):
            st.error("Delete all your stored chat history? This cannot be undone. (Academic records remain completely safe.)")
            cd_yes, cd_no = st.columns(2)
            if cd_yes.button("Confirm Delete All", key="btn_confirm_del_all"):
                ds.delete_all_student_conversations(user, db_path=db_path)
                st.session_state["tutor_conv_id"] = None
                st.session_state["tutor_messages"] = []
                st.session_state["tutor_confirm_delete_all"] = False
                st.success("All conversation history deleted.")
                st.rerun()
            if cd_no.button("Cancel", key="btn_cancel_del_all"):
                st.session_state["tutor_confirm_delete_all"] = False
                st.rerun()

    # 3. Sidebar Conversation History Drawer
    with st.expander("Saved Conversations", expanded=False):
        saved_convs = ds.list_student_conversations(user, db_path=db_path)
        if not saved_convs:
            st.caption("No previous study sessions saved.")
        else:
            for sc in saved_convs:
                cs1, cs2 = st.columns([3, 1])
                is_current = (st.session_state["tutor_conv_id"] == sc["id"])
                lbl = f"{'Active: ' if is_current else ''}{sc['title']} ({sc['language']})"
                if cs1.button(lbl, key=f"load_conv_{sc['id']}"):
                    st.session_state["tutor_conv_id"] = sc["id"]
                    msgs = ds.get_conversation_messages(user, sc["id"], db_path=db_path)
                    st.session_state["tutor_messages"] = msgs
                    st.rerun()
                if cs2.button("Delete", key=f"del_conv_{sc['id']}"):
                    ds.delete_student_conversation(user, sc["id"], db_path=db_path)
                    if st.session_state["tutor_conv_id"] == sc["id"]:
                        st.session_state["tutor_conv_id"] = None
                        st.session_state["tutor_messages"] = []
                    st.rerun()

    # 4. API Configuration Warning if unconfigured
    ai_status = tutor_svc.get_ai_config()
    if not ai_status["is_configured"]:
        st.info(
            "**AI Tutor Notice:** The AI Tutor service is currently in standby because the AI API key is not configured. "
            "Please ask your institution administrator to set the OPENAI_API_KEY environment variable. "
            "All other Learnlytics AI features remain fully operational."
        )

    # 5. Suggested Prompts
    st.markdown("##### Suggested Topics")
    p_cols = st.columns(3)
    for idx, prompt_text in enumerate(SUGGESTED_PROMPTS):
        col_target = p_cols[idx % 3]
        if col_target.button(prompt_text, key=f"sug_btn_{idx}"):
            st.session_state["selected_prompt"] = prompt_text
            st.rerun()

    st.write("")

    # 6. Chat Transcript Display
    st.markdown("---")
    chat_container = st.container()
    with chat_container:
        if not st.session_state["tutor_messages"]:
            st.markdown(
                """
                <div style="background-color: #0B2342; border: 1px dashed rgba(0, 229, 255, 0.25); border-radius: 10px; padding: 24px; text-align: center; margin: 12px 0;">
                    <div style="color: #00E5FF; font-size: 1.1rem; font-weight: 600; margin-bottom: 6px;">How can I help you learn today?</div>
                    <div style="color: #A9BCD6; font-size: 0.95rem;">Ask a doubt from your lectures, request practice questions, or ask for a step-by-step hint.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            for msg in st.session_state["tutor_messages"]:
                role = msg.get("role", "student")
                content = msg.get("content", "")
                if role in ("student", "user"):
                    with st.chat_message("user"):
                        st.markdown(content)
                else:
                    with st.chat_message("assistant"):
                        st.markdown(content)

    # 7. Chat Input & Submission Handler
    # Handle auto-filled suggested prompt if present
    initial_input = st.session_state.pop("selected_prompt", "")
    
    user_query = st.chat_input("Type your question or topic here...", key="tutor_chat_input")
    if initial_input and not user_query:
        user_query = initial_input

    if user_query:
        clean_query = user_query.strip()
        if clean_query:
            # Append student query immediately to session state transcript
            st.session_state["tutor_messages"].append({"role": "student", "content": clean_query})
            with st.chat_message("user"):
                st.markdown(clean_query)

            # Ensure conversation exists in DB
            try:
                conv = ds.get_or_create_conversation(
                    user,
                    conversation_id=st.session_state.get("tutor_conv_id"),
                    language=lang_choice,
                    db_path=db_path
                )
                st.session_state["tutor_conv_id"] = conv["id"]
                ds.add_chat_message(user, conv["id"], "student", clean_query, db_path=db_path)
            except Exception as e:
                # If database write fails, continue with in-memory conversation
                pass

            # Call AI Tutor with loading indicator
            with st.chat_message("assistant"):
                with st.spinner("Analyzing and preparing explanation..."):
                    success, reply = tutor_svc.call_ai_tutor(
                        user=user,
                        student_prompt=clean_query,
                        conversation_history=st.session_state["tutor_messages"][:-1],
                        language=lang_choice,
                        db_path=db_path
                    )
                    st.markdown(reply)

            # Store assistant response in session and DB
            st.session_state["tutor_messages"].append({"role": "assistant", "content": reply})
            if st.session_state.get("tutor_conv_id"):
                try:
                    ds.add_chat_message(user, st.session_state["tutor_conv_id"], "assistant", reply, db_path=db_path)
                except Exception:
                    pass

            st.rerun()

    # Footer note
    st.caption("Academic Guidance Note: AI Tutor explanations are supportive study aids. Official marks and curricular guidelines are verified by faculty.")
