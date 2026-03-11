import io
import magic
import pikepdf


class SanitizationError(Exception):
    """Levée quand un fichier PDF ne peut pas être validé ou nettoyé."""


def sanitize_pdf(file_bytes: bytes) -> io.BytesIO:
    """
    Valide le type MIME (magic bytes) et re-sérialise le PDF via pikepdf
    pour supprimer scripts, annotations actives et objets suspects.

    Args:
        file_bytes: Contenu brut du fichier uploadé.

    Returns:
        Un flux BytesIO contenant le PDF nettoyé.

    Raises:
        SanitizationError: Si le fichier n'est pas un PDF valide.
    """
    mime_type = magic.from_buffer(file_bytes[:2048], mime=True)
    if mime_type != "application/pdf":
        raise SanitizationError(
            f"Type MIME non autorisé : {mime_type}. Seul application/pdf est accepté."
        )

    try:
        with pikepdf.Pdf.open(io.BytesIO(file_bytes)) as pdf:
            clean_stream = io.BytesIO()
            pdf.save(clean_stream)

        clean_stream.seek(0)
        return clean_stream

    except pikepdf.PdfError:
        raise SanitizationError("Fichier PDF invalide ou corrompu.")
    except Exception:
        raise SanitizationError("Erreur lors du nettoyage du fichier.")
