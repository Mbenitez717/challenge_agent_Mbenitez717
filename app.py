from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import streamlit as st

from src.config import DATA_DIR, EXPECTED_PDFS, Settings
from src.providers import create_provider
from src.rag import answer_question, build_or_load_index, discover_pdfs


st.set_page_config(
    page_title="Santos Pegasus | Asistente RAG",
    page_icon=":material/auto_awesome:",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.container(border=True):
    st.title("Santos Pegasus Soluciones")
    st.write(
        "Empresa de tecnología especializada en el desarrollo de software escalable "
        "bajo arquitectura de microservicios y soluciones de Inteligencia Artificial "
        "(RAG). Se destaca por sus rigurosos estándares técnicos en ingeniería back-end "
        "y front-end, garantizando excelencia operativa y seguridad en infraestructuras "
        "de nube (OCI)."
    )


def save_uploads(uploaded_files: list) -> None:
    for uploaded in uploaded_files:
        safe_name = Path(uploaded.name).name
        if not safe_name.lower().endswith(".pdf"):
            continue
        (DATA_DIR / safe_name).write_bytes(uploaded.getbuffer())


def get_streamlit_secret(*names: str) -> str:
    """Lee un secreto de Streamlit sin exigir un archivo local de secretos."""
    try:
        for name in names:
            value = st.secrets.get(name, "")
            if value and str(value).strip():
                return str(value).strip()
    except Exception:
        # En ejecución local es normal que secrets.toml no exista.
        return ""
    return ""


try:
    settings = Settings.from_env()
    settings_error = ""
except ValueError as exc:
    settings = None
    settings_error = str(exc)

credentials_error = ""

if settings and settings.provider == "openai" and not settings.openai_api_key:
    deployed_api_key = get_streamlit_secret("OPENAI_API_KEY", "openai_api_key")
    if deployed_api_key:
        settings = replace(settings, openai_api_key=deployed_api_key)

with st.sidebar:
    st.subheader("Base de conocimiento", help="Manuales utilizados por el asistente RAG.")
    st.caption(f"Carpeta: {DATA_DIR}")

    if settings and settings.provider == "openai" and not settings.openai_api_key:
        session_api_key = st.text_input(
            "Clave de OpenAI para esta sesión",
            type="password",
            key="openai_api_key_session",
            icon=":material/key:",
            placeholder="sk-...",
            help=(
                "La clave permanece solamente en esta sesión del navegador; "
                "no se escribe en el proyecto ni se envía a Git."
            ),
            persist_state="session",
        )
        if session_api_key and session_api_key.strip():
            settings = replace(
                settings,
                openai_api_key=session_api_key.strip(),
            )

    if settings:
        try:
            settings.validate_credentials()
        except ValueError as exc:
            credentials_error = str(exc)

    uploaded_files = []
    if settings and settings.allow_pdf_upload:
        uploaded_files = st.file_uploader(
            "Cargar manuales PDF",
            type=["pdf"],
            accept_multiple_files=True,
            help="También puede copiar los archivos directamente dentro de data/.",
        )
        if st.button(
            "Guardar PDF cargados",
            icon=":material/upload_file:",
            width="stretch",
            disabled=not uploaded_files,
        ):
            save_uploads(uploaded_files)
            st.toast("Archivos guardados en data/.", icon=":material/check_circle:")

    pdf_paths = discover_pdfs()
    for expected_name in EXPECTED_PDFS:
        icon = "✓" if (DATA_DIR / expected_name).exists() else "○"
        st.write(f"{icon} {expected_name}")

    if settings:
        st.write(f"**Proveedor:** {settings.provider}")
        st.write(f"**Modelo:** {settings.chat_model}")
    if settings_error:
        st.error(settings_error)
    if credentials_error:
        st.warning(credentials_error, icon=":material/key:")

    can_process = bool(settings and not settings_error and not credentials_error)
    process_clicked = st.button(
        "Procesar documentos",
        type="primary",
        icon=":material/database:",
        width="stretch",
        disabled=not can_process,
    )

st.subheader("Asistente de manuales")
st.caption("Las respuestas se generan con fragmentos recuperados y muestran archivo y página.")

st.session_state.setdefault("messages", [])

if process_clicked:
    try:
        provider = create_provider(settings)
        progress_bar = st.progress(0.0, text="Preparando documentos...")

        def report(value: float, message: str) -> None:
            progress_bar.progress(value, text=message)

        st.session_state.rag_index = build_or_load_index(
            discover_pdfs(), settings, provider, report
        )
        st.session_state.provider = provider
        progress_bar.empty()
        st.success(
            "Base de conocimiento lista para responder.",
            icon=":material/check_circle:",
        )
    except Exception as exc:
        st.error(f"No se pudo procesar la base: {exc}")

if not pdf_paths:
    st.info(
        "Deposite los dos PDF dentro de la carpeta `data/` o cárguelos desde el panel lateral."
    )
elif "rag_index" not in st.session_state:
    st.info("Pulse **Procesar documentos** para crear o cargar el índice RAG.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander("Fuentes consultadas"):
                for source in message["sources"]:
                    st.markdown(
                        f"**[F{source['number']}] {source['file']} — página "
                        f"{source['page']}** · similitud {source['score']:.3f}"
                    )
                    st.caption(source["text"])

ready = "rag_index" in st.session_state and "provider" in st.session_state
question = st.chat_input(
    "Ejemplo: ¿Qué debo hacer durante mi primer día?",
    disabled=False,
    submit_mode="disable",
)
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    if not ready:
        if settings_error:
            guidance = f"Revise la configuración de la aplicación: {settings_error}"
        elif credentials_error:
            guidance = (
                "Configure la clave de OpenAI en los secretos del despliegue o "
                "en el campo de contraseña del panel lateral."
            )
        elif not pdf_paths:
            guidance = (
                "Aún no hay documentos PDF disponibles. Cargue los manuales desde "
                "el panel lateral o móntelos en la carpeta `data/` del servidor."
            )
        else:
            guidance = (
                "La base todavía no fue indexada. Pulse **Procesar documentos** "
                "y, cuando termine, vuelva a enviar la pregunta."
            )
        with st.chat_message("assistant"):
            st.info(guidance, icon=":material/info:")
        st.session_state.messages.append(
            {"role": "assistant", "content": guidance}
        )
    else:
        with st.chat_message("assistant"):
            try:
                with st.spinner("Buscando en los manuales..."):
                    response, results = answer_question(
                        question,
                        st.session_state.rag_index,
                        st.session_state.provider,
                        settings.top_k,
                    )
                st.markdown(response)
                sources = [
                    {
                        "number": number,
                        "file": result.chunk.source,
                        "page": result.chunk.page,
                        "score": result.score,
                        "text": result.chunk.text,
                    }
                    for number, result in enumerate(results, start=1)
                ]
                with st.expander("Fuentes consultadas"):
                    for source in sources:
                        st.markdown(
                            f"**[F{source['number']}] {source['file']} — página "
                            f"{source['page']}** · similitud {source['score']:.3f}"
                        )
                        st.caption(source["text"])
                st.session_state.messages.append(
                    {"role": "assistant", "content": response, "sources": sources}
                )
            except Exception as exc:
                st.error(f"No se pudo responder: {exc}")
