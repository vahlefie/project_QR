import re
from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request

ATTENDANCE_CHART_BIN_MINUTES = 30
ATTENDANCE_LAST_RANGE_MINUTES = {
    "last_30m": 30,
    "last_1h": 60,
    "last_3h": 3 * 60,
    "last_6h": 6 * 60,
    "last_12h": 12 * 60,
}
DEFAULT_ATTENDANCE_RANGE_MODE = "last_30m"
MAX_ATTENDANCE_CUSTOM_RANGE = timedelta(hours=24)
MAX_VERIFICATION_STAFF_SLICES = 6
MONTH_ABBREVIATION_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "mei": 5,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "agu": 8,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "oct": 10,
    "nov": 11,
    "des": 12,
    "dec": 12,
}


# Fungsi untuk mengambil nilai field dari model tamu atau row demo berbentuk dict.
def get_guest_chart_value(guest, field_name, default=None):
    if isinstance(guest, dict):
        return guest.get(field_name, default)
    return getattr(guest, field_name, default)


# Fungsi untuk membuat key tab status tamu yang stabil untuk payload chart.
def build_guest_status_key(status):
    return str(status or "").strip().lower().replace(" ", "-")


# Fungsi untuk memformat waktu chart.
def format_chart_time(value, include_date=False):
    if include_date:
        return value.strftime("%d/%m %H:%M")
    return value.strftime("%H:%M")


# Fungsi untuk mengambil waktu kehadiran dalam datetime naive.
def get_guest_attendance_datetime(guest, fallback_year=None):
    attendance_value = get_guest_chart_value(guest, "kehadiran")
    if not attendance_value:
        return None

    if isinstance(attendance_value, datetime):
        return attendance_value.replace(tzinfo=None)

    attendance_text = str(attendance_value).strip()
    try:
        return datetime.fromisoformat(attendance_text).replace(tzinfo=None)
    except ValueError:
        pass

    dated_time_match = re.search(r"\b(\d{1,2})[-/\s]([A-Za-z]{3})\s+(\d{1,2}):(\d{2})\b", attendance_text)
    if dated_time_match:
        day = int(dated_time_match.group(1))
        month = MONTH_ABBREVIATION_NUMBERS.get(dated_time_match.group(2).lower())
        hour = int(dated_time_match.group(3))
        minute = int(dated_time_match.group(4))
        if month and hour <= 23 and minute <= 59:
            try:
                return datetime(fallback_year or datetime.now().year, month, day, hour, minute)
            except ValueError:
                return None

    time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", attendance_text)
    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    if hour > 23 or minute > 59:
        return None
    return datetime(fallback_year or datetime.now().year, 1, 1, hour, minute)


# Fungsi untuk membulatkan waktu turun ke interval chart.
def floor_chart_datetime(value, interval_minutes=ATTENDANCE_CHART_BIN_MINUTES):
    floored_minute = (value.minute // interval_minutes) * interval_minutes
    return value.replace(minute=floored_minute, second=0, microsecond=0)


# Fungsi untuk membulatkan waktu naik ke interval chart.
def ceil_chart_datetime(value, interval_minutes=ATTENDANCE_CHART_BIN_MINUTES):
    floored_value = floor_chart_datetime(value, interval_minutes=interval_minutes)
    if floored_value == value.replace(second=0, microsecond=0):
        return floored_value
    return floored_value + timedelta(minutes=interval_minutes)


# Fungsi untuk membaca datetime-local dari filter dashboard.
def parse_dashboard_filter_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        return None


# Fungsi untuk membangun filter waktu chart dari query string dashboard.
def build_dashboard_time_filter(args, now):
    now = now.replace(second=0, microsecond=0)
    range_mode = (args.get("range_mode") or DEFAULT_ATTENDANCE_RANGE_MODE).strip()
    if range_mode not in ATTENDANCE_LAST_RANGE_MINUTES and range_mode != "custom":
        range_mode = DEFAULT_ATTENDANCE_RANGE_MODE

    if range_mode in ATTENDANCE_LAST_RANGE_MINUTES:
        end_at = now
        start_at = end_at - timedelta(minutes=ATTENDANCE_LAST_RANGE_MINUTES[range_mode])
        return start_at, end_at, range_mode

    if range_mode == "custom":
        start_at = parse_dashboard_filter_datetime(args.get("start_at"))
        end_at = parse_dashboard_filter_datetime(args.get("end_at"))
        if not start_at and not end_at:
            end_at = now
            start_at = end_at - timedelta(minutes=ATTENDANCE_LAST_RANGE_MINUTES[DEFAULT_ATTENDANCE_RANGE_MODE])
            return start_at, end_at, DEFAULT_ATTENDANCE_RANGE_MODE

        if not end_at:
            end_at = now
        if not start_at:
            start_at = end_at - MAX_ATTENDANCE_CUSTOM_RANGE

        if end_at > now:
            end_at = now
        if start_at > now:
            start_at = now
        if start_at >= end_at:
            start_at = end_at - timedelta(minutes=ATTENDANCE_CHART_BIN_MINUTES)
        if end_at - start_at > MAX_ATTENDANCE_CUSTOM_RANGE:
            start_at = end_at - MAX_ATTENDANCE_CUSTOM_RANGE
        return start_at, end_at, range_mode

    end_at = now
    start_at = end_at - timedelta(minutes=ATTENDANCE_LAST_RANGE_MINUTES[DEFAULT_ATTENDANCE_RANGE_MODE])
    return start_at, end_at, DEFAULT_ATTENDANCE_RANGE_MODE


# Fungsi untuk memfilter daftar tamu berdasarkan waktu kehadiran.
def filter_guests_by_attendance_range(guests, start_at=None, end_at=None):
    if not start_at and not end_at:
        return list(guests)

    filtered_guests = []
    for guest in guests:
        attendance_at = get_guest_attendance_datetime(guest)
        if not attendance_at:
            continue
        if start_at and attendance_at < start_at:
            continue
        if end_at and attendance_at > end_at:
            continue
        filtered_guests.append(guest)
    return filtered_guests


# Fungsi untuk menghitung jumlah hadir per slot 30 menit.
def build_guest_attendance_time_series(guests, start_at=None, end_at=None):
    attendance_items = []
    for guest in guests:
        attendance_at = get_guest_attendance_datetime(guest)
        if attendance_at:
            attendance_items.append((guest, attendance_at))

    if start_at:
        chart_start = floor_chart_datetime(start_at)
    elif attendance_items:
        chart_start = floor_chart_datetime(min(attendance_at for _, attendance_at in attendance_items))
    else:
        chart_start = None

    if end_at:
        chart_end = ceil_chart_datetime(end_at)
    elif attendance_items:
        chart_end = ceil_chart_datetime(max(attendance_at for _, attendance_at in attendance_items))
    else:
        chart_end = None

    if not chart_start or not chart_end:
        return {
            "bins": [],
            "max_count": 0,
            "total_count": 0,
            "range_label": "Belum ada waktu kehadiran tercatat",
        }

    if chart_end <= chart_start:
        chart_end = chart_start + timedelta(minutes=ATTENDANCE_CHART_BIN_MINUTES)

    bins = []
    current_start = chart_start
    include_date = chart_start.date() != chart_end.date()
    while current_start < chart_end:
        current_end = current_start + timedelta(minutes=ATTENDANCE_CHART_BIN_MINUTES)
        bins.append(
            {
                "start": current_start.isoformat(timespec="minutes"),
                "end": current_end.isoformat(timespec="minutes"),
                "label": format_chart_time(current_start, include_date=include_date),
                "range_label": (
                    f"{format_chart_time(current_start, include_date=include_date)}-"
                    f"{format_chart_time(current_end, include_date=include_date)}"
                ),
                "count": 0,
            }
        )
        current_start = current_end

    for _, attendance_at in attendance_items:
        if attendance_at < chart_start or attendance_at > chart_end:
            continue
        for index, time_bin in enumerate(bins):
            bin_start = datetime.fromisoformat(time_bin["start"])
            bin_end = datetime.fromisoformat(time_bin["end"])
            is_last_bin = index == len(bins) - 1
            if bin_start <= attendance_at < bin_end or (is_last_bin and attendance_at <= bin_end):
                bins[index]["count"] += 1
                break

    max_count = max((time_bin["count"] for time_bin in bins), default=0)
    for time_bin in bins:
        time_bin["percent"] = round((time_bin["count"] / max_count) * 100) if max_count else 0

    return {
        "bins": bins,
        "max_count": max_count,
        "total_count": sum(time_bin["count"] for time_bin in bins),
        "range_label": (f"{chart_start.strftime('%d/%m/%Y %H:%M')} - {chart_end.strftime('%d/%m/%Y %H:%M')}"),
    }


# Fungsi untuk mengambil label staff/verifikator dari data live atau demo.
def get_guest_verification_label(guest):
    staff_name = get_guest_chart_value(guest, "verified_by_staff_name")
    if staff_name:
        return str(staff_name).strip()

    staff_id = get_guest_chart_value(guest, "verified_by_staff_id")
    if staff_id:
        return f"Staff #{staff_id}"

    demo_verifier = get_guest_chart_value(guest, "verifikasi")
    if demo_verifier:
        return str(demo_verifier).strip()

    return ""


# Fungsi untuk menghitung distribusi jumlah verifikasi per staff.
def build_guest_staff_verification_chart(guests):
    verification_counts = Counter()
    for guest in guests:
        verifier_label = get_guest_verification_label(guest)
        if verifier_label:
            verification_counts[verifier_label] += 1

    total_count = sum(verification_counts.values())
    sorted_items = sorted(verification_counts.items(), key=lambda item: (-item[1], item[0]))
    if len(sorted_items) > MAX_VERIFICATION_STAFF_SLICES:
        visible_items = sorted_items[: MAX_VERIFICATION_STAFF_SLICES - 1]
        other_count = sum(count for _, count in sorted_items[MAX_VERIFICATION_STAFF_SLICES - 1 :])
        sorted_items = [*visible_items, ("Lainnya", other_count)]

    return {
        "total_count": total_count,
        "slices": [
            {
                "label": label,
                "count": count,
                "percent": round((count / total_count) * 100) if total_count else 0,
            }
            for label, count in sorted_items
        ],
    }


# Fungsi untuk menghitung segmentasi hadir/belum hadir pada satu status tamu.
def build_guest_attendance_segment(guests, status):
    status_key = build_guest_status_key(status)
    status_guests = [
        guest for guest in guests if build_guest_status_key(get_guest_chart_value(guest, "status")) == status_key
    ]
    total_count = len(status_guests)
    attended_count = sum(1 for guest in status_guests if get_guest_chart_value(guest, "kehadiran"))
    pending_count = total_count - attended_count

    return {
        "key": status_key,
        "label": f"Tamu {status}",
        "total_count": total_count,
        "attended_count": attended_count,
        "pending_count": pending_count,
        "attended_percent": round((attended_count / total_count) * 100) if total_count else 0,
        "pending_percent": round((pending_count / total_count) * 100) if total_count else 0,
    }


# Fungsi untuk membangun ringkasan chart tamu milik client.
def build_guest_chart_context(
    deps, guests, source_label, source_note="", start_at=None, end_at=None, range_mode=DEFAULT_ATTENDANCE_RANGE_MODE
):
    total_guests = len(guests)
    attended_count = sum(1 for guest in guests if get_guest_chart_value(guest, "kehadiran"))
    pending_count = total_guests - attended_count
    attended_percent = round((attended_count / total_guests) * 100) if total_guests else 0
    analytics_guests = filter_guests_by_attendance_range(guests, start_at=start_at, end_at=end_at)

    status_labels = list(deps.GUEST_STATUS_OPTIONS)
    status_counts = {status: 0 for status in status_labels}
    fallback_status = deps.DEFAULT_GUEST_STATUS
    for guest in guests:
        raw_status = get_guest_chart_value(guest, "status") or fallback_status
        status = str(raw_status).strip() or fallback_status
        if status not in status_counts:
            status_counts[status] = 0
            status_labels.append(status)
        status_counts[status] += 1

    max_status_count = max(status_counts.values(), default=0)
    status_chart = []
    for status in status_labels:
        count = status_counts.get(status, 0)
        status_chart.append(
            {
                "label": status,
                "count": count,
                "percent": round((count / total_guests) * 100) if total_guests else 0,
                "bar_percent": round((count / max_status_count) * 100) if max_status_count else 0,
            }
        )

    return {
        "total_guests": total_guests,
        "attended_count": attended_count,
        "pending_count": pending_count,
        "attended_percent": attended_percent,
        "pending_percent": 100 - attended_percent if total_guests else 0,
        "status_chart": status_chart,
        "attendance_segments": [build_guest_attendance_segment(guests, status) for status in deps.GUEST_STATUS_OPTIONS],
        "attendance_time_series": build_guest_attendance_time_series(
            analytics_guests,
            start_at=start_at,
            end_at=end_at,
        ),
        "staff_verification_chart": build_guest_staff_verification_chart(analytics_guests),
        "range_mode": range_mode,
        "source_label": source_label,
        "source_note": source_note,
    }


# Fungsi untuk membangun pilihan chart live dan demo pada dashboard client.
def build_guest_chart_modes(deps, owner_user, start_at=None, end_at=None, range_mode=DEFAULT_ATTENDANCE_RANGE_MODE):
    live_guests = deps.Guests.query.filter_by(user_id=owner_user.id).all()
    demo_guests = deps.DemoGuest.query.order_by(deps.DemoGuest.no.asc(), deps.DemoGuest.id.asc()).all()

    demo_note = (
        f"{len(demo_guests)} baris dari tabel demo_guests" if demo_guests else "Tabel demo_guests belum berisi data."
    )
    return {
        "live": build_guest_chart_context(
            deps,
            live_guests,
            "Live",
            "Data tamu client",
            start_at=start_at,
            end_at=end_at,
            range_mode=range_mode,
        ),
        "demo": build_guest_chart_context(
            deps,
            demo_guests,
            "Demo",
            demo_note,
        ),
    }


# Fungsi untuk membuat Blueprint dashboard dan profile akun.
def create_dashboard_blueprint(deps):
    dashboard_bp = Blueprint("dashboard", __name__)

    # Fungsi untuk menampilkan dashboard admin.
    @dashboard_bp.route("/admin/dashboard")
    @deps.login_required
    @deps.role_required(deps.ROLE_ADMIN)
    # Route untuk menampilkan dashboard admin.
    def admin_dashboard():
        return render_template("admin_dashboard.html", user=deps.get_current_user_display_name())

    # Fungsi untuk menampilkan dashboard super admin.
    @dashboard_bp.route("/super-admin/dashboard")
    @deps.login_required
    @deps.role_required(deps.ROLE_SUPER_ADMIN)
    # Route untuk menampilkan dashboard super admin.
    def super_admin_dashboard():
        current_user = deps.get_current_user()
        return render_template(
            "super_admin_dashboard.html",
            user=deps.get_user_display_name(current_user),
        )

    # Fungsi untuk menampilkan dashboard user.
    @dashboard_bp.route("/user/dashboard")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk menampilkan dashboard user.
    def user_dashboard():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")
        is_client_active = deps.calculate_account_activation_status(current_user)
        if is_client_active:
            start_at, end_at, range_mode = build_dashboard_time_filter(request.args, deps.get_utc_naive_datetime())
            guest_chart_modes = build_guest_chart_modes(
                deps,
                current_user,
                start_at=start_at,
                end_at=end_at,
                range_mode=range_mode,
            )
        else:
            guest_chart_modes = {}
        return render_template(
            "user_dashboard.html",
            user=deps.get_user_display_name(current_user),
            attendance_url=deps.build_guest_attendance_url(current_user),
            attendance_qr_url=deps.build_guest_attendance_qr_url(current_user),
            is_client_active=is_client_active,
            guest_chart_modes=guest_chart_modes,
        )

    # Fungsi untuk mengambil data chart live dashboard client.
    @dashboard_bp.route("/user/dashboard/chart-data")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route JSON untuk update otomatis chart dashboard.
    def user_dashboard_chart_data():
        current_user = deps.get_current_user()
        if not current_user:
            return jsonify({"status": "error", "message": "Login diperlukan."}), 401

        is_client_active = deps.calculate_account_activation_status(current_user)
        if not is_client_active:
            return jsonify({"status": "error", "message": "Client tidak aktif."}), 403

        start_at, end_at, range_mode = build_dashboard_time_filter(request.args, deps.get_utc_naive_datetime())
        live_guests = deps.Guests.query.filter_by(user_id=current_user.id).all()
        chart = build_guest_chart_context(
            deps,
            live_guests,
            "Live",
            "Data tamu client",
            start_at=start_at,
            end_at=end_at,
            range_mode=range_mode,
        )
        return jsonify({"status": "success", "chart": chart})

    # Fungsi untuk menampilkan profil user yang sedang login.
    @dashboard_bp.route("/profile")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk menampilkan halaman profil user.
    def profile():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")
        is_client_active = deps.calculate_account_activation_status(current_user)
        latest_payment = (
            deps.BillingPayment.query.filter_by(user_id=current_user.id)
            .order_by(deps.BillingPayment.payment_date.desc(), deps.BillingPayment.id.desc())
            .first()
        )
        return render_template(
            "user_profile.html",
            user=deps.get_user_display_name(current_user),
            account=current_user,
            payment=latest_payment,
            is_client_active=is_client_active,
            profile_event_name=latest_payment.event_name if latest_payment else None,
            profile_package_name=latest_payment.package_name if latest_payment else None,
            profile_period_start=latest_payment.period_start if latest_payment else None,
            profile_period_end=latest_payment.period_end if latest_payment else None,
        )

    # Fungsi untuk menampilkan histori pembayaran user yang sedang login.
    @dashboard_bp.route("/user/payment")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk menampilkan histori pembayaran client.
    def user_payment():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")

        payments = (
            deps.BillingPayment.query.filter_by(user_id=current_user.id)
            .order_by(deps.BillingPayment.payment_date.desc(), deps.BillingPayment.id.desc())
            .all()
        )
        return render_template(
            "user_payment.html",
            user=deps.get_user_display_name(current_user),
            account=current_user,
            payments=payments,
        )

    return dashboard_bp
