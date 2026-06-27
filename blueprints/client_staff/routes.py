from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request


# Fungsi untuk membuat Blueprint pengelolaan staff dari sisi client.
def create_client_staff_blueprint(deps):
    client_staff_bp = Blueprint("client_staff", __name__)

    # Fungsi untuk menolak fitur staff saat client tidak aktif.
    def is_active_client(current_user):
        return deps.is_owner_in_active_billing_period(current_user)

    def inactive_client_response():
        return "Akun client tidak aktif.", 403

    # Fungsi untuk menampilkan dan menambahkan staff milik client.
    @client_staff_bp.route("/user/staff", methods=["GET", "POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk menampilkan pengelolaan staff milik user.
    def user_staff():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")
        if not is_active_client(current_user):
            return inactive_client_response()

        if request.method == "POST":
            form_data = {
                "no_hp": request.form.get("no_hp", ""),
                "nama": request.form.get("nama", ""),
            }
            no_hp = deps.clean_staff_phone(form_data["no_hp"])
            nama = deps.clean_staff_name(form_data["nama"])
            error = deps.validate_staff_form(current_user, nama, no_hp)

            if error:
                context = deps.build_staff_page_context(current_user, error=error, form_data=form_data)
                return render_template("user_staff.html", **context), 400

            staff = deps.Staff()
            staff.owner_user_id = current_user.id
            staff.no_hp = no_hp
            staff.nama = nama
            deps.db.session.add(staff)
            deps.db.session.commit()
            deps.log_activity_event(
                "CREATE_STAFF",
                details={
                    "staff_id": staff.id,
                    "staff_name": staff.nama,
                    "staff_no_hp": staff.no_hp,
                    "owner_user_id": current_user.id,
                },
            )
            return deps.build_staff_redirect(message="Staff berhasil ditambahkan.")

        return render_template("user_staff.html", **deps.build_staff_page_context(current_user))

    # Fungsi untuk membuat URL random dan PIN login staff dari dashboard client.
    @client_staff_bp.route("/user/staff/<int:staff_id>/login", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk membuat akses login staff.
    def login_staff(staff_id):
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")
        if not is_active_client(current_user):
            return inactive_client_response()

        staff = deps.Staff.query.filter_by(id=staff_id, owner_user_id=current_user.id).first()
        if not staff:
            return deps.build_staff_redirect(error="Staff tidak ditemukan.")
        if staff.is_blocked:
            return (
                render_template(
                    "staff_access_created.html",
                    user=deps.get_user_display_name(current_user),
                    error="Staff sedang diblokir. Unblock staff sebelum membuat akses login.",
                ),
                403,
            )

        staff_access, raw_token, pin = deps.create_staff_access(staff)
        access_url = deps.build_staff_access_url(raw_token)

        deps.log_activity_event(
            "CREATE_STAFF_ACCESS",
            details={
                "staff_id": staff.id,
                "staff_access_id": staff_access.id,
                "staff_name": staff.nama,
                "staff_no_hp": staff.no_hp,
                "owner_user_id": current_user.id,
            },
        )
        return render_template(
            "staff_access_created.html",
            user=deps.get_user_display_name(current_user),
            staff=staff,
            access_url=access_url,
            pin=pin,
        )

    # Fungsi untuk mencabut akses aktif staff dari dashboard client.
    @client_staff_bp.route("/user/staff/<int:staff_id>/logout", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk mencabut sesi staff dari sisi client.
    def logout_staff_from_client(staff_id):
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")
        if not is_active_client(current_user):
            return inactive_client_response()

        staff = deps.Staff.query.filter_by(id=staff_id, owner_user_id=current_user.id).first()
        if not staff:
            return deps.build_staff_redirect(error="Staff tidak ditemukan.")

        active_access = deps.get_active_staff_access(staff)
        if active_access:
            deps.revoke_staff_access(active_access, revoked_by="client", reason="client_logout")
            deps.db.session.commit()
            deps.log_activity_event(
                "LOGOUT_STAFF_FROM_CLIENT",
                details={
                    "staff_id": staff.id,
                    "staff_access_id": active_access.id,
                    "staff_name": staff.nama,
                    "staff_no_hp": staff.no_hp,
                    "owner_user_id": current_user.id,
                },
            )
            return deps.build_staff_redirect(message="Akses staff berhasil dilogout.")

        return deps.build_staff_redirect(message="Staff sudah tidak memiliki akses aktif.")

    # Fungsi untuk memblokir staff milik client.
    @client_staff_bp.route("/user/staff/<int:staff_id>/block", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk memblokir akun staff.
    def block_staff(staff_id):
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")
        if not is_active_client(current_user):
            return inactive_client_response()

        staff = deps.Staff.query.filter_by(id=staff_id, owner_user_id=current_user.id).first()
        if not staff:
            return deps.build_staff_redirect(error="Staff tidak ditemukan.")

        deps.block_staff_account(staff, reason="client_block")
        deps.db.session.commit()
        deps.log_activity_event(
            "BLOCK_STAFF",
            details={
                "staff_id": staff.id,
                "staff_name": staff.nama,
                "staff_no_hp": staff.no_hp,
                "owner_user_id": current_user.id,
            },
        )
        return deps.build_staff_redirect(message="Staff berhasil diblokir.")

    # Fungsi untuk membuka blokir staff milik client.
    @client_staff_bp.route("/user/staff/<int:staff_id>/unblock", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk membuka blokir akun staff.
    def unblock_staff(staff_id):
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")
        if not is_active_client(current_user):
            return inactive_client_response()

        staff = deps.Staff.query.filter_by(id=staff_id, owner_user_id=current_user.id).first()
        if not staff:
            return deps.build_staff_redirect(error="Staff tidak ditemukan.")

        deps.unblock_staff_account(staff)
        deps.db.session.commit()
        deps.log_activity_event(
            "UNBLOCK_STAFF",
            details={
                "staff_id": staff.id,
                "staff_name": staff.nama,
                "staff_no_hp": staff.no_hp,
                "owner_user_id": current_user.id,
            },
        )
        return deps.build_staff_redirect(message="Blokir staff berhasil dilepas.")

    # Fungsi untuk mengirim status aktif/blokir staff ke halaman client.
    @client_staff_bp.route("/user/staff/status")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk mengambil status staff milik user.
    def user_staff_status():
        current_user = deps.get_current_user()
        if not current_user:
            return jsonify({"staff": []})
        if not is_active_client(current_user):
            return jsonify({"staff": []}), 403
        return jsonify({"staff": deps.build_staff_status_items(current_user)})

    # Fungsi untuk mengambil log aktivitas staff terpilih pada hari ini.
    @client_staff_bp.route("/user/staff/<int:staff_id>/logs")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER)
    # Route untuk mengambil log aktivitas staff milik user.
    def user_staff_logs(staff_id):
        current_user = deps.get_current_user()
        if not current_user:
            return jsonify({"error": "Session client tidak valid."}), 401
        if not is_active_client(current_user):
            return jsonify({"error": "Akun client tidak aktif."}), 403

        staff = deps.Staff.query.filter_by(id=staff_id, owner_user_id=current_user.id).first()
        if not staff:
            return jsonify({"error": "Staff tidak ditemukan."}), 404

        today_text = datetime.now().strftime("%d-%m-%Y")
        staff_name = staff.nama or staff.no_hp or "Staff"
        return jsonify(
            {
                "title": f"Log Aktivitas Staff {staff_name} {today_text}",
                "keyword": deps.build_staff_log_keyword(staff),
                "staff_name": staff_name,
                "entries": deps.get_today_staff_log_entries(staff),
            }
        )

    return client_staff_bp
