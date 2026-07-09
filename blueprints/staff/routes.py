from flask import Blueprint, g, jsonify, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash


# Fungsi untuk membuat Blueprint session dan data staff.
def create_staff_blueprint(deps):
    staff_bp = Blueprint("staff", __name__)

    # Fungsi untuk menampilkan pesan session staff yang sudah berakhir.
    @staff_bp.route("/staff/session-expired")
    # Route untuk menampilkan halaman sesi staff berakhir.
    def staff_session_expired():
        is_logout = request.args.get("reason") == "logout"
        message = "Logout staff berhasil." if is_logout else "Silakan minta client membuka akses staff kembali."
        status_code = 200 if is_logout else 401
        return render_template("staff_session_expired.html", message=message), status_code

    # Fungsi untuk memverifikasi PIN URL random staff dan membuat session staff.
    @staff_bp.route("/staff/access/<access_token>", methods=["GET", "POST"])
    # Route untuk memproses login akses staff.
    def staff_access_login(access_token):
        staff_access = deps.get_staff_access_by_token(access_token)
        staff = staff_access.staff if staff_access else None

        if (
            not staff_access
            or not staff_access.is_active
            or staff_access.revoked_at
            or not staff
            or not deps.get_staff_owner(staff)
            or deps.is_staff_access_idle_expired(staff_access)
        ):
            if staff_access and staff_access.is_active and not staff_access.revoked_at:
                deps.revoke_staff_access(
                    staff_access,
                    revoked_by="system",
                    reason="idle_timeout_or_invalid",
                )
                deps.db.session.commit()
            response = render_template(
                "staff_pin_verify.html",
                error="Link akses staff tidak valid atau sudah berakhir.",
                access_token=access_token,
            )
            return response, 401

        if staff.is_blocked:
            return (
                render_template(
                    "staff_pin_verify.html",
                    error="Staff sedang diblokir. Hubungi client untuk membuka blokir.",
                    access_token=access_token,
                ),
                403,
            )

        if request.method == "POST":
            pin = deps.get_form_text("pin")
            if check_password_hash(staff_access.pin_hash, pin):
                staff_access.failed_pin_attempts = 0
                staff_access.last_activity_at = deps.get_utc_naive_datetime()
                deps.db.session.commit()
                deps.log_staff_activity_event(
                    "LOGIN_STAFF_WITH_PIN",
                    staff,
                    details={"staff_access_id": staff_access.id},
                )
                response = redirect(url_for("staff.staff_data"))
                return deps.set_staff_session_cookie(response, staff_access)

            staff_access.failed_pin_attempts += 1
            remaining_attempts = max(
                deps.STAFF_PIN_MAX_ATTEMPTS - staff_access.failed_pin_attempts,
                0,
            )
            if staff_access.failed_pin_attempts >= deps.STAFF_PIN_MAX_ATTEMPTS:
                deps.block_staff_account(staff, reason="pin_failed")
                deps.db.session.commit()
                deps.log_staff_activity_event(
                    "BLOCK_STAFF_PIN_FAILED",
                    staff,
                    details={
                        "staff_access_id": staff_access.id,
                        "failed_pin_attempts": staff_access.failed_pin_attempts,
                    },
                    level="WARN",
                )
                return (
                    render_template(
                        "staff_pin_verify.html",
                        error="PIN salah 3 kali. Staff diblokir dan akses dicabut.",
                        access_token=access_token,
                    ),
                    403,
                )

            deps.db.session.commit()
            return (
                render_template(
                    "staff_pin_verify.html",
                    staff=staff,
                    error=f"PIN salah. Sisa percobaan: {remaining_attempts}.",
                    access_token=access_token,
                ),
                400,
            )

        return render_template("staff_pin_verify.html", staff=staff, access_token=access_token)

    # Fungsi untuk menampilkan data tamu client yang dikelola staff.
    @staff_bp.route("/staff/data")
    @deps.staff_login_required
    # Route untuk menampilkan data tamu dari sesi staff.
    def staff_data():
        staff = deps.get_current_staff()
        if not staff or not deps.get_staff_owner(staff):
            response = redirect(url_for("staff.staff_session_expired"))
            return deps.delete_staff_session_cookie(response)

        search = request.args.get("search", "")
        page = deps.parse_int(request.args.get("page"), 1)
        per_page = deps.parse_int(request.args.get("per_page"), 10)
        sort_by = request.args.get("sort_by", "latest")

        context = deps.build_staff_guest_context(staff, search, page, per_page, sort_by)
        context["message"] = request.args.get("message", "")
        return render_template("user_data.html", **context)

    # Fungsi untuk menambahkan data tamu manual oleh staff.
    @staff_bp.route("/staff/guests/new", methods=["POST"])
    @deps.staff_login_required
    # Route untuk menambahkan tamu melalui sesi staff.
    def add_staff_guest():
        staff = deps.get_current_staff()
        owner_user = deps.get_staff_owner(staff)
        if not staff or not owner_user:
            response = redirect(url_for("staff.staff_session_expired"))
            return deps.delete_staff_session_cookie(response)

        form_data = {
            "nama": request.form.get("nama", ""),
            "no_hp": request.form.get("no_hp", ""),
            "email": request.form.get("email", ""),
            "status": request.form.get("status", deps.DEFAULT_GUEST_STATUS),
        }
        guest_data = deps.build_manual_guest_data(
            form_data,
            owner_user,
            added_by=deps.build_staff_guest_added_by(staff),
        )

        if not guest_data:
            context = deps.build_staff_guest_context(
                staff,
                request.form.get("search", ""),
                deps.parse_int(request.form.get("page"), 1),
                deps.parse_int(request.form.get("per_page"), 10),
                request.form.get("sort_by", "latest"),
            )
            context["add_guest_error"] = "Nama dan No HP wajib diisi dengan format valid."
            context["add_guest_form"] = form_data
            return render_template("user_data.html", **context), 400
        if deps.is_guest_phone_registered(owner_user, guest_data["no_hp"]):
            context = deps.build_staff_guest_context(
                staff,
                request.form.get("search", ""),
                deps.parse_int(request.form.get("page"), 1),
                deps.parse_int(request.form.get("per_page"), 10),
                request.form.get("sort_by", "latest"),
            )
            context["add_guest_error"] = "No HP sudah terdaftar."
            context["add_guest_form"] = form_data
            return render_template("user_data.html", **context), 400

        guest = deps.Guests()
        guest.no = guest_data["no"]
        guest.nama = guest_data["nama"]
        guest.no_hp = guest_data["no_hp"]
        guest.email = guest_data["email"]
        guest.status = guest_data["status"]
        guest.added_by = guest_data.get("added_by")
        guest.user_id = owner_user.id
        deps.db.session.add(guest)
        deps.db.session.commit()
        deps.log_staff_activity_event(
            "CREATE_GUEST_ROW",
            staff,
            details={
                "guest_id": guest.id,
                "owner_user_id": owner_user.id,
                "guest_name": guest.nama,
            },
        )
        return redirect(url_for("staff.staff_data", message="Data tamu berhasil ditambahkan."))

    # Fungsi untuk memperbarui status tamu oleh staff.
    @staff_bp.route("/staff/guests/<int:guest_id>/status", methods=["POST"])
    @deps.staff_login_required
    # Route untuk memperbarui status tamu melalui staff.
    def update_staff_guest_status(guest_id):
        staff = deps.get_current_staff()
        if not staff:
            response = redirect(url_for("staff.staff_session_expired"))
            return deps.delete_staff_session_cookie(response)

        guest = deps.get_accessible_staff_guest(staff, guest_id)
        if not guest:
            return "Data tamu tidak ditemukan", 404

        old_status = guest.status
        guest.status = deps.clean_guest_status(request.form.get("status"))
        deps.db.session.commit()
        deps.log_staff_activity_event(
            "UPDATE_GUEST_STATUS",
            staff,
            details={
                "guest_id": guest.id,
                "owner_user_id": guest.user_id,
                "old_status": old_status,
                "new_status": guest.status,
            },
        )
        return deps.build_staff_guest_table_redirect()

    # Fungsi untuk menghapus baris data tamu oleh staff.
    @staff_bp.route("/staff/guests/<int:guest_id>/delete", methods=["POST"])
    @deps.staff_login_required
    # Route untuk menghapus tamu melalui staff.
    def delete_staff_guest_row(guest_id):
        staff = deps.get_current_staff()
        if not staff:
            response = redirect(url_for("staff.staff_session_expired"))
            return deps.delete_staff_session_cookie(response)

        guest = deps.get_accessible_staff_guest(staff, guest_id)
        if not guest:
            return "Data tamu tidak ditemukan", 404

        deleted_guest_details = {
            "guest_id": guest.id,
            "owner_user_id": guest.user_id,
            "guest_name": guest.nama,
        }
        deps.db.session.delete(guest)
        deps.db.session.commit()
        deps.log_staff_activity_event("DELETE_GUEST_ROW", staff, details=deleted_guest_details)
        return deps.build_staff_guest_table_redirect()

    # Fungsi untuk mengambil popup request verifikasi kehadiran terbaru untuk staff.
    @staff_bp.route("/staff/attendance-notification")
    @deps.staff_login_required
    # Route polling popup request verifikasi kehadiran staff.
    def staff_attendance_notification():
        staff = deps.get_current_staff()
        notification = deps.get_staff_attendance_notification(staff)
        return jsonify({"notification": notification})

    # Fungsi untuk mengonfirmasi request verifikasi kehadiran.
    @staff_bp.route("/staff/attendance-notification/<int:request_id>/confirm", methods=["POST"])
    @deps.staff_login_required
    # Route konfirmasi kehadiran oleh staff.
    def confirm_staff_attendance_notification(request_id):
        staff = deps.get_current_staff()
        result = deps.confirm_attendance_verification_request(staff, request_id)
        status_code = 200 if result.get("status") in {"confirmed", "already_verified"} else 400
        if result.get("status") == "not_found":
            status_code = 404
        return jsonify(result), status_code

    # Fungsi untuk menolak/menutup request verifikasi kehadiran untuk staff ini.
    @staff_bp.route("/staff/attendance-notification/<int:request_id>/reject", methods=["POST"])
    @deps.staff_login_required
    # Route tolak atau tutup popup request verifikasi staff.
    def reject_staff_attendance_notification(request_id):
        staff = deps.get_current_staff()
        result = deps.reject_attendance_verification_request(staff, request_id)
        status_code = 200 if result.get("status") in {"rejected", "expired"} else 400
        if result.get("status") == "not_found":
            status_code = 404
        return jsonify(result), status_code

    # Fungsi untuk logout staff dan menghapus cookie session staff.
    @staff_bp.route("/staff/logout")
    # Route untuk mengakhiri sesi staff.
    def staff_logout():
        staff = deps.get_current_staff()
        staff_access = getattr(g, "current_staff_access", None)
        if staff:
            if staff_access:
                deps.revoke_staff_access(staff_access, revoked_by="staff", reason="staff_logout")
                deps.db.session.commit()
            deps.log_staff_activity_event("LOGOUT_STAFF", staff)
        response = redirect(url_for("staff.staff_session_expired", reason="logout"))
        return deps.delete_staff_session_cookie(response)

    return staff_bp
