import io
import qrcode
from aiogram.types import BufferedInputFile


def generate_qr_code_file(data: str, filename: str = "subscription_qr.png") -> BufferedInputFile:
    """
    Generate an in-memory PNG QR code for a subscription URL.
    Returns an aiogram BufferedInputFile ready for message.answer_photo.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return BufferedInputFile(buffer.getvalue(), filename=filename)
