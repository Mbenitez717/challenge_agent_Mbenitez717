from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from src.config import EXPECTED_PDFS, Settings
from src.providers import AIProvider, create_provider
from src.rag import VectorIndex, answer_question, build_or_load_index, discover_pdfs


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


def friendly_index_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "connection" in message or "conexión" in message:
        return "El servicio local de inteligencia artificial no está disponible."
    if "404" in message or "not found" in message:
        return "Los modelos configurados todavía no están disponibles en el servidor."
    if "no hay archivos pdf" in message:
        return "Los manuales requeridos no están instalados en el servidor."
    return "No se pudo preparar la base de conocimiento."


def document_signature(pdf_paths: list[Path]) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        (str(path.resolve()), path.stat().st_size, path.stat().st_mtime_ns)
        for path in pdf_paths
    )


@st.cache_resource(show_spinner=False, max_entries=2)
def load_rag_runtime(
    settings: Settings,
    signature: tuple[tuple[str, int, int], ...],
) -> tuple[VectorIndex, AIProvider]:
    # La firma invalida la caché automáticamente si cambia un manual.
    del signature
    provider = create_provider(settings)
    index = build_or_load_index(discover_pdfs(), settings, provider)
    return index, provider


settings = Settings.from_env()
pdf_paths = discover_pdfs()
available_names = {path.name for path in pdf_paths}
missing_documents = [name for name in EXPECTED_PDFS if name not in available_names]

with st.sidebar:
    st.subheader("Base de conocimiento")
    for expected_name in EXPECTED_PDFS:
        if expected_name in available_names:
            st.write(f":material/check_circle: {expected_name}")
        else:
            st.write(f":material/error: {expected_name}")
    st.divider()
    st.caption(f"Modelo: {settings.chat_model}")
    st.caption("Procesamiento automático · sin API Key")

if missing_documents:
    st.error(
        "La instalación del servidor está incompleta. Faltan los manuales: "
        + ", ".join(missing_documents)
    )
    st.stop()

try:
    with st.status(
        "Preparando la base de conocimiento...",
        expanded=True,
    ) as runtime_status:
        rag_index, provider = load_rag_runtime(
            settings,
            document_signature(pdf_paths),
        )
        runtime_status.update(
            label="Base de conocimiento disponible",
            state="complete",
            expanded=False,
        )
except Exception as exc:
    logger.exception("No se pudo inicializar el entorno RAG")
    st.error(friendly_index_error(exc))
    st.caption("El administrador del servidor debe revisar los registros de la aplicación.")
    st.stop()

st.subheader("Asistente")
st.caption("Escribe tu consulta en el campo inferior.")

st.session_state.setdefault("messages", [])

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input(
    "Escribe tu pregunta",
    submit_mode="disable",
)

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Consultando los manuales..."):
                response = answer_question(
                    question,
                    rag_index,
                    provider,
                    settings.top_k,
                    settings.min_similarity,
                )
            st.markdown(response)
            st.session_state.messages.append(
                {"role": "assistant", "content": response}
            )
        except Exception:
            logger.exception("No se pudo responder la pregunta")
            response = "No pude completar la consulta. Inténtalo nuevamente en unos segundos."
            st.error(response)
            st.session_state.messages.append(
                {"role": "assistant", "content": response}
            )
