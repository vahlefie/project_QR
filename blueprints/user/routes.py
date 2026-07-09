from io import BytesIO

import pandas as pd
from flask import Blueprint, jsonify, redirect, render_template, request, send_file, url_for


# Fungsi untuk membuat Blueprint data dan upload tamu milik user.
def create_user_blueprint(deps):
    user_bp = Blueprint("user", __name__)

    # Fungsi untuk menyinkronkan status aktivasi user saat membuka halaman user.
    def sync_current_user_activation(current_user):
        previous_activation = current_user.aktivasi
        deps.sync_user_activation_status(current_user)
        if current_user.aktivasi != previous_activation:
            deps.db.session.commit()

    # Fungsi untuk menangani upload Excel tamu oleh user dan menyiapkan konfirmasi.
    @user_bp.route("/user/upload", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk mengunggah Excel tamu milik user.
    def upload_excel():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")
        sync_current_user_activation(current_user)
        if not current_user.aktivasi:
            context = deps.build_user_guest_context(current_user, "", 1, 10, "latest")
            context["upload_error"] = "Client tidak aktif. Upload data tamu dinonaktifkan."
            return render_template("user_data.html", **context), 403

        try:
            file = deps.get_uploaded_file()
            preview = deps.build_guest_upload_preview(file, current_user)
            saved_upload_path = deps.save_uploaded_guest_file(file, current_user)
            deps.clear_pending_guest_upload()
            if preview["stats"]["duplicate_count"] == 0:
                deps.save_guest_rows(
                    owner_user=current_user,
                    rows=preview["rows"],
                    duplicate_indexes=[],
                    include_duplicates=True,
                )
                context = deps.build_user_guest_context(current_user, "", 1, 10, "latest")
                context["upload_result"] = preview
                deps.log_activity_event(
                    "UPLOAD_GUESTS_USER",
                    details={
                        "owner_user_id": current_user.id,
                        "stats": preview.get("stats", {}),
                        "duplicate_action": "none",
                        "upload_file_path": str(saved_upload_path),
                    },
                )
                return render_template("user_data.html", **context)

            pending_upload = deps.save_pending_guest_upload(current_user, preview)
            deps.log_activity_event(
                "UPLOAD_GUESTS_PENDING",
                details={
                    "owner_user_id": current_user.id,
                    "stats": preview.get("stats", {}),
                    "upload_file_path": str(saved_upload_path),
                },
            )
        except deps.UploadValidationError as exc:
            context = deps.build_user_guest_context(current_user, "", 1, 10, "latest")
            message = str(exc)
            if message == "Format data excel tidak sesuai":
                context["upload_warning"] = message
            else:
                context["upload_error"] = message
            return render_template("user_data.html", **context), 400

        context = deps.build_user_guest_context(current_user, "", 1, 10, "latest")
        context["pending_upload"] = pending_upload
        return render_template("user_data.html", **context)

    # Fungsi untuk menyimpan hasil upload tamu setelah user mengonfirmasi duplicate.
    @user_bp.route("/user/upload-confirm", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk mengonfirmasi hasil preview upload Excel.
    def upload_confirm():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")

        pending_upload = deps.load_pending_guest_upload()
        if not pending_upload or pending_upload.get("owner_user_id") != current_user.id:
            deps.clear_pending_guest_upload()
            context = deps.build_user_guest_context(current_user, "", 1, 10, "latest")
            context["upload_error"] = "Data upload sudah tidak tersedia. Silakan upload ulang."
            return render_template("user_data.html", **context)

        should_update_duplicates = request.form.get("include_duplicates") == "yes"
        if should_update_duplicates:
            saved_count = deps.replace_guest_rows(current_user, pending_upload["rows"])
            message = f"{saved_count} data tamu berhasil diperbarui/disimpan."
        else:
            saved_count = deps.save_guest_rows(
                owner_user=current_user,
                rows=pending_upload["rows"],
                duplicate_indexes=pending_upload.get("duplicate_indexes", []),
                include_duplicates=False,
            )
            message = f"{saved_count} data tamu berhasil disimpan."

        deps.clear_pending_guest_upload()
        deps.log_activity_event(
            "CONFIRM_GUEST_UPLOAD",
            details={
                "owner_user_id": current_user.id,
                "saved_count": saved_count,
                "include_duplicates": should_update_duplicates,
            },
        )
        return redirect(url_for("user.user_data", message=message))

    # Fungsi untuk menambahkan data tamu manual oleh user.
    @user_bp.route("/user/guests/new", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk menambahkan tamu manual milik user.
    def add_user_guest():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")
        sync_current_user_activation(current_user)
        if not current_user.aktivasi:
            return "Client tidak aktif. Tambah tamu dinonaktifkan.", 403

        form_data = {
            "nama": request.form.get("nama", ""),
            "no_hp": request.form.get("no_hp", ""),
            "email": request.form.get("email", ""),
            "status": request.form.get("status", deps.DEFAULT_GUEST_STATUS),
        }
        guest_data = deps.build_manual_guest_data(
            form_data,
            current_user,
            added_by=current_user.nama or current_user.username,
        )

        if not guest_data:
            context = deps.build_user_guest_context(
                current_user,
                request.form.get("search", ""),
                deps.parse_int(request.form.get("page"), 1),
                deps.parse_int(request.form.get("per_page"), 10),
                request.form.get("sort_by", "latest"),
            )
            context["add_guest_error"] = "Nama dan No HP wajib diisi dengan format valid."
            context["add_guest_form"] = form_data
            return render_template("user_data.html", **context), 400
        if deps.is_guest_phone_registered(current_user, guest_data["no_hp"]):
            context = deps.build_user_guest_context(
                current_user,
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
        guest.user_id = current_user.id
        deps.db.session.add(guest)
        deps.db.session.commit()
        deps.log_activity_event(
            "CREATE_GUEST_ROW",
            details={
                "guest_id": guest.id,
                "owner_user_id": current_user.id,
                "guest_name": guest.nama,
            },
        )

        return redirect(url_for("user.user_data", message="Data tamu berhasil ditambahkan."))

    # Fungsi untuk menampilkan data tamu milik user dengan search dan pagination.
    @user_bp.route("/user/data")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk menampilkan data tamu milik user.
    def user_data():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")

        sync_current_user_activation(current_user)
        search = request.args.get("search", "")
        page = deps.parse_int(request.args.get("page"), 1)
        per_page = deps.parse_int(request.args.get("per_page"), 10)
        sort_by = request.args.get("sort_by", "latest")

        context = deps.build_user_guest_context(current_user, search, page, per_page, sort_by)
        context["message"] = request.args.get("message", "")
        return render_template("user_data.html", **context)

    # Fungsi untuk mengunduh data tamu milik user dalam format Excel.
    @user_bp.route("/user/guests/download")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk mengunduh data tamu client ke Excel.
    def download_user_guests():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")

        sync_current_user_activation(current_user)
        if not current_user.aktivasi:
            archive = deps.ensure_final_guest_backup(current_user) or deps.get_latest_final_archive(current_user)
            if not archive:
                return "Data backup final belum tersedia.", 404
            output = deps.build_final_archive_excel(current_user, archive=archive)
            deps.log_activity_event(
                "DOWNLOAD_GUESTS_USER_FINAL",
                details={
                    "owner_user_id": current_user.id,
                    "archive_id": archive.id,
                    "csv_path": archive.csv_path,
                },
            )
            return send_file(
                output,
                as_attachment=True,
                download_name=deps.build_final_guest_export_filename(current_user, archive=archive),
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        search = request.args.get("search", "")
        sort_by = request.args.get("sort_by", "latest")
        query = deps.build_guest_query(
            search=search,
            owner_user_id=current_user.id,
            sort_by=sort_by,
        )

        rows = []
        for index, guest in enumerate(query.all(), start=1):
            rows.append(
                {
                    "no": index,
                    "nama": guest.nama,
                    "no_hp": guest.no_hp or "N/A",
                    "email": guest.email or "N/A",
                    "status": guest.status or deps.DEFAULT_GUEST_STATUS,
                    "kehadiran": deps.format_attendance_time(guest.kehadiran) or "N/A",
                    "verifikasi": guest.verified_by_staff_name or "N/A",
                }
            )

        deps.log_activity_event(
            "DOWNLOAD_GUESTS_USER",
            details={
                "owner_user_id": current_user.id,
                "row_count": len(rows),
                "search": search,
                "sort_by": sort_by,
            },
        )

        output = BytesIO()
        columns = ["no", "nama", "no_hp", "email", "status", "kehadiran", "verifikasi"]
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(rows, columns=columns).to_excel(writer, index=False, sheet_name="Data Tamu")
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=deps.build_active_guest_export_filename(current_user),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # Fungsi untuk menampilkan scanner QR tamu khusus client Premium.
    @user_bp.route("/user/scan")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk menampilkan halaman scan kehadiran user.
    def user_scan():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")

        if not deps.is_premium_user(current_user):
            return (
                render_template(
                    "user_scan.html",
                    user=current_user.nama or current_user.username,
                    is_available=False,
                    verify_url="",
                    error_message="Fitur Scan hanya tersedia untuk paket Premium.",
                ),
                403,
            )

        if not deps.is_owner_in_active_billing_period(current_user):
            return (
                render_template(
                    "user_scan.html",
                    user=current_user.nama or current_user.username,
                    is_available=False,
                    verify_url="",
                    error_message=deps.build_inactive_billing_period_message(),
                ),
                403,
            )

        return render_template(
            "user_scan.html",
            user=current_user.nama or current_user.username,
            is_available=True,
            verify_url=url_for("user.verify_user_scan"),
            error_message="",
        )

    # Fungsi API untuk verifikasi kehadiran dari hasil scan QR panitia.
    @user_bp.route("/user/scan/verify", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk memverifikasi hasil scan QR user.
    def verify_user_scan():
        current_user = deps.get_current_user()
        if not current_user:
            return jsonify({"status": "unauthorized", "message": "Session tidak valid."}), 401

        if not deps.is_premium_user(current_user):
            return jsonify({"status": "forbidden", "message": "Fitur Scan hanya tersedia untuk paket Premium."}), 403
        if not deps.is_owner_in_active_billing_period(current_user):
            return (
                jsonify(
                    {
                        "status": "inactive_period",
                        "message": deps.build_inactive_billing_period_message(),
                    }
                ),
                403,
            )

        try:
            payload = request.get_json(silent=True) or request.form
            result = deps.verify_guest_qr_attendance(current_user, payload.get("token", ""))
            result["request_id"] = deps.get_request_id()
            status_code = (
                200
                if result.get("status") in {"pending_confirmation", "verified", "already_verified", "pending_retry"}
                else 400
            )
            return jsonify(result), status_code
        except Exception as error:
            deps.db.session.rollback()
            deps.log_system_error(error)
            return (
                jsonify(
                    {
                        "status": "server_error",
                        "message": "Gagal Terhubung ke Server.",
                        "request_id": deps.get_request_id(),
                    }
                ),
                500,
            )

    # Route lama dipertahankan agar request lama tidak error, tetapi fitur hapus semua data user dinonaktifkan.
    @user_bp.route("/user/delete-data", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk menghapus semua data tamu milik user.
    def delete_data():
        deps.log_activity_event(
            "DELETE_USER_DATA_DISABLED",
            details={"reason": "feature_disabled"},
        )
        return redirect(url_for("user.user_data"))

    return user_bp
