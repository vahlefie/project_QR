from flask import Blueprint, redirect, render_template, request, session
from sqlalchemy import func


# Fungsi untuk membuat Blueprint autentikasi dengan dependency dari aplikasi utama.
def create_auth_blueprint(deps):
    auth_bp = Blueprint("auth", __name__)

    # Fungsi untuk mengarahkan halaman root ke halaman login.
    @auth_bp.route("/")
    # Route untuk menampilkan halaman awal aplikasi.
    def index():
        if session.get("user"):
            if session.get("role") == deps.ROLE_SUPER_ADMIN:
                return redirect("/super-admin/dashboard")
            if session.get("role") == deps.ROLE_ADMIN:
                return redirect("/admin/dashboard")
            if session.get("role") == deps.ROLE_USER:
                return redirect("/user/dashboard")
        return redirect("/login")

    # Fungsi untuk menangani autentikasi login semua role.
    @auth_bp.route("/login", methods=["GET", "POST"])
    # Route untuk memproses login pengguna.
    def login():
        if request.method == "POST":
            identifier = request.form.get("identifier", "").strip()
            password = request.form.get("password", "")
            client_ip = deps.get_client_ip()
            login_throttle = deps.find_login_throttle(identifier, client_ip)

            if login_throttle and deps.is_login_throttle_locked(login_throttle):
                login_attempts = login_throttle.failed_attempts
                session[deps.LOGIN_ATTEMPT_SESSION_KEY] = login_attempts
                deps.log_auth_event(
                    "AUTH_LOCKED",
                    "Login ditolak: terlalu banyak percobaan gagal",
                    identifier=identifier,
                    level="WARN",
                    login_attempts=login_attempts,
                    is_brute_force_suspicion=True,
                )
                remaining_seconds = deps.get_login_lockout_remaining_seconds(login_throttle)
                return (
                    f"Terlalu banyak percobaan login gagal. Coba lagi dalam {remaining_seconds // 60 + 1} menit.",
                    429,
                )

            user = deps.User.query.filter(
                deps.User.username == identifier,
                deps.User.role.in_((deps.ROLE_ADMIN, deps.ROLE_SUPER_ADMIN)),
            ).first()
            if not user:
                if "@" in identifier:
                    user = deps.User.query.filter(
                        func.lower(deps.User.email) == identifier.lower(),
                        deps.User.role == deps.ROLE_USER,
                    ).first()
                else:
                    normalized_identifier = deps.normalize_phone_number(identifier)
                    no_hp = deps.parse_int(normalized_identifier)
                    if no_hp is not None:
                        user = deps.User.query.filter_by(no_hp=no_hp, role=deps.ROLE_USER).first()

            if user and deps.password_matches(user.password, password):
                if getattr(user, "is_blocked", False):
                    deps.log_auth_event(
                        "AUTH_BLOCKED",
                        "Login ditolak: akun sedang diblokir",
                        account=user,
                        level="WARN",
                    )
                    return "Akun sedang diblokir. Hubungi administrator.", 403

                deps.clear_login_throttle(identifier, client_ip)
                deps.start_login_session(user)
                session[deps.LOGIN_ATTEMPT_SESSION_KEY] = 0
                deps.log_auth_event(
                    "AUTH_SUCCESS",
                    "Login berhasil",
                    account=user,
                    login_attempts=0,
                )
                deps.log_activity_event(
                    "LOGIN_ACCOUNT",
                    username=user.username,
                    role=user.role,
                )

                if user.must_reset_password:
                    return redirect(deps.PASSWORD_RESET_PATH)
                if user.role == deps.ROLE_SUPER_ADMIN:
                    return redirect("/super-admin/dashboard")
                if user.role == deps.ROLE_ADMIN:
                    return redirect("/admin/dashboard")
                return redirect("/user/dashboard")

            login_throttle = deps.register_failed_login(identifier, client_ip)
            login_attempts = login_throttle.failed_attempts
            session[deps.LOGIN_ATTEMPT_SESSION_KEY] = login_attempts
            deps.log_auth_event(
                "AUTH_FAILED",
                "Gagal login: kata sandi salah" if user else "Gagal login: akun tidak ditemukan",
                account=user,
                identifier=identifier,
                level="WARN",
                login_attempts=login_attempts,
                is_brute_force_suspicion=deps.is_login_throttle_locked(login_throttle),
            )
            if deps.is_login_throttle_locked(login_throttle):
                remaining_seconds = deps.get_login_lockout_remaining_seconds(login_throttle)
                return (
                    f"Terlalu banyak percobaan login gagal. Coba lagi dalam {remaining_seconds // 60 + 1} menit.",
                    429,
                )
            return "Login gagal ❌"

        return render_template("login.html")

    # Fungsi untuk menangani pembuatan password baru oleh akun yang sedang login.
    @auth_bp.route("/reset-password", methods=["GET", "POST"])
    @auth_bp.route(deps.PASSWORD_RESET_PATH, methods=["GET", "POST"])
    @deps.login_required
    # Route untuk memproses reset password akun aktif.
    def reset_password():
        current_user = deps.get_current_user()
        if not current_user:
            return redirect("/login")

        if request.method == "POST":
            password = deps.get_form_text("password")
            password_confirmation = deps.get_form_text("password_confirmation")

            if password != password_confirmation:
                context = deps.build_password_template_context("Konfirmasi password tidak sama.")
                return render_template("reset_password.html", **context)

            if not deps.is_valid_password_for_role(password, current_user.role):
                context = deps.build_password_template_context(
                    deps.get_password_title_for_role(current_user.role) + "."
                )
                return render_template("reset_password.html", **context)

            deps.set_account_password(current_user, password)
            current_user.must_reset_password = False
            deps.db.session.commit()
            deps.log_activity_event(
                "RESET_OWN_PASSWORD",
                details={"account_role": current_user.role},
            )

            if current_user.role == deps.ROLE_SUPER_ADMIN:
                return redirect("/super-admin/dashboard")
            if current_user.role == deps.ROLE_ADMIN:
                return redirect("/admin/dashboard")
            return redirect("/user/dashboard")

        return render_template("reset_password.html", **deps.build_password_template_context())

    # Fungsi untuk logout dan membersihkan session user.
    @auth_bp.route("/logout")
    # Route untuk mengakhiri sesi login pengguna.
    def logout():
        username = session.get("user")
        role = session.get("role")
        tracking_session_id = deps.get_tracking_session_id()
        if username:
            deps.log_auth_event(
                "AUTH_LOGOUT",
                "Logout berhasil",
                identifier=username,
                login_attempts=0,
            )
            deps.log_activity_event(
                "LOGOUT_ACCOUNT",
                username=username,
                role=role,
                session_id=tracking_session_id,
            )
        deps.clear_active_login_session_for_current_user()
        deps.end_login_session()
        return redirect("/login")

    return auth_bp
