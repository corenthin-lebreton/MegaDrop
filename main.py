import io
import logging
import os
import re

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from security import sanitize_pdf, SanitizationError
from mega_client import upload_file_to_mega, MegaClientError, validate_config

_MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
_MAX_FILE_SIZE_BYTES = _MAX_FILE_SIZE_MB * 1024 * 1024
validate_config()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    """Nettoie un filename pour éviter la log injection (CRLF, etc.)."""
    return re.sub(r"[\r\n\t]", "_", name)[:255]


app = FastAPI(
    title="SeaDrop",
    description="Plateforme sécurisée de dépôt de documents PDF",
    version="1.0.0",
)


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_template() -> FileResponse:
    return FileResponse("index.html")


@app.post("/upload", summary="Dépose un PDF sanitisé vers Mega.nz")
async def upload_document(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Extension invalide. Seuls les fichiers .pdf sont acceptés.")

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Type de contenu invalide.")

    safe_name = _safe_filename(file.filename)

    file_bytes: bytes = await file.read()

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Aucun fichier fourni.")

    if len(file_bytes) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Fichier trop volumineux. Taille maximale : {_MAX_FILE_SIZE_MB} Mo.",
        )

    try:
        logger.info("Début sanitization — fichier: %s", safe_name)
        clean_pdf_stream: io.BytesIO = sanitize_pdf(file_bytes)
        logger.info("Sanitization réussie — fichier: %s", safe_name)
    except SanitizationError as exc:
        logger.warning("Échec sanitization — fichier: %s — %s", safe_name, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # pragma: no cover — filet de sécurité
        logger.error("Erreur inattendue (sanitization) — fichier: %s", safe_name, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne lors du traitement du fichier.")

    try:
        logger.info("Envoi vers Mega.nz — fichier: %s", safe_name)
        upload_file_to_mega(safe_name, clean_pdf_stream)
        logger.info("Upload terminé — fichier: %s", safe_name)
    except MegaClientError as exc:
        logger.error("Erreur Mega.nz — fichier: %s — %s", safe_name, exc)
        raise HTTPException(status_code=502, detail="Erreur de communication avec le serveur de stockage.")
    except Exception as exc:  # pragma: no cover — filet de sécurité
        logger.error("Erreur inattendue (upload) — fichier: %s", safe_name, exc_info=True)
        raise HTTPException(status_code=500, detail="Une erreur inattendue est survenue.")

    return {"message": "Document sécurisé avec succès", "filename": safe_name}
