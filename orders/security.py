from pathlib import Path

from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ValidationError


MAX_DRIVER_LICENSE_SIZE = 5 * 1024 * 1024

LICENSE_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}


def is_driver(user):
    """Return True only for authenticated users with a driver profile."""
    return (
        user.is_authenticated
        and hasattr(user, "driver_profile")
    )


driver_required = user_passes_test(
    is_driver,
    login_url="/driver/login/",
)


def validate_driver_license_file(uploaded_file):
    """Validate driver licence size, extension and actual file signature."""

    if not uploaded_file:
        raise ValidationError("Please select a driver licence file.")

    if uploaded_file.size > MAX_DRIVER_LICENSE_SIZE:
        raise ValidationError("Driver licence files must not exceed 5 MB.")

    extension = Path(uploaded_file.name).suffix.lower()
    expected_signatures = LICENSE_SIGNATURES.get(extension)

    if not expected_signatures:
        raise ValidationError(
            "Only PDF, JPG, JPEG and PNG files are accepted."
        )

    try:
        uploaded_file.seek(0)
        file_header = uploaded_file.read(8)
        uploaded_file.seek(0)
    except (AttributeError, OSError):
        raise ValidationError("The uploaded file could not be read.")

    if not any(file_header.startswith(signature) for signature in expected_signatures):
        raise ValidationError(
            "The file contents do not match the selected file type."
        )

    return uploaded_file
