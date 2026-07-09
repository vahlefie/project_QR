from flask import Blueprint, redirect, request


# Fungsi untuk membuat Blueprint update dan hapus baris tamu lintas role.
def create_guests_blueprint(deps):
    guests_bp = Blueprint("guests", __name__)

    # Fungsi untuk mengecek request client inactive pada mutasi data tamu.
    def is_inactive_client_request():
        current_user = deps.get_current_user()
        return bool(
            current_user
            and current_user.role == deps.ROLE_USER
            and not deps.is_owner_in_active_billing_period(current_user)
        )

    # Fungsi untuk memperbarui status tamu oleh user/admin.
    @guests_bp.route("/guests/<int:guest_id>/status", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER, deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk memperbarui status tamu.
    def update_guest_status(guest_id):
        guest = deps.get_accessible_guest(guest_id)
        if not guest:
            return "Data tamu tidak ditemukan", 404
        if is_inactive_client_request():
            return "Client tidak aktif. Edit data tamu dinonaktifkan.", 403

        current_user = deps.get_current_user()
        is_client_full_edit = bool(
            current_user
            and current_user.role == deps.ROLE_USER
            and any(field_name in request.form for field_name in ("nama", "no_hp", "email"))
        )
        if is_client_full_edit:
            guest_data = deps.build_guest_edit_data(request.form)
            if not guest_data:
                return "Nama dan No HP wajib diisi dengan format valid.", 400
            if deps.is_guest_phone_registered(current_user, guest_data["no_hp"], exclude_guest_id=guest.id):
                return "No HP sudah terdaftar.", 400

            old_data = {
                "nama": guest.nama,
                "no_hp": guest.no_hp,
                "email": guest.email,
                "status": guest.status,
            }
            guest.nama = guest_data["nama"]
            guest.no_hp = guest_data["no_hp"]
            guest.email = guest_data["email"]
            guest.status = guest_data["status"]
            deps.db.session.commit()
            deps.log_activity_event(
                "UPDATE_GUEST_ROW",
                details={
                    "guest_id": guest.id,
                    "owner_user_id": guest.user_id,
                    "old_data": old_data,
                    "new_data": guest_data,
                },
            )
            return deps.build_guest_table_redirect()

        old_status = guest.status
        guest.status = deps.clean_guest_status(request.form.get("status"))
        deps.db.session.commit()
        deps.log_activity_event(
            "UPDATE_GUEST_STATUS",
            details={
                "guest_id": guest.id,
                "owner_user_id": guest.user_id,
                "old_status": old_status,
                "new_status": guest.status,
            },
        )
        return deps.build_guest_table_redirect()

    # Fungsi untuk membuka WhatsApp berisi pesan undangan QR tamu.
    @guests_bp.route("/guests/<int:guest_id>/whatsapp-invite")
    @deps.login_required
    @deps.role_required(deps.ROLE_USER, deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk redirect pengiriman undangan QR lewat WhatsApp.
    def send_guest_whatsapp_invite(guest_id):
        guest = deps.get_accessible_guest(guest_id)
        if not guest:
            return "Data tamu tidak ditemukan", 404
        if is_inactive_client_request():
            return "Client tidak aktif. Kirim undangan dinonaktifkan.", 403

        try:
            invite = deps.build_guest_whatsapp_invite(guest)
        except ValueError as exc:
            return str(exc), 400

        deps.log_activity_event(
            "OPEN_GUEST_WHATSAPP_INVITE",
            details={
                "guest_id": guest.id,
                "owner_user_id": guest.user_id,
                "guest_no_hp": guest.no_hp,
                "send_mode": invite["mode"],
                "short_qr_url": invite["short_qr_url"],
            },
        )
        return redirect(invite["send_url"])

    # Fungsi untuk menghapus baris data tamu oleh user/admin.
    @guests_bp.route("/guests/<int:guest_id>/delete", methods=["POST"])
    @deps.login_required
    @deps.role_required(deps.ROLE_USER, deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)
    # Route untuk menghapus satu baris tamu.
    def delete_guest_row(guest_id):
        guest = deps.get_accessible_guest(guest_id)
        if not guest:
            return "Data tamu tidak ditemukan", 404
        if is_inactive_client_request():
            return "Client tidak aktif. Hapus data tamu dinonaktifkan.", 403

        deleted_guest_details = {
            "guest_id": guest.id,
            "owner_user_id": guest.user_id,
            "guest_name": guest.nama,
        }
        deps.db.session.delete(guest)
        deps.db.session.commit()
        deps.log_activity_event(
            "DELETE_GUEST_ROW",
            details=deleted_guest_details,
        )
        return deps.build_guest_table_redirect()

    return guests_bp
