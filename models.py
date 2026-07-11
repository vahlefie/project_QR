from datetime import datetime

from constants import APP_TIMEZONE, DEFAULT_GUEST_STATUS, GUEST_ADDED_BY_MAX_LENGTH, ROLE_USER
from extensions import db


# Model User dipakai untuk akun super_admin, admin, dan user.
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(15), unique=True)
    nama = db.Column(db.String(35))
    no_hp = db.Column(db.Integer, unique=True)  # format diawali 62 tanpa tanda + atau spasi
    email = db.Column(db.String(30), unique=True)
    perusahaan = db.Column(db.String(50))
    alamat = db.Column(db.String(100))
    kota = db.Column(db.String(60))
    provinsi = db.Column(db.String(50))
    aktivasi = db.Column(db.Boolean, default=False)
    paket = db.Column(db.String(10))
    tgl_daftar = db.Column(db.Date)
    periode_akhir = db.Column("tgl_expired", db.Date)
    password = db.Column(db.String(255))
    role = db.Column(db.String(20), default=ROLE_USER)
    must_reset_password = db.Column(db.Boolean, default=False)
    active_session_token = db.Column(db.String(128))
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    blocked_at = db.Column(db.DateTime)
    attendance_token_nonce = db.Column(db.String(64))
    attendance_token_generated_at = db.Column(db.DateTime)
    guests = db.relationship("Guests", back_populates="owner", lazy=True)
    staff_members = db.relationship("Staff", back_populates="owner", lazy=True, cascade="all, delete-orphan")
    billing_payments = db.relationship(
        "BillingPayment",
        back_populates="client",
        lazy=True,
        cascade="all, delete-orphan",
    )


# Model BillingPayment dipakai untuk histori pembayaran dan pencatatan kas masuk client.
class BillingPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payment_time = db.Column(db.Time)
    amount = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(30))
    origin_bank = db.Column(db.String(60))
    account_number = db.Column(db.String(40))
    payment_type = db.Column(db.String(20))
    package_name = db.Column(db.String(10))
    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)
    event_name = db.Column(db.String(120))
    status = db.Column(db.String(20), default="verified", nullable=False)
    notes = db.Column(db.String(255))
    created_by = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None))
    client = db.relationship("User", back_populates="billing_payments")


# Model EventArchive dipakai untuk mencatat backup final data tamu per event client.
class EventArchive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    event_name = db.Column(db.String(120), nullable=False)
    package_name = db.Column(db.String(10))
    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date, index=True)
    csv_path = db.Column(db.String(255))
    tar_path = db.Column(db.String(255))
    guest_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="csv_ready", nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None))
    archived_at = db.Column(db.DateTime)
    owner = db.relationship("User")


# Model Guests dipakai untuk data tamu/calon customer.
class Guests(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    no = db.Column(db.Integer)
    nama = db.Column(db.String(35))
    no_hp = db.Column(db.String(15))
    email = db.Column(db.String(30))
    status = db.Column(db.String(10), default=DEFAULT_GUEST_STATUS)
    added_by = db.Column(db.String(GUEST_ADDED_BY_MAX_LENGTH))
    kehadiran = db.Column(db.DateTime)
    jumlah_orang = db.Column(db.Integer, default=1, nullable=False)
    verified_by_staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=True)
    verified_by_staff_name = db.Column(db.String(35))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=True)
    owner = db.relationship("User", back_populates="guests")
    short_url = db.relationship("GuestShortUrl", back_populates="guest", uselist=False, cascade="all, delete-orphan")


# Model DemoGuest dipakai sebagai sumber data dummy dashboard mode demo.
class DemoGuest(db.Model):
    __tablename__ = "demo_guests"

    id = db.Column(db.Integer, primary_key=True)
    no = db.Column(db.Integer, index=True)
    nama = db.Column(db.String(60))
    no_hp = db.Column(db.String(20))
    email = db.Column(db.String(120))
    status = db.Column(db.String(20), default=DEFAULT_GUEST_STATUS)
    kehadiran = db.Column(db.String(30))
    verifikasi = db.Column(db.String(60))
    source_file = db.Column(db.String(120))


# Model GuestShortUrl dipakai untuk URL pendek halaman QR tamu.
class GuestShortUrl(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey("guests.id"), unique=True, index=True, nullable=False)
    short_code = db.Column(db.String(120), unique=True, index=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None),
        onupdate=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None),
    )
    guest = db.relationship("Guests", back_populates="short_url")


# Model AttendanceVerificationRequest dipakai untuk antrean konfirmasi kehadiran oleh staff.
class AttendanceVerificationRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    target_staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), index=True)
    guest_id = db.Column(db.Integer, db.ForeignKey("guests.id"), index=True)
    no_hp = db.Column(db.String(15))
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    source = db.Column(db.String(20), default="phone", nullable=False)
    message = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None))
    expires_at = db.Column(db.DateTime, index=True)
    confirmed_at = db.Column(db.DateTime)
    confirmed_by_staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"))
    confirmed_by_staff_name = db.Column(db.String(35))
    owner = db.relationship("User")
    target_staff = db.relationship("Staff", foreign_keys=[target_staff_id])
    guest = db.relationship("Guests")
    dismissals = db.relationship(
        "AttendanceVerificationDismissal",
        back_populates="verification_request",
        lazy=True,
        cascade="all, delete-orphan",
    )


# Model AttendanceVerificationDismissal mencatat staff yang menolak/menutup request pending.
class AttendanceVerificationDismissal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey("attendance_verification_request.id"),
        index=True,
        nullable=False,
    )
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), index=True, nullable=False)
    dismissed_at = db.Column(db.DateTime, default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None))
    verification_request = db.relationship("AttendanceVerificationRequest", back_populates="dismissals")
    staff = db.relationship("Staff")
    __table_args__ = (db.UniqueConstraint("request_id", "staff_id", name="uq_attendance_request_staff"),)


# Model WhatsappSetting dipakai untuk konfigurasi pengiriman WhatsApp global.
class WhatsappSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    send_mode = db.Column(db.String(20), default="development", nullable=False)
    phone_number = db.Column(db.String(15))
    api_token = db.Column(db.String(512))
    api_phone_number_id = db.Column(db.String(120))
    active_template_id = db.Column(db.Integer)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None),
        onupdate=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None),
    )


# Model WhatsappTemplate dipakai untuk menyimpan template pesan WhatsApp.
class WhatsappTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    body = db.Column(db.Text, default="")
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None),
        onupdate=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None),
    )


# Model Staff untuk akses pengelolaan data tamu milik client tertentu.
class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    nama = db.Column(db.String(35), nullable=False)
    no_hp = db.Column(db.String(15), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None))
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    blocked_at = db.Column(db.DateTime)
    block_reason = db.Column(db.String(100))
    attendance_token_nonce = db.Column(db.String(64))
    attendance_token_generated_at = db.Column(db.DateTime)
    owner = db.relationship("User", back_populates="staff_members")
    access_links = db.relationship("StaffAccess", back_populates="staff", lazy=True, cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint("owner_user_id", "no_hp", name="uq_staff_owner_no_hp"),)


# Model StaffAccess untuk menyimpan URL random dan PIN login staff.
class StaffAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), index=True, nullable=False)
    token_hash = db.Column(db.String(64), unique=True, index=True, nullable=False)
    pin_hash = db.Column(db.String(255), nullable=False)
    failed_pin_attempts = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(APP_TIMEZONE).replace(tzinfo=None))
    last_activity_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)
    revoked_by = db.Column(db.String(20))
    revoked_reason = db.Column(db.String(100))
    staff = db.relationship("Staff", back_populates="access_links")


# Model LoginThrottle untuk menyimpan percobaan login gagal dan lockout sementara.
class LoginThrottle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scope_key = db.Column(db.String(64), unique=True, index=True, nullable=False)
    identifier = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    failed_attempts = db.Column(db.Integer, default=0)
    first_failed_at = db.Column(db.DateTime)
    last_failed_at = db.Column(db.DateTime)
    locked_until = db.Column(db.DateTime)
