from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for


# Fungsi untuk membuat Blueprint verifikasi kehadiran tamu.
def create_attendance_blueprint(deps):
    attendance_bp = Blueprint("attendance", __name__)

    # Fungsi untuk menambahkan URL polling dan hasil pada payload request verifikasi.
    def attach_attendance_request_urls(payload, attendance_token):
        request_id = payload.get("verification_request_id") or payload.get("request_id")
        if not request_id:
            return payload
        payload["status_url"] = url_for(
            "attendance.guest_attendance_request_status",
            attendance_token=attendance_token,
            request_id=request_id,
        )
        payload["result_url"] = url_for(
            "attendance.guest_attendance_request_result",
            attendance_token=attendance_token,
            request_id=request_id,
        )
        return payload

    # Fungsi untuk membuat halaman hasil request verifikasi kehadiran tamu.
    def render_guest_attendance_request_result(owner_user, attendance_token, payload, status_code=200):
        page_state = payload.get("status")
        if page_state not in {"pending", "confirmed", "expired"}:
            page_state = "message"
        payload = attach_attendance_request_urls(payload, attendance_token)
        return (
            render_template(
                "guest_attendance.html",
                owner_user=owner_user,
                verify_url=url_for("attendance.verify_guest_attendance_route", attendance_token=attendance_token),
                is_available=True,
                error_message="",
                page_state=page_state,
                status_url=payload.get("status_url", ""),
                result_url=payload.get("result_url", ""),
                result_message=payload.get("message", ""),
                request_id=payload.get("request_id"),
            ),
            status_code,
        )

    # Fungsi untuk menampilkan landing page publik verifikasi kehadiran tamu.
    @attendance_bp.route("/kehadiran/<attendance_token>")
    # Route untuk menampilkan halaman verifikasi kehadiran publik.
    def guest_attendance_landing(attendance_token):
        owner_user = deps.get_attendance_owner_from_token(attendance_token)
        if not owner_user:
            deps.log_attendance_event(
                "GUEST_ATTENDANCE_INVALID_LINK",
                no_hp=None,
                level="WARN",
                details={"attendance_token_prefix": attendance_token[:12]},
            )
            return (
                render_template(
                    "guest_attendance.html",
                    owner_user=None,
                    verify_url="",
                    is_available=False,
                    error_message="Link verifikasi tidak valid.",
                ),
                404,
            )

        if not deps.is_owner_in_active_billing_period(owner_user):
            deps.log_attendance_event(
                "GUEST_ATTENDANCE_INACTIVE_PERIOD",
                owner_user=owner_user,
                no_hp=None,
                level="WARN",
                details={"attendance_token_prefix": attendance_token[:12]},
            )
            return (
                render_template(
                    "guest_attendance.html",
                    owner_user=owner_user,
                    verify_url="",
                    is_available=False,
                    error_message=deps.build_inactive_billing_period_message(),
                ),
                403,
            )

        return render_template(
            "guest_attendance.html",
            owner_user=owner_user,
            verify_url=url_for("attendance.verify_guest_attendance_route", attendance_token=attendance_token),
            is_available=True,
            error_message="",
        )

    # Fungsi untuk membuat gambar QR URL verifikasi kehadiran client.
    @attendance_bp.route("/kehadiran/<attendance_token>/qr.svg")
    # Route untuk mengirim QR SVG yang berisi URL halaman verifikasi kehadiran.
    def guest_attendance_qr_image(attendance_token):
        owner_user = deps.get_attendance_owner_from_token(attendance_token)
        if not owner_user:
            return Response("Link verifikasi tidak valid.", status=404, mimetype="text/plain")
        if not deps.is_owner_in_active_billing_period(owner_user):
            return Response(deps.build_inactive_billing_period_message(), status=403, mimetype="text/plain")

        attendance_url = url_for(
            "attendance.guest_attendance_landing",
            attendance_token=attendance_token,
            _external=True,
        )
        return Response(deps.build_guest_qr_svg(attendance_url), mimetype="image/svg+xml")

    # Fungsi API untuk memeriksa nomor HP tamu dan mencatat waktu kehadiran.
    @attendance_bp.route("/kehadiran/<attendance_token>/verify", methods=["POST"])
    # Route untuk memproses verifikasi kehadiran tamu.
    def verify_guest_attendance_route(attendance_token):
        owner_user = deps.get_attendance_owner_from_token(attendance_token)
        if not owner_user:
            deps.log_attendance_event(
                "GUEST_ATTENDANCE_INVALID_LINK",
                no_hp=None,
                level="WARN",
                details={"attendance_token_prefix": attendance_token[:12]},
            )
            return (
                jsonify(
                    {
                        "status": "invalid_link",
                        "message": "Link verifikasi tidak valid.",
                        "request_id": deps.get_request_id(),
                        "client_request_id": request.headers.get("X-Client-Request-ID"),
                    }
                ),
                404,
            )

        if not deps.is_owner_in_active_billing_period(owner_user):
            deps.log_attendance_event(
                "GUEST_ATTENDANCE_INACTIVE_PERIOD",
                owner_user=owner_user,
                no_hp=None,
                level="WARN",
                details={"attendance_token_prefix": attendance_token[:12]},
            )
            return (
                jsonify(
                    {
                        "status": "inactive_period",
                        "message": deps.build_inactive_billing_period_message(),
                        "request_id": deps.get_request_id(),
                        "client_request_id": request.headers.get("X-Client-Request-ID"),
                    }
                ),
                403,
            )

        try:
            payload = request.get_json(silent=True) or request.form
            result = deps.verify_guest_attendance(owner_user, payload.get("no_hp", ""))
            attach_attendance_request_urls(result, attendance_token)
            result["request_id"] = deps.get_request_id()
            result["client_request_id"] = request.headers.get("X-Client-Request-ID")
            return jsonify(result)
        except Exception as error:
            deps.db.session.rollback()
            deps.log_system_error(error)
            deps.log_attendance_event(
                "GUEST_ATTENDANCE_SERVER_ERROR",
                owner_user=owner_user,
                no_hp=None,
                level="ERROR",
                details={"error_type": error.__class__.__name__, "message": str(error)},
            )
            return (
                jsonify(
                    {
                        "status": "server_error",
                        "message": "Gagal Terhubung ke Server.",
                        "request_id": deps.get_request_id(),
                        "client_request_id": request.headers.get("X-Client-Request-ID"),
                    }
                ),
                500,
            )

    # Fungsi API polling status request verifikasi kehadiran tamu.
    @attendance_bp.route("/kehadiran/<attendance_token>/request/<int:request_id>/status")
    # Route untuk mengambil status request verifikasi tamu.
    def guest_attendance_request_status(attendance_token, request_id):
        owner_user = deps.get_attendance_owner_from_token(attendance_token)
        if not owner_user:
            return jsonify({"status": "invalid_link", "message": "Link verifikasi tidak valid."}), 404
        if not deps.is_owner_in_active_billing_period(owner_user):
            return (
                jsonify(
                    {
                        "status": "inactive_period",
                        "message": deps.build_inactive_billing_period_message(),
                    }
                ),
                403,
            )

        payload = deps.get_guest_attendance_verification_status(owner_user, request_id)
        attach_attendance_request_urls(payload, attendance_token)
        status_code = 404 if payload.get("status") == "not_found" else 200
        return jsonify(payload), status_code

    # Fungsi halaman hasil request verifikasi kehadiran tamu.
    @attendance_bp.route("/kehadiran/<attendance_token>/request/<int:request_id>/result")
    # Route untuk menampilkan hasil request verifikasi tamu tanpa popup.
    def guest_attendance_request_result(attendance_token, request_id):
        owner_user = deps.get_attendance_owner_from_token(attendance_token)
        if not owner_user:
            return (
                render_template(
                    "guest_attendance.html",
                    owner_user=None,
                    verify_url="",
                    is_available=False,
                    error_message="Link verifikasi tidak valid.",
                    page_state="error",
                ),
                404,
            )
        if not deps.is_owner_in_active_billing_period(owner_user):
            return (
                render_template(
                    "guest_attendance.html",
                    owner_user=owner_user,
                    verify_url="",
                    is_available=False,
                    error_message=deps.build_inactive_billing_period_message(),
                    page_state="error",
                ),
                403,
            )

        payload = deps.get_guest_attendance_verification_status(owner_user, request_id)
        status_code = 404 if payload.get("status") == "not_found" else 200
        return render_guest_attendance_request_result(owner_user, attendance_token, payload, status_code)

    # Fungsi untuk menampilkan halaman QR publik milik tamu Premium.
    @attendance_bp.route("/qr/<guest_token>")
    # Route untuk menampilkan halaman QR tamu.
    def guest_qr_page(guest_token):
        guest = deps.get_guest_from_qr_token(guest_token)
        if not guest:
            return (
                render_template(
                    "guest_qr.html",
                    guest=None,
                    owner_user=None,
                    is_available=False,
                    is_verified=False,
                    show_welcome=False,
                    qr_image_url="",
                    status_url="",
                    welcome_message="",
                    already_verified_message="Kode QR tidak valid.",
                ),
                404,
            )

        if not deps.is_owner_in_active_billing_period(guest.owner):
            return (
                render_template(
                    "guest_qr.html",
                    guest=guest,
                    owner_user=guest.owner,
                    is_available=False,
                    is_verified=False,
                    show_welcome=False,
                    qr_image_url="",
                    status_url="",
                    welcome_message="",
                    already_verified_message=deps.build_inactive_billing_period_message(),
                ),
                403,
            )

        is_verified = bool(guest.kehadiran)
        show_welcome = is_verified and request.args.get("verified") == "1"
        return render_template(
            "guest_qr.html",
            guest=guest,
            owner_user=guest.owner,
            is_available=True,
            is_verified=is_verified,
            show_welcome=show_welcome,
            qr_image_url=url_for("attendance.guest_qr_image", guest_token=guest_token),
            status_url=url_for("attendance.guest_qr_status", guest_token=guest_token),
            qr_page_ttl_seconds=deps.GUEST_QR_PAGE_TTL_SECONDS,
            welcome_message=deps.build_qr_welcome_message(guest),
            already_verified_message=deps.build_qr_already_verified_message(),
        )

    # Fungsi redirect URL pendek QR tamu ke halaman QR asli.
    @attendance_bp.route("/q/<short_code>")
    # Route untuk membuka URL pendek QR tamu.
    def guest_qr_short_redirect(short_code):
        guest = deps.get_guest_from_short_qr_code(short_code)
        if not guest:
            return (
                render_template(
                    "guest_qr.html",
                    guest=None,
                    owner_user=None,
                    is_available=False,
                    is_verified=False,
                    show_welcome=False,
                    qr_image_url="",
                    status_url="",
                    welcome_message="",
                    already_verified_message="Link QR tidak valid.",
                ),
                404,
            )

        if not deps.is_owner_in_active_billing_period(guest.owner):
            return (
                render_template(
                    "guest_qr.html",
                    guest=guest,
                    owner_user=guest.owner,
                    is_available=False,
                    is_verified=False,
                    show_welcome=False,
                    qr_image_url="",
                    status_url="",
                    welcome_message="",
                    already_verified_message=deps.build_inactive_billing_period_message(),
                ),
                403,
            )

        guest_token = deps.build_guest_qr_token(guest)
        return redirect(url_for("attendance.guest_qr_page", guest_token=guest_token))

    # Fungsi untuk membuat gambar QR SVG yang berisi URL publik QR tamu.
    @attendance_bp.route("/qr/<guest_token>/image.svg")
    # Route untuk mengirim gambar SVG QR tamu.
    def guest_qr_image(guest_token):
        guest = deps.get_guest_from_qr_token(guest_token)
        if not guest:
            return Response("Kode QR tidak valid.", status=404, mimetype="text/plain")
        if not deps.is_owner_in_active_billing_period(guest.owner):
            return Response(deps.build_inactive_billing_period_message(), status=403, mimetype="text/plain")

        qr_value = deps.build_guest_qr_scan_value(guest, guest_token)
        return Response(deps.build_guest_qr_svg(qr_value), mimetype="image/svg+xml")

    # Fungsi status publik agar halaman QR tamu dapat reload setelah discan panitia.
    @attendance_bp.route("/qr/<guest_token>/status")
    # Route untuk mengambil status verifikasi QR tamu.
    def guest_qr_status(guest_token):
        guest = deps.get_guest_from_qr_token(guest_token)
        if not guest:
            return jsonify({"status": "invalid_qr", "message": "Kode QR tidak valid."}), 404
        if not deps.is_owner_in_active_billing_period(guest.owner):
            return (
                jsonify(
                    {
                        "status": "inactive_period",
                        "message": deps.build_inactive_billing_period_message(),
                    }
                ),
                403,
            )

        if guest.kehadiran:
            return jsonify(
                {
                    "status": "verified",
                    "guest_name": guest.nama,
                    "attendance_time": deps.format_attendance_time(guest.kehadiran),
                }
            )
        return jsonify({"status": "pending"})

    return attendance_bp
