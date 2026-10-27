import base64
import hashlib
import hmac
import io
import re
import secrets
import string
import struct
import time
from urllib.parse import quote

try:
    import pyotp
except ImportError:
    pyotp = None

try:
    import qrcode
    import qrcode.image.svg
except ImportError:
    qrcode = None


RECOVERY_CODE_ALPHABET = string.ascii_lowercase + string.digits
BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'


def generate_totp_secret(length=32):
    """Generate a random Base32 secret for TOTP enrollment."""
    if pyotp:
        return pyotp.random_base32(length=length)
    return ''.join(secrets.choice(BASE32_ALPHABET) for _ in range(length))


def get_totp_uri(secret, email, app_name='COMET', issuer=None):
    """Generate RFC 6238 otpauth:// provisioning URI."""
    brand = issuer or app_name or 'COMET'
    encoded_app = quote(brand)
    encoded_email = quote(email)
    return (
        f"otpauth://totp/{encoded_app}:{encoded_email}?"
        f"secret={secret}&issuer={encoded_app}&algorithm=SHA1&digits=6&period=30"
    )


def generate_totp_code(secret, t=None):
    """Generate current 6-digit TOTP code for testing / verification."""
    if pyotp:
        totp = pyotp.TOTP(secret, interval=30, digits=6)
        return totp.now()

    if t is None:
        t = time.time()
    counter = int(t // 30)
    key = base64.b32decode(secret, casefold=True)
    msg = struct.pack('>Q', counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[19] & 15
    code = (struct.unpack('>I', h[o:o+4])[0] & 0x7fffffff) % 1000000
    return f"{code:06d}"


def verify_totp_code(secret, code, window=1):
    """Verify a 6-digit TOTP code against a secret with window tolerance."""
    if not secret or not code:
        return False

    code = str(code).strip().replace(' ', '')
    if len(code) != 6 or not code.isdigit():
        return False

    if pyotp:
        totp = pyotp.TOTP(secret, interval=30, digits=6)
        return bool(totp.verify(code, valid_window=window))

    now = time.time()
    for offset in range(-window, window + 1):
        expected = generate_totp_code(secret, t=now + (offset * 30))
        if hmac.compare_digest(code, expected):
            return True
    return False


def generate_qr_svg(data):
    """Generate an SVG string for a QR code."""
    if not qrcode:
        return None

    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(data, image_factory=factory, box_size=10, border=2)
    buffer = io.BytesIO()
    img.save(buffer)
    return buffer.getvalue().decode('utf-8')


def generate_qr_data_uri(data):
    """Generate a data: URI containing the SVG QR code."""
    svg_text = generate_qr_svg(data)
    if not svg_text:
        return None
    encoded = quote(svg_text)
    return f"data:image/svg+xml;utf8,{encoded}"


def normalize_recovery_code(code):
    """Normalize recovery code by stripping spaces, hyphens, and converting to lowercase."""
    return re.sub(r'[\s\-]+', '', str(code or '')).lower()


def generate_recovery_codes(count=8):
    """Generate count recovery codes in format xxxx-xxxx."""
    codes = []
    for _ in range(count):
        part1 = ''.join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(4))
        part2 = ''.join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(4))
        codes.append(f"{part1}-{part2}")
    return codes


def hash_recovery_code(code):
    """Compute SHA-256 hash of normalized recovery code."""
    normalized = normalize_recovery_code(code)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def verify_recovery_code(code, expected_hash):
    """Verify raw recovery code against expected SHA-256 hash."""
    if not code or not expected_hash:
        return False
    actual_hash = hash_recovery_code(code)
    return hmac.compare_digest(actual_hash, expected_hash)


# Convenient aliases
generate_secret = generate_totp_secret
get_provisioning_uri = get_totp_uri
verify_totp = verify_totp_code
generate_qr_code_svg = generate_qr_data_uri
