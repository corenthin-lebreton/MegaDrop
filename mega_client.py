import contextlib
import io
import os
import tempfile

from mega import Mega


class MegaClientError(Exception):
    """Levée en cas d'échec de communication avec Mega.nz."""


def validate_config() -> None:
    """
    Vérifie que les variables d'environnement Mega sont présentes.
    Doit être appelée au démarrage de l'application.

    Raises:
        RuntimeError: Si MEGA_EMAIL ou MEGA_PASSWORD est absent.
    """
    missing = [var for var in ("MEGA_EMAIL", "MEGA_PASSWORD") if not os.getenv(var)]
    if missing:
        raise RuntimeError(
            f"Variables d'environnement manquantes : {', '.join(missing)}. "
            "Définissez-les via --env ou --env-file."
        )


def _get_or_create_folder(client, folder_name: str):
    """Retourne le handle du dossier Mega, le crée s'il n'existe pas."""
    folder = client.find(folder_name)
    if not folder:
        client.create_folder(folder_name)
        folder = client.find(folder_name)
    if not folder:
        raise MegaClientError(f"Impossible de trouver ou créer le dossier '{folder_name}'.")
    return folder


def upload_file_to_mega(filename: str, clean_pdf_stream: io.BytesIO) -> None:
    """
    Téléverse un PDF nettoyé vers Mega.nz dans le dossier configuré.

    Args:
        filename: Nom de destination sur Mega.nz.
        clean_pdf_stream: Flux BytesIO du PDF sanitisé.

    Raises:
        MegaClientError: En cas d'échec de l'upload.
    """
    mega_email = os.getenv("MEGA_EMAIL")
    mega_password = os.getenv("MEGA_PASSWORD")
    mega_folder = os.getenv("MEGA_FOLDER", "seadrop_uploads")

    if not mega_email or not mega_password:
        raise MegaClientError("Credentials Mega.nz non configurés.")

    try:
        client = Mega().login(mega_email, mega_password)
        folder = _get_or_create_folder(client, mega_folder)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(clean_pdf_stream.getvalue())
            tmp_path = tmp.name

        try:
            client.upload(tmp_path, folder[0], dest_filename=filename)
        finally:
            with contextlib.suppress(FileNotFoundError, OSError):
                os.remove(tmp_path)

    except MegaClientError:
        raise
    except Exception as exc:
        raise MegaClientError(f"Erreur lors de l'upload vers Mega.nz : {exc}") from exc
